"""Pure VATS candidate/evidence transitions; execution and durable CAS belong to the caller.

Inputs are trusted controller records, not authenticated executor messages. This module
neither starts work nor grants a claim, releases a lease, spends budget or promotes a
production version. See docs/speculative-search.md for the adapter boundary.
"""

from dataclasses import dataclass, fields, replace
from math import isfinite

from inferrsi.contracts.claim import Verdict


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identity must be a nonempty string")


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Expected a bounded nonnegative integer")


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or set(value) - set("0123456789abcdef"):
        raise ValueError("Expected a lowercase SHA-256 digest")


@dataclass(frozen=True)
class Context:
    contract: str
    plan: str
    validator: str
    environment: str
    workload: str
    baseline: str
    quality_reference: str

    def __post_init__(self):
        for field in fields(self):
            _text(getattr(self, field.name))


@dataclass(frozen=True, order=True)
class Dependency:
    key: str
    epoch: int

    def __post_init__(self):
        _text(self.key)
        _integer(self.epoch)


def _dependencies(values):
    values = tuple(values)
    if any(not isinstance(value, Dependency) for value in values):
        raise ValueError("Expected dependency identities")
    if len({value.key for value in values}) != len(values):
        raise ValueError("Duplicate dependency key")
    return tuple(sorted(values))


@dataclass(frozen=True)
class Producer:
    snapshot: str
    revision: str
    context_digest: str
    history_digest: str

    def __post_init__(self):
        _text(self.snapshot)
        _text(self.revision)
        _sha(self.context_digest)
        _sha(self.history_digest)


@dataclass(frozen=True)
class Contract:
    search_id: str
    context: Context
    improver_snapshot: str
    checks: tuple[str, ...]
    objective_check: str
    direction: str
    max_candidates: int
    max_depth: int
    max_attempts: int

    def __post_init__(self):
        _text(self.search_id)
        _text(self.improver_snapshot)
        if not isinstance(self.context, Context):
            raise ValueError("Expected verification context")
        if not isinstance(self.checks, (tuple, list)):
            raise ValueError("Required checks must be an ordered sequence")
        checks = tuple(self.checks)
        for check in checks:
            _text(check)
        if not checks or len(set(checks)) != len(checks) or self.objective_check not in checks:
            raise ValueError("Required checks must be unique and include the objective")
        object.__setattr__(self, "checks", checks)
        if self.direction not in ("maximize", "minimize"):
            raise ValueError("Unknown objective direction")
        for value in (self.max_candidates, self.max_depth, self.max_attempts):
            _integer(value, 1)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    artifact_digest: str
    parent_id: str | None
    producer: Producer
    dependencies: tuple[Dependency, ...] = ()

    def __post_init__(self):
        _text(self.candidate_id)
        _sha(self.artifact_digest)
        if self.parent_id is not None:
            _text(self.parent_id)
        if not isinstance(self.producer, Producer):
            raise ValueError("Expected producer identity")
        object.__setattr__(self, "dependencies", _dependencies(self.dependencies))


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    execution_key: str
    reservation_id: str
    lease_id: str
    search_id: str
    candidate_id: str
    artifact_digest: str
    check_id: str
    context: Context
    dependencies: tuple[Dependency, ...] = ()
    experiment_identity: str | None = None

    def __post_init__(self):
        for name in ("attempt_id", "execution_key", "reservation_id", "lease_id", "search_id",
                     "candidate_id", "check_id"):
            _text(getattr(self, name))
        if self.experiment_identity is not None:
            _text(self.experiment_identity)
        _sha(self.artifact_digest)
        if not isinstance(self.context, Context):
            raise ValueError("Expected verification context")
        object.__setattr__(self, "dependencies", _dependencies(self.dependencies))


@dataclass(frozen=True)
class Receipt:
    attempt: Attempt
    verdict: Verdict
    evidence_digest: str
    objective: float | None = None

    def __post_init__(self):
        if not isinstance(self.attempt, Attempt) or not isinstance(self.verdict, Verdict):
            raise ValueError("Expected bound attempt and verdict")
        _sha(self.evidence_digest)
        if self.objective is not None and (
            type(self.objective) not in (int, float) or not isfinite(self.objective)
        ):
            raise ValueError("Objective must be a finite number, not missing-value imputation")
        if self.verdict != Verdict.PASS and self.objective is not None:
            raise ValueError("Rejected or inconclusive evidence cannot supply an objective")


@dataclass(frozen=True)
class SearchState:
    contract: Contract
    root_id: str
    candidates: tuple[Candidate, ...]
    attempts: tuple[Attempt, ...]
    receipts: tuple[Receipt, ...]
    dependencies: tuple[Dependency, ...]
    revision: int = 0


def candidate(state, candidate_id):
    for value in state.candidates:
        if value.candidate_id == candidate_id:
            return value
    raise ValueError("Unknown candidate")


def _current(state, dependencies):
    epochs = {item.key: item.epoch for item in state.dependencies}
    return all(epochs.get(item.key) == item.epoch for item in dependencies)


def candidate_valid(state, candidate_id):
    return _current(state, candidate(state, candidate_id).dependencies)


def _binding(state, attempt):
    node = candidate(state, attempt.candidate_id)
    if (attempt.search_id != state.contract.search_id
            or attempt.artifact_digest != node.artifact_digest
            or attempt.context != state.contract.context
            or attempt.check_id not in state.contract.checks
            or not set(node.dependencies).issubset(attempt.dependencies)):
        raise ValueError("Attempt does not bind this candidate and verification contract")


def latest_attempt(state, candidate_id, check_id):
    return next((item for item in reversed(state.attempts)
                 if (item.candidate_id, item.check_id) == (candidate_id, check_id)), None)


def evidence(state, candidate_id):
    """Current, scoped outcomes, including FAIL; INCONCLUSIVE remains missing."""
    if not candidate_valid(state, candidate_id):
        return {}
    receipts = {item.attempt.attempt_id: item for item in state.receipts}
    result = {}
    for check in state.contract.checks:
        attempt = latest_attempt(state, candidate_id, check)
        if attempt is None or not _current(state, attempt.dependencies):
            continue
        receipt = receipts.get(attempt.attempt_id)
        if receipt is not None and receipt.verdict != Verdict.INCONCLUSIVE:
            result[check] = receipt
    return result


def missing_checks(state, candidate_id):
    observed = evidence(state, candidate_id)
    return tuple(check for check in state.contract.checks if check not in observed)


def complete_candidates(state):
    result = []
    for node in state.candidates:
        records = evidence(state, node.candidate_id)
        if len(records) == len(state.contract.checks) and all(
            record.verdict == Verdict.PASS for record in records.values()
        ):
            result.append(node)
    return tuple(result)


def accept(state):
    """Select a development candidate only; the root wins ties, then stable ID order."""
    complete = complete_candidates(state)
    if state.root_id not in {item.candidate_id for item in complete}:
        raise ValueError("Search root no longer has complete admissible evidence")
    sign = -1 if state.contract.direction == "maximize" else 1
    return min(complete, key=lambda item: (
        sign * evidence(state, item.candidate_id)[state.contract.objective_check].objective,
        item.candidate_id != state.root_id, item.candidate_id,
    ))


def verified_gain(state):
    selected = accept(state)
    check = state.contract.objective_check
    gain = (evidence(state, selected.candidate_id)[check].objective
            - evidence(state, state.root_id)[check].objective)
    if not isfinite(gain):
        raise ValueError("Verified gain exceeds the finite objective domain")
    return gain if state.contract.direction == "maximize" else -gain


def _receipt_shape(state, receipt):
    objective = receipt.attempt.check_id == state.contract.objective_check
    if (receipt.verdict == Verdict.PASS and objective) != (receipt.objective is not None):
        raise ValueError("Only a passing objective check must supply an objective")


def initialize(contract, root, receipts, *, dependencies=()):
    """Import previously acquired root evidence; its execution/cost remains caller-owned."""
    receipts = tuple(receipts)
    if root.parent_id is not None:
        raise ValueError("Search root cannot have an edit parent in this search")
    state = SearchState(contract, root.candidate_id, (root,),
                        tuple(item.attempt for item in receipts), receipts,
                        _dependencies(dependencies))
    if len(receipts) != len(contract.checks) or len(receipts) > contract.max_attempts:
        raise ValueError("Root requires exactly one receipt per required check within the cap")
    if len({item.attempt.check_id for item in receipts}) != len(receipts):
        raise ValueError("Duplicate root check")
    for field in ("attempt_id", "execution_key"):
        if len({getattr(item.attempt, field) for item in receipts}) != len(receipts):
            raise ValueError("Root execution identities must be unique")
    for receipt in receipts:
        _binding(state, receipt.attempt)
        _receipt_shape(state, receipt)
    accept(state)
    return state


def _guard(state, expected_revision, *, require_root=True):
    _integer(expected_revision)
    if state.revision != expected_revision:
        raise ValueError("Stale search revision; reread and recompute before storage CAS")
    if require_root:
        accept(state)


def add_candidate(state, node, *, expected_revision):
    _guard(state, expected_revision)
    if len(state.candidates) >= state.contract.max_candidates:
        raise ValueError("Candidate limit exhausted")
    if any(item.candidate_id == node.candidate_id for item in state.candidates):
        raise ValueError("Candidate identity is immutable")
    parent = candidate(state, node.parent_id)
    if (node.producer.snapshot != state.contract.improver_snapshot
            or not _current(state, node.dependencies)
            or not set(parent.dependencies).issubset(node.dependencies)):
        raise ValueError("Invalid generation dependencies or changed improver snapshot")
    depth = 1
    while parent.parent_id is not None:
        parent = candidate(state, parent.parent_id)
        depth += 1
    if depth > state.contract.max_depth:
        raise ValueError("Draft depth limit exhausted")
    return replace(state, candidates=(*state.candidates, node), revision=state.revision + 1)


def register_attempt(state, attempt, *, expected_revision):
    """Record a caller-owned claim. A return value is NOT permission to execute."""
    _guard(state, expected_revision)
    _binding(state, attempt)
    if not _current(state, attempt.dependencies):
        raise ValueError("Attempt depends on invalidated evidence or generation sources")
    if len(state.attempts) >= state.contract.max_attempts:
        raise ValueError("Check attempt limit exhausted")
    if any(item.attempt_id == attempt.attempt_id or item.execution_key == attempt.execution_key
           for item in state.attempts):
        raise ValueError("Attempt and execution identities cannot be reused")
    previous = latest_attempt(state, attempt.candidate_id, attempt.check_id)
    if previous is not None:
        receipt = next((item for item in state.receipts if item.attempt == previous), None)
        if receipt is None:
            raise ValueError("Unsettled attempt cannot be replaced or implicitly replayed")
        if _current(state, previous.dependencies) and receipt.verdict != Verdict.INCONCLUSIVE:
            raise ValueError("A valid outcome cannot be retried until it passes")
    return replace(state, attempts=(*state.attempts, attempt), revision=state.revision + 1)


def record_receipt(state, receipt, *, expected_revision):
    """Retain late receipts as history; evidence() separately decides current admission."""
    _guard(state, expected_revision, require_root=False)
    if receipt.attempt not in state.attempts:
        raise ValueError("Receipt does not match a registered attempt")
    _receipt_shape(state, receipt)
    previous = next((item for item in state.receipts
                     if item.attempt.attempt_id == receipt.attempt.attempt_id), None)
    if previous is not None:
        if previous != receipt:
            raise ValueError("Conflicting receipt for an immutable attempt")
        return state
    return replace(state, receipts=(*state.receipts, receipt), revision=state.revision + 1)


def invalidate(state, dependency_key, *, expected_revision):
    """Invalidate a real source, not a parent quality outcome; no cancel/release is issued."""
    _guard(state, expected_revision, require_root=False)
    if dependency_key not in {item.key for item in state.dependencies}:
        raise ValueError("Unknown dependency")
    dependencies = tuple(replace(item, epoch=item.epoch + 1) if item.key == dependency_key
                         else item for item in state.dependencies)
    return replace(state, dependencies=dependencies, revision=state.revision + 1)
