"""Fail-closed cumulative PR budget transitions; Git adapter is a separate module.

Money is integer USD microdollars, rounded UP by the trusted plan producer.
A reservation is a permanent charge against capacity, even after cancellation.
"""

import json
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Protocol

PR_LIMIT_MICROUSD = 200_000_000


class BudgetError(ValueError):
    """Invalid, ambiguous, exhausted, or unsafe budget state."""


def _text(value):
    if type(value) is not str or not value.strip() or len(value) > 512:
        raise BudgetError("Expected a bounded nonempty identifier")


def _amount(value, *, positive=False):
    if type(value) is not int or value < int(positive):
        raise BudgetError("Expected nonnegative integer USD microdollars")


@dataclass(frozen=True)
class PRKey:
    repository_id: int
    pr_number: int

    def __post_init__(self):
        _amount(self.repository_id, positive=True)
        _amount(self.pr_number, positive=True)


@dataclass(frozen=True)
class Genesis:
    """Trusted operator audit, NOT a proof inferred from an absent ledger.

    legacy_charge includes settled spend and upper bounds for ALL outstanding
    work. Unknown legacy spend is not representable and must block creation.
    evidence identifies the audited no-prior-ledger/legacy reconciliation record.
    """

    evidence: str
    legacy_charge: int

    def __post_init__(self):
        _text(self.evidence)
        _amount(self.legacy_charge)


@dataclass(frozen=True)
class Binding:
    """Immutable plan digest + execution attempt identity + worst-case cost.

    plan_digest must cover revisions, mapping, exam, provider/pricing and limits.
    run_id must include the workflow run attempt, not only its run number.
    """

    plan_digest: str
    run_id: str
    worst_case: int

    def __post_init__(self):
        if (type(self.plan_digest) is not str or len(self.plan_digest) != 64
                or any(c not in "0123456789abcdef" for c in self.plan_digest)):
            raise BudgetError("Expected SHA-256 plan digest")
        _text(self.run_id)
        _amount(self.worst_case, positive=True)


@dataclass(frozen=True)
class Entry:
    binding: Binding
    phase: str = "reserved"
    actual_cost: int | None = None

    def __post_init__(self):
        if type(self.binding) is not Binding or self.phase not in {
            "reserved", "claimed", "finished", "cancelled"
        }:
            raise BudgetError("Invalid reservation")
        if self.phase == "finished":
            _amount(self.actual_cost)
            if self.actual_cost > self.binding.worst_case:
                raise BudgetError("Actual cost exceeds reservation; quarantine externally")
        elif self.actual_cost is not None:
            raise BudgetError("Only finished reservations have actual cost")


@dataclass(frozen=True)
class Ledger:
    key: PRKey
    genesis: Genesis
    revision: int = 0
    entries: tuple[Entry, ...] = ()

    def __post_init__(self):
        if type(self.key) is not PRKey or type(self.genesis) is not Genesis:
            raise BudgetError("Missing ledger identity or genesis audit")
        _amount(self.revision)
        if type(self.entries) is not tuple or any(type(e) is not Entry for e in self.entries):
            raise BudgetError("Invalid ledger entries")
        expected_revision = sum({"reserved": 1, "claimed": 2, "finished": 3,
                                 "cancelled": 2}[e.phase] for e in self.entries)
        if self.revision != expected_revision:
            raise BudgetError("Inconsistent transition revision")
        plans = [e.binding.plan_digest for e in self.entries]
        runs = [e.binding.run_id for e in self.entries]
        if len(set(plans)) != len(plans) or len(set(runs)) != len(runs):
            raise BudgetError("Duplicate plan or run binding")
        if self.charged > PR_LIMIT_MICROUSD:
            raise BudgetError("PR cumulative budget exhausted")

    @property
    def charged(self):
        return self.genesis.legacy_charge + sum(e.binding.worst_case for e in self.entries)

    @property
    def remaining(self):
        return PR_LIMIT_MICROUSD - self.charged


def reserve(ledger: Ledger, binding: Binding) -> Ledger:
    """Idempotent for the exact binding only; never authorize execution here."""
    if type(ledger) is not Ledger or type(binding) is not Binding:
        raise BudgetError("Invalid ledger or binding")
    for entry in ledger.entries:
        if entry.binding == binding:
            return ledger
        if (entry.binding.plan_digest == binding.plan_digest
                or entry.binding.run_id == binding.run_id):
            raise BudgetError("Plan or run already bound differently")
    return replace(ledger, revision=ledger.revision + 1,
                   entries=ledger.entries + (Entry(binding),))


def advance(ledger: Ledger, binding: Binding, phase: str, *, actual_cost=None) -> Ledger:
    """Claim is deliberately NOT idempotent: a second claimant must not execute.

    Finished/cancelled writes may be retried with identical evidence. No phase
    frees capacity; a crash in claimed is permanently ambiguous, not retryable.
    """
    if type(ledger) is not Ledger or type(binding) is not Binding:
        raise BudgetError("Invalid ledger or binding")
    for i, entry in enumerate(ledger.entries):
        if entry.binding != binding:
            continue
        updated = Entry(binding, phase, actual_cost)
        if updated == entry and phase in {"finished", "cancelled"}:
            return ledger
        allowed = {"reserved": {"claimed", "cancelled"}, "claimed": {"finished"}}
        if phase not in allowed.get(entry.phase, set()):
            raise BudgetError("Unsafe or duplicate execution transition")
        return replace(ledger, revision=ledger.revision + 1,
                       entries=ledger.entries[:i] + (updated,) + ledger.entries[i + 1:])
    raise BudgetError("No exact reservation for this plan/run")


@dataclass(frozen=True)
class Snapshot:
    """Verified history token and immutable state, never a cached/missing read."""

    token: str
    ledger: Ledger

    def __post_init__(self):
        _text(self.token)
        if type(self.ledger) is not Ledger:
            raise BudgetError("Missing or corrupt existing ledger")


class WriteResult(Enum):
    COMMITTED = "committed"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class AtomicStore(Protocol):
    """Durable storage contract; see skill_eval_budget_git for the GitHub adapter.

    read_verified MUST reject absent/corrupt/untrusted/reset history. A durable
    independent lineage anchor must survive ledger deletion/rollback within the
    documented backend trust boundary. Creation
    MUST be separately audited and atomically create-if-never-created, not an
    upsert. Genesis cannot be inferred from an HTTP 404 or empty history.

    compare_and_swap atomically appends exactly one successor only if the current
    immutable history token equals expected.token; it validates key, genesis,
    revision, monotonic entries/charges and allowed transitions. It returns
    COMMITTED only for this invocation's durable successful write, never merely
    because matching content is already present (especially for claim writes).
    Unknown write outcome must not be reported as CONFLICT or COMMITTED.
    """

    def read_verified(self, key: PRKey) -> Snapshot: ...

    def compare_and_swap(self, expected: Snapshot, successor: Ledger) -> WriteResult: ...


def claim_once(store: AtomicStore, key: PRKey, binding: Binding) -> Ledger:
    """Return only after this caller wins the durable one-shot execution claim.

    A returned ledger is NOT a transferable/replayable execution token. The
    trusted caller must execute at most once in this process, enforce the frozen
    plan's bounds, and never retry paid requests outside those bounds. A crash
    after commit, including before return, burns the reservation. No takeover.
    """
    snapshot = store.read_verified(key)
    if type(snapshot) is not Snapshot or snapshot.ledger.key != key:
        raise BudgetError("Storage returned the wrong PR ledger")
    successor = advance(snapshot.ledger, binding, "claimed")
    result = store.compare_and_swap(snapshot, successor)
    if result is not WriteResult.COMMITTED:
        raise BudgetError("Execution blocked: claim write conflicted or outcome unknown")
    return successor


def validate_successor(before: Ledger, after: Ledger) -> None:
    """Storage adapters must enforce this in addition to atomic history CAS."""
    if type(before) is not Ledger or type(after) is not Ledger:
        raise BudgetError("Invalid transition state")
    if (before.key != after.key or before.genesis != after.genesis
            or after.revision != before.revision + 1):
        raise BudgetError("Reset or identity change forbidden")
    candidates = []
    if len(after.entries) == len(before.entries) + 1:
        candidates.append(reserve(before, after.entries[-1].binding))
    elif len(after.entries) == len(before.entries):
        for old, new in zip(before.entries, after.entries):
            if old != new:
                candidates.append(advance(before, new.binding, new.phase,
                                          actual_cost=new.actual_cost))
    if after not in candidates:
        raise BudgetError("Not a single monotonic budget transition")


def encode(ledger: Ledger) -> str:
    if type(ledger) is not Ledger:
        raise BudgetError("Invalid ledger")
    return json.dumps({"schema_version": 1, **asdict(ledger)},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode(payload: str) -> Ledger:
    """Strict schema/number/duplicate validation, not history authentication."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BudgetError("Duplicate ledger JSON field")
            result[key] = value
        return result

    try:
        value = json.loads(payload, object_pairs_hook=unique)
        if (type(value) is not dict
                or set(value) != {"schema_version", "key", "genesis", "revision", "entries"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or type(value["entries"]) is not list):
            raise BudgetError("Unsupported ledger schema")
        entries = []
        for entry in value["entries"]:
            if type(entry) is not dict or set(entry) != {"binding", "phase", "actual_cost"}:
                raise BudgetError("Invalid reservation schema")
            entries.append(Entry(Binding(**entry["binding"]), entry["phase"], entry["actual_cost"]))
        return Ledger(PRKey(**value["key"]), Genesis(**value["genesis"]),
                      value["revision"], tuple(entries))
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError) as exc:
        raise BudgetError("Missing, corrupt, or unsupported ledger") from exc
