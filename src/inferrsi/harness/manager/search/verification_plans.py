"""Bounded exact completion-menu construction for offline VATS controls.

Costs are caller-supplied conservative integer bounds in one declared unit. A plan
is a proposal against a budget view, never a resource reservation or execution grant.
"""

from dataclasses import dataclass
from itertools import combinations

from inferrsi.contracts.claim import Verdict

from .search_tree import accept, candidate_valid, evidence, missing_checks


@dataclass(frozen=True)
class Job:
    job_id: str
    cost: int
    candidate_id: str | None = None
    check_id: str | None = None
    prerequisites: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.job_id, str) or not self.job_id.strip():
            raise ValueError("Job identity must be nonempty")
        if type(self.cost) is not int or self.cost <= 0:
            raise ValueError("Job cost must be a known positive integer upper bound")
        if (self.candidate_id is None) != (self.check_id is None):
            raise ValueError("A check job needs both candidate and check identities")
        for value in (self.candidate_id, self.check_id):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("Check identity must be nonempty")
        for name in ("prerequisites", "conflicts"):
            if not isinstance(getattr(self, name), (tuple, list)):
                raise ValueError("Job relations must be ordered sequences")
            values = tuple(getattr(self, name))
            if (any(not isinstance(value, str) or not value.strip() for value in values)
                    or len(set(values)) != len(values) or self.job_id in values):
                raise ValueError("Job relations must be unique, nonempty, non-self identities")
            object.__setattr__(self, name, values)


@dataclass(frozen=True)
class Plan:
    candidate_ids: tuple[str, ...]
    job_ids: tuple[str, ...]
    cost: int
    search_id: str
    state_revision: int


def completion_menu(state, jobs, *, available_budget, available_jobs, max_targets, max_jobs):
    """Enumerate unions of up to max_targets completion seeds, retaining every feasible seed.

The caller must settle a synchronous work block first. Preparation jobs have no
candidate/check pair. Shared prerequisites are charged once per proposed plan;
conflicts prohibit co-scheduling even when only one side declares the relation.
"""
    for value, minimum in ((available_budget, 0), (available_jobs, 0),
                           (max_targets, 1), (max_jobs, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError("Menu limits and available budget must be known integers")
    accept(state)
    receipts = {item.attempt.attempt_id for item in state.receipts}
    # An invalidated in-flight job is still real work; only its owner can settle it.
    if any(item.attempt_id not in receipts for item in state.attempts):
        raise ValueError("Settle the current work block before constructing another menu")
    jobs = tuple(jobs)
    if len(jobs) > max_jobs:
        raise ValueError("Job menu exceeds the declared enumeration bound")
    by_id = {job.job_id: job for job in jobs}
    if len(by_id) != len(jobs):
        raise ValueError("Duplicate job identity")
    checks = {}
    for job in jobs:
        if (set(job.prerequisites) | set(job.conflicts)) - by_id.keys():
            raise ValueError("Unknown job relation")
        if job.candidate_id is not None:
            candidate_valid(state, job.candidate_id)  # Reject unknown candidate IDs.
            if job.check_id not in state.contract.checks:
                raise ValueError("Unknown required check")
            pair = (job.candidate_id, job.check_id)
            if pair in checks:
                raise ValueError("Ambiguous jobs for one candidate check")
            checks[pair] = job.job_id

    closures = {}

    def closure(job_id, visiting=frozenset()):
        if job_id in visiting:
            raise ValueError("Cyclic job prerequisites")
        if job_id not in closures:
            result = {job_id}
            for parent in by_id[job_id].prerequisites:
                result.update(closure(parent, visiting | {job_id}))
            closures[job_id] = frozenset(result)
        return closures[job_id]

    for job in jobs:
        closure(job.job_id)

    seeds = {}
    for node in state.candidates:
        cid = node.candidate_id
        if not candidate_valid(state, cid) or any(
            item.verdict == Verdict.FAIL for item in evidence(state, cid).values()
        ):
            continue
        missing = missing_checks(state, cid)
        if not missing or any((cid, check) not in checks for check in missing):
            continue
        seeds[cid] = frozenset().union(*(closure(checks[(cid, check)]) for check in missing))

    plans = {}
    remaining_attempts = state.contract.max_attempts - len(state.attempts)
    for size in range(1, min(max_targets, len(seeds)) + 1):
        for targets in combinations(sorted(seeds), size):
            union = frozenset().union(*(seeds[cid] for cid in targets))
            if len(union) > available_jobs:
                continue
            check_jobs = [by_id[jid] for jid in union if by_id[jid].candidate_id is not None]
            if len(check_jobs) > remaining_attempts:
                continue
            # A cross-candidate prerequisite must itself be a legal outstanding check.
            if any(job.check_id not in missing_checks(state, job.candidate_id)
                   or not candidate_valid(state, job.candidate_id) for job in check_jobs):
                continue
            if any(set(by_id[jid].conflicts) & union for jid in union):
                continue
            cost = sum(by_id[jid].cost for jid in union)
            if cost > available_budget:
                continue
            # Stable topological order, so an adapter never receives a child before setup.
            ordered = []
            remaining = set(union)
            while remaining:
                ready = sorted(jid for jid in remaining
                               if not (set(by_id[jid].prerequisites) & remaining))
                ordered.extend(ready)
                remaining.difference_update(ready)
            completed = tuple(sorted(cid for cid, seed in seeds.items() if seed <= union))
            plan = Plan(completed, tuple(ordered), cost, state.contract.search_id, state.revision)
            plans[plan.job_ids] = plan
    return tuple(sorted(plans.values(), key=lambda plan: (plan.cost, plan.job_ids)))
