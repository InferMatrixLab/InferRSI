"""Campaign assembly: real root acquisition, independent searches, GVO and final gating."""

import math
import time
from dataclasses import asdict, dataclass, replace

from inferrsi.contracts.claim import Verdict
from inferrsi.harness.artifact_primitives import digest

from . import search_tree as tree
from .gvo import train_group
from .search_adapter import development_binding, validate_development_evidence
from .search_records import decode, encode, initial_conditions
from .vats import Search


def qualify_root(control, campaign, adapter, root, contract):
    """Acquire root evidence using real checks and the same authoritative accounting."""
    experiment = development_binding(adapter)
    retained = control.recover_unstarted(campaign)["state"].get("qualified_root")
    if retained is not None:
        state = decode(retained)
        if state.contract != contract or tree.candidate(state, state.root_id) != root:
            raise ValueError("Root qualification is bound to another frozen context")
        validate_development_evidence(state, experiment)
        tree.accept(state)
        return state
    receipts = []
    for check in contract.checks:
        doc = control.read(campaign)
        binding = {
            "candidate": asdict(root),
            "context": asdict(contract.context),
            "check": check,
            "adapter": adapter.identity,
            **experiment,
        }
        operation = "root-" + digest(binding)
        previous = doc["operations"].get(operation)
        if previous is None:
            control.claim(
                campaign,
                doc["revision"],
                operation,
                category="root",
                cap_ms=adapter.checks[check],
                domains=(adapter.domain,),
                binding=binding,
            )
            claim = control.launch(campaign, operation)
            result = adapter.verify(root, check, operation, claim["deadline"])
        elif previous["status"] == "claimed":
            raise ValueError("Root reservation still awaits launch")
        elif previous["status"] == "settled":
            if "started_at" not in previous:
                raise ValueError("Root qualification did not start")
            result = previous["receipt"]
        else:
            result = adapter.recover(operation, {"kind": "verify", "binding": binding})
            if result is None:
                raise ValueError("Root execution unknown; recover its receipt without relaunch")
        control.settle(
            campaign,
            operation,
            result,
            actual_ms=result.get("elapsed_ms"),
            cleanup_verified=result.get("cleanup_verified"),
        )
        if (
            result["cleanup_verified"] is not True
            or result["verdict"] != "PASS"
            or control.read(campaign)["blocked"]
        ):
            raise ValueError("Root lacks complete admissible real evidence")
        attempt = tree.Attempt(
            operation,
            operation,
            operation,
            operation,
            contract.search_id,
            root.candidate_id,
            root.artifact_digest,
            check,
            contract.context,
            root.dependencies,
            **experiment,
        )
        receipts.append(
            tree.Receipt(attempt, Verdict.PASS, result["evidence_digest"], result.get("objective"))
        )
    state = tree.initialize(contract, root, receipts, dependencies=root.dependencies)
    doc = control.read(campaign)
    control.update(campaign, doc["revision"], lambda body: body | {"qualified_root": encode(state)})
    return state


def import_qualified_root(source, contract):
    """Explicit root-only evidence import under identical artifact/check/context scope.

    No new physical execution is asserted: execution/reservation/lease keys and
    evidence digests retain their original identity. The receiving attempt is a
    scoped import recorded in the campaign; arbitrary child evidence is not reused.
    """
    if (
        source.contract.context != contract.context
        or source.contract.checks != contract.checks
        or source.contract.objective_check != contract.objective_check
        or source.contract.direction != contract.direction
    ):
        raise ValueError("Root evidence reuse requires an identical verification contract")
    root = tree.candidate(source, source.root_id)
    observed = tree.evidence(source, source.root_id)
    if len(observed) != len(contract.checks) or any(
        r.verdict != Verdict.PASS for r in observed.values()
    ):
        raise ValueError("Cannot import invalid root evidence")
    receipts = [
        replace(
            record,
            attempt=replace(
                record.attempt,
                search_id=contract.search_id,
                attempt_id=f"{contract.search_id}-import-{check}",
            ),
        )
        for check, record in observed.items()
    ]
    return tree.initialize(contract, root, receipts, dependencies=source.dependencies)


def collect_group(
    control, campaign, adapter, root, snapshot, settings, *, group_id, size, seed=0, collect=True
):
    if type(size) is not int or size < 2:
        raise ValueError("A group needs two or more independent searches")
    doc = control.recover_unstarted(campaign)
    outstanding = sum(
        max(
            0,
            settings.search_ms
            - doc["state"]["searches"].get(f"{group_id}-{i}", {}).get("spent_ms", 0),
        )
        for i in range(size)
        if doc["state"]["searches"].get(f"{group_id}-{i}", {}).get("status") != "complete"
    )
    if outstanding > min(control.available(doc), (doc["deadline"] - time.time()) * 1000):
        raise ValueError("Group cannot provide identical search budgets within the campaign cap")
    result = []
    for index in range(size):
        search_id = f"{group_id}-{index}"
        contract = replace(
            root.contract, search_id=search_id, improver_snapshot=digest(snapshot.document())
        )
        initial = import_qualified_root(root, contract)
        search = Search(control, campaign, search_id, snapshot, settings, adapter)
        doc = control.read(campaign)
        if search_id not in doc["state"]["searches"]:
            search.start(initial, seed=seed + index, collect=collect)
        else:
            _, retained, retained_tree = search.read()
            if (
                retained["seed"] != seed + index
                or retained["collect"] != collect
                or retained_tree.contract != contract
                or tree.candidate(retained_tree, retained_tree.root_id)
                != tree.candidate(initial, initial.root_id)
            ):
                raise ValueError("Resumed group has different frozen starting conditions")
        result.append(search.run())
    return tuple(result)


def learn(
    control,
    campaign,
    adapter,
    root,
    snapshot,
    settings,
    *,
    rounds,
    group_size,
    training_cap_ms,
    learning_rate,
    seed=0,
    mode="reset",
    **training,
):
    if type(rounds) is not int or rounds < 1 or mode not in ("reset", "carry"):
        raise ValueError("Frozen positive outer rounds and Reset/Carry mode are required")
    reference = snapshot
    for index in range(rounds):
        records = collect_group(
            control,
            campaign,
            adapter,
            root,
            snapshot,
            settings,
            group_id=f"round-{index}",
            size=group_size,
            seed=seed + index * group_size,
        )
        ids = [decode(r["tree"]).contract.search_id for r in records]
        doc = control.read(campaign)
        retained = [
            op
            for op in doc["operations"].values()
            if op["category"] == "training" and op["binding"]["searches"] == ids
        ]
        if retained:
            if len(retained) != 1 or retained[0]["status"] != "settled":
                raise ValueError("Unknown training outcome; no second update is permitted")
            op = retained[0]
            if "started_at" not in op:
                raise ValueError("Group training did not start")
            expected = {
                "learning_rate": learning_rate,
                "expense_weight": 0.0,
                "elapsed_weight": 0.0,
                **training,
            }
            if (
                op["binding"]["snapshot"] != digest(snapshot.document())
                or op["binding"]["reference"] != digest(reference.document())
                or digest(op["binding"]["training"]) != digest(expected)
            ):
                raise ValueError("Frozen outer-loop training configuration changed")
            snapshot = snapshot.restore(op["receipt"]["checkpoint"])
        else:
            snapshot = train_group(
                control,
                campaign,
                records,
                snapshot,
                reference,
                cap_ms=training_cap_ms,
                learning_rate=learning_rate,
                **training,
            )
        if mode == "carry":
            best = min(
                (decode(record["tree"]) for record in records),
                key=lambda state: (-tree.verified_gain(state), state.contract.search_id),
            )
            selected = tree.accept(best)
            # Carry the complete selected artifact, retaining its actual receipts.
            selected = replace(selected, parent_id=None)
            root = tree.initialize(
                best.contract,
                selected,
                tree.evidence(best, selected.candidate_id).values(),
                dependencies=best.dependencies,
            )
    return snapshot


class _FutureAcceptanceVersion(ValueError):
    pass


@dataclass(frozen=True)
class FinalAcceptance:
    """Require all checks to pass and optionally a minimum score on the deployment objective."""

    minimum_objective: int | float | None = None

    def __post_init__(self):
        value = self.minimum_objective
        if value is not None and not self._finite_number(value):
            raise ValueError("Final acceptance minimum_objective must be a finite number")
        if type(value) is float and value.is_integer():
            object.__setattr__(self, "minimum_objective", int(value))

    @staticmethod
    def _finite_number(value):
        # Integers are exact. Converting a large integer to float can change the gate.
        return type(value) is int or (type(value) is float and math.isfinite(value))

    def document(self):
        return {"version": 1, "minimum_objective": self.minimum_objective}

    @classmethod
    def from_document(cls, raw):
        if type(raw) is dict and type(raw.get("version")) is int and raw["version"] > 1:
            raise _FutureAcceptanceVersion("Future final acceptance version is unsupported")
        if (
            type(raw) is not dict or set(raw) != {"version", "minimum_objective"}
            or type(raw["version"]) is not int or raw["version"] != 1
        ):
            raise ValueError("Missing or unsupported frozen final acceptance rule")
        return cls(raw["minimum_objective"])

    def accepts(self, results, objective_check):
        if not results or not all(r["verdict"] == "PASS" and r["cleanup_verified"] is True
                   for r in results.values()):
            return False
        if self.minimum_objective is None:
            return True
        value = results[objective_check].get("objective")
        return self._finite_number(value) and value >= self.minimum_objective


class _AmbiguousDeployment(ValueError):
    pass


def _deployment_winner(doc, adapter, selected, search_id):
    searches = doc["state"].get("searches", {})
    experiment = getattr(adapter.evaluator, "experiment_identity", None)
    if experiment is not None:
        histories = [
            op["binding"] for op in doc["operations"].values() if op["category"] == "root"
        ] + list(searches.values())
        if any(record.get("experiment_identity") != experiment for record in histories):
            raise ValueError("Final evaluator must match the frozen development experiment")

    eligible = {
        name: record for name, record in searches.items()
        if record.get("status") == "complete" and record.get("collect") is False
        and record.get("forced") is False and record.get("pending") is None
        and record.get("active_action") is None
    }
    if search_id is None:
        if len(eligible) > 1:
            raise _AmbiguousDeployment("Several completed deployment searches. "
                                       "Specify deployment_search for the selected winner.")
        search_id = next(iter(eligible), None)
    if search_id not in eligible:
        raise ValueError("Final requires a completed, natural deployment search")
    record = eligible[search_id]
    initial_conditions(record)
    state = decode(record["tree"])
    if state.contract.search_id != search_id:
        raise ValueError("Deployment search ID disagrees with its retained tree")
    if experiment is None:
        if record["adapter"] != adapter.identity:
            raise ValueError("Final adapter must match the deployment experiment")
    else:
        validate_development_evidence(state, {"experiment_identity": experiment})
    winner = tree.accept(state)
    if record["selected"] != winner.candidate_id:
        raise ValueError("Recorded deployment winner disagrees with the verified search result")
    if selected != winner and selected != replace(winner, parent_id=None):
        raise ValueError("Final candidate must be the winner of the selected deployment search")
    return state.contract


def finalize(
    control, campaign, adapter, selected, *, holdout_scope, acceptance=None, deployment_search=None,
    accept_result=None,
):
    """Freeze once; a failed/unknown holdout never reopens search or changes selection.

    deployment_search names the completed natural deployment that selected the candidate.
    A campaign with exactly one eligible deployment can omit the name. New claims require
    an explicit FinalAcceptance. Receipt recovery uses the rule in the original claim.
    """
    completed = control.read(campaign)["final_result"]
    if completed is not None:
        return completed
    with control.final_owner(campaign) as stored_campaign:
        return _finalize(
            control, campaign, adapter, selected, holdout_scope=holdout_scope,
            acceptance=acceptance, deployment_search=deployment_search, accept_result=accept_result,
            stored_campaign=stored_campaign,
        )


def _finalize(
    control, campaign, adapter, selected, *, holdout_scope, acceptance, deployment_search,
    accept_result, stored_campaign,
):
    # Re-read under the guard. Another finalizer may have finished since the read-only fast path.
    doc = control.read(campaign)
    if doc["final_result"] is not None:
        return doc["final_result"]
    if accept_result is not None:
        raise ValueError("Final acceptance callbacks cannot be frozen; supply FinalAcceptance")
    if acceptance is not None and type(acceptance) is not FinalAcceptance:
        raise ValueError("Final acceptance must be a FinalAcceptance rule")
    frozen = doc["final_claim"]
    recovering = frozen is not None
    checks = dict(adapter.checks)
    if not recovering and not checks:
        raise ValueError("Final acceptance requires a nonempty set of checks")
    binding = {
        "candidate": asdict(selected),
        "adapter": adapter.identity,
        "checks": checks,
        "scope": holdout_scope,
    }
    previous_search = None
    acceptance_error = None
    if recovering:
        # Reuse the original rule bytes in the binding, even when this version cannot
        # interpret them. That binding identifies the already launched physical checks.
        stored = frozen["binding"]
        if "final_owner" in stored:
            if stored["final_owner"] != control.FINAL_OWNER_PROTOCOL:
                raise ValueError("Unsupported final owner protocol")
            binding["final_owner"] = stored["final_owner"]
        for name in ("acceptance", "objective_check"):
            if name in stored:
                binding[name] = stored[name]
        try:
            rule = FinalAcceptance.from_document(binding.get("acceptance"))
            if rule.minimum_objective is not None:
                name = binding.get("objective_check")
                if type(name) is not str or name not in checks:
                    raise ValueError("Missing or unknown frozen final objective check")
            elif "objective_check" in binding:
                raise ValueError("Unexpected objective check for a score-free acceptance rule")
        except _FutureAcceptanceVersion:
            raise
        except ValueError as error:
            if acceptance is not None:
                raise ValueError("Cannot replace an unproven final acceptance rule") from error
            acceptance_error = str(error)
        else:
            if acceptance is not None and acceptance != rule:
                raise ValueError("Cannot change the frozen final acceptance rule")
        previous_search = frozen["binding"].get("deployment_search")
        if previous_search is not None:
            if deployment_search not in (None, previous_search):
                raise ValueError("Cannot change the frozen deployment search")
            binding["deployment_search"] = previous_search
        # Match the exact original inputs before inspecting receipts, including legacy keys.
        if digest(stored) != digest(binding):
            raise ValueError("Cannot change the final candidate or validation scope")
        # Binding equality authenticates membership. Keep the adapter's report order and
        # take each cap from the persisted claim (RunStore sorts JSON object keys).
        checks = {name: stored["checks"][name] for name in checks}
    else:
        if acceptance is None:
            raise ValueError("New final claims require an explicit FinalAcceptance rule")
        binding["final_owner"] = control.FINAL_OWNER_PROTOCOL
        binding["acceptance"] = acceptance.document()
        rule = FinalAcceptance.from_document(binding["acceptance"])

    # An incompatible retry must not even release an expired reservation. Once the
    # binding matches, recover reservations and use the resulting revision for the CAS.
    doc = control.recover_unstarted(campaign)
    if doc["final_result"] is not None:
        return doc["final_result"]
    if doc["final_claim"] != frozen:
        raise ValueError("Final claim changed; recover using its frozen binding")

    selection_error = None
    if acceptance_error is None:
        try:
            validate_final = getattr(adapter.evaluator, "validate_final", None)
            if validate_final is not None:
                validate_final(holdout_scope)
            required_scope = getattr(adapter.evaluator, "holdout_scope", None)
            if required_scope is not None and holdout_scope != required_scope:
                raise ValueError("Final scope must match the evaluator's frozen holdout identity")
            contract = _deployment_winner(
                doc, adapter, selected, previous_search or deployment_search
            )
            if not set(contract.checks).issubset(checks):
                raise ValueError("Final checks must include every required deployment check")
            if rule.minimum_objective is not None:
                if recovering and binding["objective_check"] != contract.objective_check:
                    raise ValueError("Frozen final objective check differs from deployment")
                binding["objective_check"] = contract.objective_check
        except _AmbiguousDeployment:
            raise
        except ValueError as error:
            if not recovering or (previous_search is None and deployment_search is not None):
                raise
            selection_error = str(error)
        if selection_error is None:
            try:
                # Authenticate the entire retained bundle before committing a fresh holdout claim.
                adapter.path(selected)
            except (ValueError, OSError) as error:
                if not recovering:
                    raise
                selection_error = str(error)
    accounting_only = acceptance_error is not None or selection_error is not None
    if not recovering:
        binding["deployment_search"] = contract.search_id
        control.claim_final(
            campaign, doc["revision"], holdout_scope, binding,
            previous_scope_prefix=getattr(adapter.evaluator, "previous_holdout_scope_prefix", None),
        )
    results = {}
    unreserved = set()
    operation_campaign = stored_campaign if "final_owner" in binding else campaign
    for check, cap in checks.items():
        doc = control.read(campaign)
        operation = "final-" + digest(
            {"campaign": operation_campaign, "binding": binding, "check": check}
        )
        if recovering:
            op = doc["operations"].get(operation)
            if op is None:
                # No claim means no launch intent or charge. Never call the adapter for it.
                # finish_final authenticates absence and legacy writer exclusion atomically.
                unreserved.add(check)
                results[check] = {
                    "check": check, "not_started": "unreserved", "verdict": "INCONCLUSIVE",
                    "objective": None, "elapsed_ms": 0, "cleanup_verified": True,
                }
                continue
            if op["status"] == "claimed":
                raise ValueError("Final reservation still awaits launch")
            if op["status"] == "settled":
                result = op["receipt"]
                if "started_at" not in op:
                    result = {
                        **result,
                        "verdict": "INCONCLUSIVE",
                        "objective": None,
                        "elapsed_ms": 0,
                        "cleanup_verified": True,
                    }
            else:
                recover = adapter.recover_accounting if accounting_only else adapter.recover
                result = recover(
                    operation,
                    {"kind": "verify", "final": True,
                     "binding": {"candidate": binding["candidate"], "check": check}},
                )
                if result is None:
                    raise ValueError("Unknown final execution; recover its receipt without rerun")
                control.settle(
                    campaign,
                    operation,
                    result,
                    actual_ms=result.get("elapsed_ms"),
                    cleanup_verified=result.get("cleanup_verified"),
                )
        else:
            control.claim(
                campaign,
                doc["revision"],
                operation,
                category="final",
                cap_ms=cap,
                domains=(adapter.domain,),
                binding=binding | {"check": check},
                final=True,
            )
            claim = control.launch(campaign, operation)
            result = adapter.verify(selected, check, operation, claim["deadline"])
            control.settle(
                campaign,
                operation,
                result,
                actual_ms=result.get("elapsed_ms"),
                cleanup_verified=result.get("cleanup_verified"),
            )
            if result.get("cleanup_verified") is not True or result.get("elapsed_ms") is None:
                raise ValueError("Unknown final usage or cleanup; recover the existing receipt")
        results[check] = result
    doc = control.read(campaign)
    unsettled = any(op["status"] != "settled" for op in doc["operations"].values())
    if unsettled:
        raise ValueError("Unknown final usage or cleanup; recover its receipt without rerun")
    complete = bool(checks) and results.keys() == checks.keys()
    passed = complete and not accounting_only and not doc["blocked"] and rule.accepts(
        results, binding.get("objective_check")
    )
    result = {
        "candidate": selected.candidate_id,
        "verdict": "PASS" if passed else "FAIL",
        "results": list(results.values()),
        "promoted": passed,
    }
    if selection_error is not None:
        result["selection_error"] = selection_error
    if acceptance_error is not None:
        result["acceptance_error"] = acceptance_error
    if not complete or accounting_only or doc["blocked"] or any(
        r["verdict"] == "INCONCLUSIVE" or r["cleanup_verified"] is not True
        for r in results.values()
    ):
        result.update(verdict="INCONCLUSIVE", promoted=False)
    control.finish_final(
        campaign,
        binding,
        result,
        unreserved=unreserved,
        transition=(lambda body: body | {"stable": asdict(selected)}) if passed else None,
    )
    return result
