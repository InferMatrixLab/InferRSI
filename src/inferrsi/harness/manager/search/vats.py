"""Bounded synchronous VATS over immutable candidates and injected real operations.

The controller owns search transitions; WorkControl owns persistent claims and
accounting; the adapter owns permitted edits and authenticated real observations.
No value prediction is admitted as evidence. There is no background re-dispatch.
"""

import math
import random
import time
import uuid
from dataclasses import asdict, dataclass, replace
from itertools import combinations

from inferrsi.harness.records.artifact_primitives import digest

from . import search_tree as tree
from .search_adapter import development_binding, validate_development_evidence
from .search_records import decode, encode, initial_conditions
from .verification_plans import completion_menu


@dataclass(frozen=True)
class Settings:
    max_steps: int
    max_parents: int
    draft_depth: int
    max_targets: int
    max_jobs: int
    max_plans: int
    preparation_ms: int
    draft_ms: int
    search_ms: int
    refine_queries: int = 0
    temperature: float = 1.0
    exploration: float = 0.1
    draft_ahead: bool = True
    bundled: bool = True

    def __post_init__(self):
        for key in (
            "max_steps",
            "max_parents",
            "draft_depth",
            "max_targets",
            "max_jobs",
            "max_plans",
            "preparation_ms",
            "draft_ms",
            "search_ms",
        ):
            if type(getattr(self, key)) is not int or getattr(self, key) <= 0:
                raise ValueError("VATS bounds must be positive integers")
        if type(self.refine_queries) is not int or self.refine_queries < 0:
            raise ValueError("Invalid Scorer query cap")
        if not math.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("Invalid policy temperature")
        if not 0 <= self.exploration < 1:
            raise ValueError("Invalid policy exploration")


@dataclass(frozen=True)
class Action:
    kind: str
    parents: tuple[str, ...] = ()
    depth: int = 0
    jobs: tuple[str, ...] = ()
    cost_ms: int = 0

    @property
    def key(self):
        return digest(asdict(self))


def depth(state, node):
    result = 0
    while node.parent_id is not None:
        result += 1
        node = tree.candidate(state, node.parent_id)
    return result


def decision_count(record):
    """Include the natural prefix omitted from a forced continuation's trace."""
    return record.get("continuation", {}).get("step", 0) + len(record["trace"])


def features(state, action, available, settings):
    """Fixed public features; ACCEPT has a fixed zero Policy logit."""
    if action.kind == "accept":
        return (0.0,) * 8
    return (
        1.0,
        float(action.kind == "draft"),
        float(action.kind == "verify"),
        action.cost_ms / settings.search_ms,
        len(state.candidates) / state.contract.max_candidates,
        available / settings.search_ms,
        action.depth / state.contract.max_depth,
        len(action.jobs) / settings.max_jobs,
    )


def menu(state, jobs, available, settings, snapshot):
    """Preserve singleton completion seeds before optionally refining their unions."""
    available = min(available, settings.search_ms)
    plans = completion_menu(
        state,
        jobs,
        available_budget=max(0, available),
        available_jobs=settings.max_jobs,
        max_targets=settings.max_targets,
        max_jobs=settings.max_jobs,
    )
    singleton_plans = completion_menu(
        state,
        jobs,
        available_budget=max(0, available),
        available_jobs=settings.max_jobs,
        max_targets=1,
        max_jobs=settings.max_jobs,
    )
    seeds = [Action("verify", jobs=plan.job_ids, cost_ms=plan.cost) for plan in singleton_plans]
    unions = [Action("verify", jobs=plan.job_ids, cost_ms=plan.cost) for plan in plans]
    allowed = {frozenset(a.jobs): a for a in unions}
    # Refine priority among feasible bounded unions without evicting completion
    # seeds or bypassing Solver's frozen target/job/cost/attempt constraints.
    by_job = {job.job_id: job for job in jobs}
    queries = 0
    extra = []
    for left, right in combinations(seeds, 2):
        if queries + 2 > settings.refine_queries:
            break
        union = tuple(dict.fromkeys((*left.jobs, *right.jobs)))
        if frozenset(union) not in allowed:
            continue
        cost = sum(by_job[jid].cost for jid in union)
        attempts = sum(by_job[jid].candidate_id is not None for jid in union)
        if (
            cost > available
            or len(union) > settings.max_jobs
            or attempts + len(state.attempts) > state.contract.max_attempts
            or any(set(by_job[jid].conflicts) & set(union) for jid in union)
        ):
            continue
        trial = allowed[frozenset(union)]
        queries += 2
        if snapshot.predict(features(state, trial, available, settings)) > snapshot.predict(
            features(state, left, available, settings)
        ):
            extra.append(trial)
    if not settings.bundled:
        # Ablation: individual executable jobs, explicitly retaining incomplete evidence.
        seeds = [
            Action("verify", jobs=(job.job_id,), cost_ms=job.cost)
            for job in jobs
            if not job.prerequisites
            and job.cost <= available
            and job.candidate_id is not None
            and job.check_id in tree.missing_checks(state, job.candidate_id)
        ]
        extra = []
        unions = []
    parents = [
        node
        for node in state.candidates
        if tree.candidate_valid(state, node.candidate_id)
        and (settings.draft_ahead or node in tree.complete_candidates(state))
    ]
    drafts = []
    slots = state.contract.max_candidates - len(state.candidates)
    for count in range(1, min(len(parents), settings.max_parents) + 1):
        for selected in combinations(parents, count):
            for height in range(1, settings.draft_depth + 1):
                cost = count * height * settings.draft_ms
                if (
                    cost <= available
                    and count * height <= slots
                    and all(
                        depth(state, node) + height <= state.contract.max_depth for node in selected
                    )
                ):
                    drafts.append(
                        Action(
                            "draft",
                            tuple(node.candidate_id for node in selected),
                            height,
                            cost_ms=cost,
                        )
                    )
                if len(drafts) >= settings.max_plans:
                    break
            if len(drafts) >= settings.max_plans:
                break
        if len(drafts) >= settings.max_plans:
            break
    required = [Action("accept"), *seeds]
    if len(required) > settings.max_plans:
        raise ValueError("Menu cap cannot preserve all feasible completion seeds")
    unique = {action.key: action for action in required}
    for action in (*extra, *drafts, *unions):
        if len(unique) >= settings.max_plans:
            break
        unique[action.key] = action
    return tuple(unique.values())


class Search:
    """A resumable search bound to one immutable role snapshot and adapter contract.

    Adapter methods: jobs(tree), draft(parent, choice_context, snapshot, rng,
    destination, deadline), verify(node, check, destination, deadline), recover(...).
    Draft returns (Candidate, Choice|None, receipt); verify returns Receipt facts.
    Both return authenticated elapsed_ms and cleanup_verified in their receipt.
    """

    def __init__(self, control, campaign, search_id, snapshot, settings, adapter):
        self.experiment = development_binding(adapter)
        self.control, self.campaign, self.search_id = control, campaign, search_id
        self.snapshot, self.settings, self.adapter = snapshot, settings, adapter
        self.snapshot_id = digest(snapshot.document())
        self.settings_id = digest(asdict(settings))

    def read(self):
        document = self.control.read(self.campaign)
        search = document["state"]["searches"][self.search_id]
        initial_conditions(search)
        if (
            search["snapshot"] != self.snapshot_id
            or search["settings"] != self.settings_id
            or search["adapter"] != self.adapter.identity
            or search.get("experiment_identity") != self.experiment.get("experiment_identity")
        ):
            raise ValueError("Frozen search roles, menu or adapter changed")
        return document, search, decode(search["tree"])

    def start(self, initial, *, seed, collect=True, forced=False):
        if (
            initial.contract.search_id != self.search_id
            or initial.contract.improver_snapshot != self.snapshot_id
        ):
            raise ValueError("Search root must bind the frozen search and improver")
        validate_development_evidence(initial, self.experiment)
        tree.accept(initial)
        if not forced and len(initial.candidates) != 1:
            raise ValueError("Independent natural searches must start from one qualified root")

        def observation(attempt):
            return {
                key: value
                for key, value in encode(attempt).items()
                if key not in ("attempt_id", "search_id")
            }

        initial_conditions = digest(
            {
                "candidates": [asdict(node) for node in initial.candidates],
                "dependencies": [asdict(item) for item in initial.dependencies],
                "attempts": [observation(a) for a in initial.attempts],
                "receipts": [
                    {**encode(r), "attempt": observation(r.attempt)} for r in initial.receipts
                ],
            }
        )
        doc = self.control.read(self.campaign)

        def transition(state):
            if self.search_id in state["searches"]:
                raise ValueError("Search already exists; resume it")
            state["searches"][self.search_id] = {
                "tree": encode(initial),
                "snapshot": self.snapshot_id,
                "settings": self.settings_id,
                "adapter": self.adapter.identity,
                **self.experiment,
                "seed": seed,
                "collect": collect,
                "forced": forced,
                "trace": [],
                "status": "active",
                "pending": None,
                "spent_ms": 0,
                "started_at": time.time(),
                "elapsed_ms": 0,
                "draft_attempts": 0,
                "active_action": None,
                "initial_gain": tree.verified_gain(initial),
                "initial_conditions": initial_conditions,
                "selected": initial.root_id,
            }
            return state

        self.control.update(self.campaign, doc["revision"], transition)

    def _change(self, state, operation, result):
        search = state["searches"][self.search_id]
        pending = search["pending"]
        if pending is None or pending["operation"] != operation:
            raise ValueError("Late result does not match the active work identity")
        current = decode(search["tree"])
        if pending["kind"] == "draft":
            search["draft_attempts"] += 1
            if result.get("candidate") is not None:
                raw = result["candidate"]
                node = tree.Candidate(
                    **(
                        raw
                        | {
                            "producer": tree.Producer(**raw["producer"]),
                            "dependencies": tuple(
                                tree.Dependency(**d) for d in raw["dependencies"]
                            ),
                        }
                    )
                )
                try:
                    tree.accept(current)
                    root_valid = True
                except ValueError:
                    root_valid = False
                if root_valid and tree.candidate_valid(current, node.parent_id):
                    current = tree.add_candidate(current, node, expected_revision=current.revision)
                else:
                    search.setdefault("rejected_drafts", []).append(operation)
        else:
            bound = next(a for a in current.attempts if a.attempt_id == operation)
            from inferrsi.contracts.claim import Verdict

            receipt = tree.Receipt(
                bound,
                Verdict(result["verdict"]),
                result["evidence_digest"],
                result.get("objective"),
            )
            current = tree.record_receipt(current, receipt, expected_revision=current.revision)
        search["tree"] = encode(current)
        if tree.complete_candidates(current) and tree.evidence(current, current.root_id):
            try:
                search["selected"] = tree.accept(current).candidate_id
            except ValueError:
                search.update(status="blocked", selected=None)
        else:
            search.update(status="blocked", selected=None)
        search["spent_ms"] += result["elapsed_ms"]
        search["pending"] = None
        active = search["active_action"]
        if active is not None:
            active["cursor"] += 1
            if pending["kind"] == "draft":
                active["last_child"] = (
                    result["candidate"]["candidate_id"]
                    if result.get("candidate")
                    and any(
                        n.candidate_id == result["candidate"]["candidate_id"]
                        for n in current.candidates
                    )
                    else None
                )
        if result.get("choice") is not None:
            search["trace"][-1]["draft_choices"].append(result["choice"])
        return state

    def invalidate(self, dependency):
        """Persist invalidation and incumbent replacement before any cancellation.

        In-flight work remains charged to its original claim; late receipts can
        still be archived by recover(), but can never revive invalid evidence.
        """
        doc, _, _ = self.read()

        def transition(state):
            record = state["searches"][self.search_id]
            current = decode(record["tree"])
            current = tree.invalidate(current, dependency, expected_revision=current.revision)
            record["tree"] = encode(current)
            try:
                record["selected"] = tree.accept(current).candidate_id
            except ValueError:
                record.update(status="blocked", selected=None)
            record.setdefault("invalidations", []).append(dependency)
            return state

        self.control.update(self.campaign, doc["revision"], transition)

    def recover(self):
        self.control.recover_unstarted(self.campaign)
        doc, search, _ = self.read()
        pending = search["pending"]
        if pending is None:
            return
        operation = doc["operations"][pending["operation"]]
        not_started = operation["status"] == "settled" and "started_at" not in operation
        if operation["status"] == "settled" and (not_started or doc["blocked"]):
            # The durable control record is conclusive. Unstarted work has no
            # adapter receipt, and blocked work cannot contribute its output.
            # Close the Attempt with control-only INCONCLUSIVE evidence.
            def archive(state):
                from inferrsi.contracts.claim import Verdict

                record = state["searches"][self.search_id]
                current = decode(record["tree"])
                if pending["kind"] == "verify":
                    bound = next(
                        a for a in current.attempts if a.attempt_id == pending["operation"]
                    )
                    current = tree.record_receipt(
                        current,
                        tree.Receipt(bound, Verdict.INCONCLUSIVE, digest(operation)),
                        expected_revision=current.revision,
                    )
                record.update(
                    tree=encode(current),
                    pending=None,
                    active_action=None,
                    block_stop_reason="campaign_blocked" if doc["blocked"] else "launch_deadline",
                )
                if doc["blocked"]:
                    record["spent_ms"] += operation["actual_ms"]
                    record.setdefault("discarded_operations", []).append(pending["operation"])
                    record["status"] = "blocked"
                    if pending["kind"] == "draft" and not not_started:
                        record["draft_attempts"] += 1
                try:
                    record["selected"] = tree.accept(current).candidate_id
                except ValueError:
                    record.update(status="blocked", selected=None)
                return state

            if doc["blocked"]:
                self.control.reconcile_blocked(
                    self.campaign, doc["revision"], pending["operation"], archive
                )
            else:
                self.control.update(self.campaign, doc["revision"], archive)
            return
        if operation["status"] == "claimed":
            raise ValueError("Unstarted reservation still awaits launch")
        # All uncertain launches still require an adapter receipt. Never call
        # draft/verify from recovery, including after launch-intent crashes.
        result = self.adapter.recover(pending["operation"], pending)
        if result is None:
            raise ValueError("Unknown execution: retain reservation and do not relaunch")
        self.control.settle(
            self.campaign,
            pending["operation"],
            result,
            actual_ms=result.get("elapsed_ms"),
            cleanup_verified=result.get("cleanup_verified"),
            transition=lambda state: self._change(state, pending["operation"], result),
        )
        settled = self.control.read(self.campaign)
        if (settled["blocked"]
                and settled["operations"][pending["operation"]]["status"] == "settled"):
            self.recover()

    def _execute(self, kind, node, check=None):
        doc, search, current = self.read()
        operation = self.search_id + "-" + uuid.uuid4().hex
        cap = self.settings.draft_ms if kind == "draft" else check.cost
        binding = {
            "search": self.search_id,
            "candidate": asdict(node),
            "check": check.check_id if check else None,
            "snapshot": self.snapshot_id,
            "adapter": self.adapter.identity,
        }

        def pending(state):
            search = state["searches"][self.search_id]
            current = decode(search["tree"])
            if search["pending"] is not None:
                raise ValueError("An operation is already pending")
            if kind == "verify":
                attempt = tree.Attempt(
                    operation,
                    operation,
                    operation,
                    operation,
                    self.search_id,
                    node.candidate_id,
                    node.artifact_digest,
                    check.check_id,
                    current.contract.context,
                    node.dependencies,
                    **self.experiment,
                )
                current = tree.register_attempt(
                    current, attempt, expected_revision=current.revision
                )
                search["tree"] = encode(current)
            search["pending"] = {"operation": operation, "kind": kind, "binding": binding}
            return state

        self.control.claim(
            self.campaign,
            doc["revision"],
            operation,
            category=kind,
            cap_ms=cap,
            binding=binding,
            domains=self.adapter.domains(kind, node, check),
            transition=pending,
        )
        claim = self.control.launch(self.campaign, operation)
        # Any exception retains the claim. The adapter's authenticated receipt is
        # the only recovery route, including when writing the state below fails.
        if kind == "draft":
            rng = random.Random(
                f"{search['seed']}:{len(current.candidates)}:{decision_count(search)}"
            )
            result = self.adapter.draft(
                node, current, self.snapshot, rng, operation, claim["deadline"]
            )
        else:
            result = self.adapter.verify(node, check.check_id, operation, claim["deadline"])
        self.control.settle(
            self.campaign,
            operation,
            result,
            actual_ms=result.get("elapsed_ms"),
            cleanup_verified=result.get("cleanup_verified"),
            transition=lambda state: self._change(state, operation, result),
        )
        _, updated, _ = self.read()
        if updated["pending"] is not None:
            raise ValueError("Execution or cleanup remains unknown")
        return result

    def run(self, *, forced_action=None):
        self.recover()
        while True:
            doc, search, current = self.read()
            if search["status"] == "complete":
                return search
            if doc["blocked"] or doc["final_claim"] is not None:
                raise ValueError("Campaign blocked or final selection frozen")
            if search["status"] == "blocked":
                raise ValueError("Search root evidence is invalid; search remains blocked")
            if any(
                op["status"] != "settled" and op["binding"].get("search") == self.search_id
                for op in doc["operations"].values()
            ):
                raise ValueError("Unresolved claim: recover without relaunch")
            if search["trace"] and search["trace"][-1]["action"]["kind"] == "accept":
                # Preparation/copy already committed this terminal decision.
                # A crash before finish must not sample or pay for another action.
                return self.finish("forced_accept" if search["trace"][-1]["forced"] else "accept")
            if search["active_action"] is not None:
                self._continue_action()
                continue
            remaining = min(
                self.control.available(doc), self.settings.search_ms - search["spent_ms"]
            )
            attempts_left = (
                current.contract.max_attempts - len(current.attempts) - search["draft_attempts"]
            )
            if (
                decision_count(search) >= self.settings.max_steps
                or attempts_left <= 0
                or remaining <= self.settings.preparation_ms
                or time.time() >= doc["deadline"]
            ):
                return self.finish("limit")
            op = self.search_id + "-prepare-" + uuid.uuid4().hex
            self.control.claim(
                self.campaign,
                doc["revision"],
                op,
                category="preparation",
                cap_ms=self.settings.preparation_ms,
                binding={"search": self.search_id},
            )
            claim = self.control.launch(self.campaign, op)
            started = time.monotonic()
            jobs = self.adapter.jobs(current)
            planning_state = replace(
                current,
                contract=replace(
                    current.contract,
                    max_attempts=current.contract.max_attempts - search["draft_attempts"],
                ),
            )
            actions = menu(
                planning_state,
                jobs,
                remaining - self.settings.preparation_ms,
                self.settings,
                self.snapshot,
            )
            actions = tuple(
                a for a in actions if a.kind != "draft" or len(a.parents) * a.depth <= attempts_left
            )
            vectors = tuple(
                features(current, action, remaining, self.settings) for action in actions
            )
            rng = random.Random(f"{search['seed']}:policy:{decision_count(search)}")
            choice = self.snapshot.choose(
                "policy",
                [action.key for action in actions],
                vectors,
                rng=rng,
                context=digest(encode(current)),
                collect=search["collect"],
                temperature=self.settings.temperature,
                exploration=self.settings.exploration if search["collect"] else 0,
            )
            selected = choice.selected
            forced = forced_action is not None and not search["trace"]
            if forced:
                if not search["forced"]:
                    raise ValueError("Forced continuation must be isolated from actor training")
                selected = next(
                    i for i, action in enumerate(actions) if action.key == forced_action
                )
            action = actions[selected]
            elapsed = max(1, math.ceil((time.monotonic() - started) * 1000))

            def prepared(state):
                record = state["searches"][self.search_id]
                record["spent_ms"] += elapsed
                record["trace"].append(
                    {
                        "action": asdict(action),
                        "choice": asdict(choice),
                        "forced": forced,
                        "features": vectors[selected],
                        "draft_choices": [],
                        "gain_before": tree.verified_gain(current),
                        "spent_before": record["spent_ms"],
                        "at": time.time(),
                        "paid_state": encode(current),
                        "menu": [asdict(a) for a in actions],
                        "vectors": vectors,
                        "jobs": [asdict(job) for job in jobs],
                        "draft_attempts": record["draft_attempts"],
                    }
                )
                if action.kind != "accept":
                    record["active_action"] = {
                        "action": asdict(action),
                        "cursor": 0,
                        "last_child": None,
                        "jobs": [asdict(job) for job in jobs],
                    }
                return state

            self.control.settle(
                self.campaign,
                op,
                {"menu": [asdict(a) for a in actions], "elapsed_ms": elapsed},
                actual_ms=elapsed,
                cleanup_verified=True,
                transition=prepared,
            )
            if time.time() >= claim["deadline"]:
                raise ValueError("Preparation deadline exceeded")
            if action.kind == "accept":
                return self.finish("accept")

    def _continue_action(self):
        from .verification_plans import Job

        while True:
            doc, search, current = self.read()
            active = search["active_action"]
            action = Action(**active["action"])
            cursor = active["cursor"]
            limit = (
                len(action.parents) * action.depth if action.kind == "draft" else len(action.jobs)
            )
            if cursor >= limit:

                def done(state):
                    state["searches"][self.search_id]["active_action"] = None
                    return state

                self.control.update(self.campaign, doc["revision"], done)
                return
            next_cap = (
                self.settings.draft_ms
                if action.kind == "draft"
                else next(
                    job["cost"] for job in active["jobs"] if job["job_id"] == action.jobs[cursor]
                )
            )
            if (
                time.time() >= doc["deadline"]
                or next_cap > self.control.available(doc)
                or next_cap > self.settings.search_ms - search["spent_ms"]
            ):

                def exhausted(state):
                    record = state["searches"][self.search_id]
                    record["active_action"] = None
                    record["block_stop_reason"] = "budget_or_deadline"
                    return state

                self.control.update(self.campaign, doc["revision"], exhausted)
                return
            if action.kind == "draft":
                branch, level = divmod(cursor, action.depth)
                if level and active["last_child"] is None:

                    def skip(state):
                        state["searches"][self.search_id]["active_action"]["cursor"] = (
                            branch + 1
                        ) * action.depth
                        return state

                    self.control.update(self.campaign, doc["revision"], skip)
                    continue
                parent = active["last_child"] if level else action.parents[branch]
                self._execute("draft", tree.candidate(current, parent))
            else:
                by_id = {raw["job_id"]: Job(**raw) for raw in active["jobs"]}
                job = by_id[action.jobs[cursor]]
                if job.candidate_id is None:
                    raise ValueError("Adapter must package shared setup into its real check")
                self._execute("verify", tree.candidate(current, job.candidate_id), job)

    def finish(self, reason):
        doc, search, current = self.read()
        if search["pending"] is not None:
            raise ValueError("Cannot accept unsettled work")
        if search["active_action"] is not None:
            raise ValueError("Cannot accept an unfinished bounded work block")
        if any(
            op["status"] != "settled" and op["binding"].get("search") == self.search_id
            for op in doc["operations"].values()
        ):
            raise ValueError("Cannot accept an unresolved claim")

        def transition(state):
            record = state["searches"][self.search_id]
            record.update(
                status="complete",
                stop_reason=reason,
                selected=tree.accept(current).candidate_id,
                gain=tree.verified_gain(current),
                elapsed_ms=max(1, math.ceil((time.time() - record["started_at"]) * 1000)),
            )
            return state

        self.control.update(self.campaign, doc["revision"], transition)
        return self.read()[1]
