"""Campaign assembly: real root acquisition, independent searches, GVO and final gating."""

import time
from dataclasses import asdict, replace

from inferrsi.contracts.claim import Verdict

from . import search_tree as tree
from .artifact_primitives import digest
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
    return search_id


def finalize(
    control, campaign, adapter, selected, *, holdout_scope, accept_result, deployment_search=None
):
    """Freeze once; a failed/unknown holdout never reopens search or changes selection.

    deployment_search names the completed natural deployment that selected the candidate.
    A campaign with exactly one eligible deployment can omit the name. accept_result is
    the fixed independent final gate.
    """
    doc = control.recover_unstarted(campaign)
    if doc["final_result"] is not None:
        return doc["final_result"]
    frozen = doc["final_claim"]
    recovering = frozen is not None
    binding = {
        "candidate": asdict(selected),
        "adapter": adapter.identity,
        "checks": adapter.checks,
        "scope": holdout_scope,
    }
    previous_search = None
    if recovering:
        previous_search = frozen["binding"].get("deployment_search")
        if previous_search is not None:
            if deployment_search not in (None, previous_search):
                raise ValueError("Cannot change the frozen deployment search")
            binding["deployment_search"] = previous_search
        # Match the exact original inputs before inspecting receipts, including legacy keys.
        if digest(frozen["binding"]) != digest(binding):
            raise ValueError("Cannot change the final candidate or validation scope")

    selection_error = None
    try:
        validate_final = getattr(adapter.evaluator, "validate_final", None)
        if validate_final is not None:
            validate_final(holdout_scope)
        required_scope = getattr(adapter.evaluator, "holdout_scope", None)
        if required_scope is not None and holdout_scope != required_scope:
            raise ValueError("Final scope must match the evaluator's frozen holdout data identity")
        search_id = _deployment_winner(doc, adapter, selected, previous_search or deployment_search)
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
    if not recovering:
        binding["deployment_search"] = search_id
        control.claim_final(
            campaign, doc["revision"], holdout_scope, binding,
            previous_scope_prefix=getattr(adapter.evaluator, "previous_holdout_scope_prefix", None),
        )
    results = []
    for check, cap in adapter.checks.items():
        doc = control.read(campaign)
        operation = "final-" + digest({"campaign": campaign, "binding": binding, "check": check})
        if recovering:
            op = doc["operations"].get(operation)
            if op is None:
                if selection_error is not None:
                    continue  # No reservation or launch to reconcile; never dispatch it.
                raise ValueError("Interrupted holdout may be consumed; no new execution")
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
                recover = adapter.recover if selection_error is None else adapter.recover_accounting
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
        results.append(result)
    doc = control.read(campaign)
    unsettled = any(op["status"] != "settled" for op in doc["operations"].values())
    if selection_error is not None and unsettled:
        raise ValueError("Unknown final usage or cleanup; recover its receipt without rerun")
    unresolved = doc["blocked"] or unsettled
    passed = (
        selection_error is None
        and not unresolved
        and all(r["verdict"] == "PASS" and r["cleanup_verified"] is True for r in results)
        and accept_result(results)
    )
    result = {
        "candidate": selected.candidate_id,
        "verdict": "PASS" if passed else "FAIL",
        "results": results,
        "promoted": passed,
    }
    if selection_error is not None:
        result["selection_error"] = selection_error
    if selection_error is not None or unresolved or any(
        r["verdict"] == "INCONCLUSIVE" or r["cleanup_verified"] is not True for r in results
    ):
        result.update(verdict="INCONCLUSIVE", promoted=False)
    control.finish_final(
        campaign,
        binding,
        result,
        transition=(lambda body: body | {"stable": asdict(selected)}) if passed else None,
    )
    return result
