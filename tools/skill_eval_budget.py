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


DAILY_LIMIT_MICROUSD = 1_000_000_000


def _day(value):
    from datetime import date

    try:
        valid = type(value) is str and date.fromisoformat(value).isoformat() == value
    except ValueError:
        valid = False
    if not valid:
        raise BudgetError("Expected canonical calendar day")
    return value


def shanghai_day(now=None):
    """Trusted aware wall clock only; a missing timezone database fails closed."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise BudgetError("An aware trusted clock is required")
    return now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


@dataclass(frozen=True)
class DailyKey:
    repository_id: int

    def __post_init__(self):
        _amount(self.repository_id, positive=True)


@dataclass(frozen=True)
class DailyEntry:
    key: PRKey
    binding: Binding
    admitted_day: str
    phase: str = "reserved"
    closed_day: str | None = None
    actual_cost: int | None = None

    def __post_init__(self):
        if type(self.key) is not PRKey:
            raise BudgetError("Missing daily reservation PR identity")
        Entry(self.binding, self.phase, self.actual_cost)
        _day(self.admitted_day)
        if self.phase in {"finished", "cancelled"}:
            if _day(self.closed_day) < self.admitted_day:
                raise BudgetError("Closing day precedes admission")
        elif self.closed_day is not None:
            raise BudgetError("Outstanding reservation cannot have a closing day")


@dataclass(frozen=True)
class DailyLedger:
    """Repository-wide history, not one ref per date or per PR.

    Audited genesis must import ALL historical daily charges and ALL outstanding
    upper bounds, including legacy PR reservations. Unknown costs block genesis.
    Outstanding work counts on every day from admission until trusted settlement.
    Settlement retains the FULL bound on every day through closure, inclusive;
    it never refunds prior days. A missing settlement safely reduces availability.
    """

    key: DailyKey
    evidence: str
    entries: tuple[DailyEntry, ...] = ()
    revision: int = 0
    quarantine: str | None = None

    def __post_init__(self):
        if type(self.key) is not DailyKey:
            raise BudgetError("Missing daily ledger repository identity")
        _text(self.evidence)
        _amount(self.revision)
        if self.quarantine is not None:
            _text(self.quarantine)
        if (type(self.entries) is not tuple
                or any(type(e) is not DailyEntry or e.key.repository_id != self.key.repository_id
                       for e in self.entries)):
            raise BudgetError("Invalid daily ledger entries")
        plans = [(e.key, e.binding.plan_digest) for e in self.entries]
        runs = [e.binding.run_id for e in self.entries]
        if len(set(plans)) != len(plans) or len(set(runs)) != len(runs):
            raise BudgetError("Duplicate global plan or execution attempt")
        # Charges can only increase at admissions; checking these boundaries
        # proves the cap for the entire timeline, including open-ended entries.
        if any(self.charged_on(e.admitted_day) > DAILY_LIMIT_MICROUSD for e in self.entries):
            raise BudgetError("Global Shanghai daily budget exhausted")

    def require_active(self):
        if self.quarantine is not None:
            raise BudgetError("Global budget quarantined; audited reconciliation required")

    def charged_on(self, day):
        _day(day)
        return sum(e.binding.worst_case for e in self.entries
                   if e.admitted_day <= day and (e.closed_day is None or day <= e.closed_day))

    def remaining_on(self, day):
        return DAILY_LIMIT_MICROUSD - self.charged_on(day)


def daily_reserve(ledger, key, binding, day):
    _day(day)
    if type(ledger) is not DailyLedger or type(key) is not PRKey or type(binding) is not Binding:
        raise BudgetError("Invalid global reservation")
    ledger.require_active()
    for entry in ledger.entries:
        if entry.key == key and entry.binding == binding:
            return ledger  # Across midnight too: never create another reservation.
        if ((entry.key == key and entry.binding.plan_digest == binding.plan_digest)
                or entry.binding.run_id == binding.run_id):
            raise BudgetError("Global plan or run already bound differently")
    if any(day < e.admitted_day or (e.closed_day is not None and day < e.closed_day)
           for e in ledger.entries):
        raise BudgetError("Daily ledger clock moved backwards")
    return replace(ledger, revision=ledger.revision + 1,
                   entries=ledger.entries + (DailyEntry(key, binding, day),))


def daily_advance(ledger, key, binding, phase, day, *, actual_cost=None):
    _day(day)
    if type(ledger) is not DailyLedger:
        raise BudgetError("Invalid global ledger")
    ledger.require_active()
    if any(day < e.admitted_day or (e.closed_day is not None and day < e.closed_day)
           for e in ledger.entries):
        raise BudgetError("Daily ledger clock moved backwards")
    for i, entry in enumerate(ledger.entries):
        if entry.key != key or entry.binding != binding:
            continue
        if phase == "claimed" and day != entry.admitted_day:
            raise BudgetError("A reservation must be claimed on its admission day")
        closed = day if phase in {"finished", "cancelled"} else None
        updated = replace(entry, phase=phase, closed_day=closed, actual_cost=actual_cost)
        if updated == entry and phase in {"finished", "cancelled"}:
            return ledger
        allowed = {"reserved": {"claimed", "cancelled"}, "claimed": {"finished"}}
        if phase not in allowed.get(entry.phase, set()):
            raise BudgetError("Unsafe or duplicate global execution transition")
        return replace(ledger, revision=ledger.revision + 1,
                       entries=ledger.entries[:i] + (updated,) + ledger.entries[i + 1:])
    raise BudgetError("No exact global reservation")


@dataclass(frozen=True)
class DailySnapshot:
    token: str
    ledger: DailyLedger

    def __post_init__(self):
        _text(self.token)
        if type(self.ledger) is not DailyLedger:
            raise BudgetError("Missing global ledger")


def daily_claim_once(store, key, binding, day):
    snapshot = store.read_verified(DailyKey(key.repository_id))
    if type(snapshot) is not DailySnapshot or snapshot.ledger.key != DailyKey(key.repository_id):
        raise BudgetError("Storage returned wrong global ledger")
    successor = daily_advance(snapshot.ledger, key, binding, "claimed", day)
    if store.compare_and_swap(snapshot, successor) is not WriteResult.COMMITTED:
        raise BudgetError("Global claim conflicted or outcome unknown")
    return successor


def daily_quarantine(ledger, evidence):
    """Durably stop ALL global execution on unknown/over-bound exposure.

    This is a one-way transition. There is deliberately no reset/reconciliation
    writer. Record only bounded non-secret evidence; do not include credentials
    or raw provider errors. Existing quarantine is sufficient and unchanged.
    """
    if type(ledger) is not DailyLedger:
        raise BudgetError("Invalid global ledger")
    _text(evidence)
    if ledger.quarantine is not None:
        return ledger
    return replace(ledger, quarantine=evidence, revision=ledger.revision + 1)


def validate_daily_successor(before, after):
    if type(before) is not DailyLedger or type(after) is not DailyLedger:
        raise BudgetError("Invalid global transition state")
    if (before.key != after.key or before.evidence != after.evidence
            or after.revision != before.revision + 1):
        raise BudgetError("Global ledger reset or identity change forbidden")
    if before.quarantine is not None:
        raise BudgetError("Quarantine cannot be reset or edited")
    if after.quarantine is not None:
        if after != daily_quarantine(before, after.quarantine):
            raise BudgetError("Quarantine must preserve all existing charges")
        return
    candidates = []
    if len(after.entries) == len(before.entries) + 1:
        new = after.entries[-1]
        candidates.append(daily_reserve(before, new.key, new.binding, new.admitted_day))
    elif len(after.entries) == len(before.entries):
        for old, new in zip(before.entries, after.entries):
            if old != new:
                candidates.append(daily_advance(before, new.key, new.binding, new.phase,
                                               new.closed_day or new.admitted_day,
                                               actual_cost=new.actual_cost))
    if after not in candidates:
        raise BudgetError("Not a single monotonic global budget transition")


def encode_daily(ledger):
    if type(ledger) is not DailyLedger:
        raise BudgetError("Invalid global ledger")
    return json.dumps({"schema_version": 1, "kind": "shanghai_daily", **asdict(ledger)},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode_daily(payload):
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
                or set(value) != {"schema_version", "kind", "key", "evidence",
                                  "entries", "revision", "quarantine"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["kind"] != "shanghai_daily" or type(value["entries"]) is not list):
            raise BudgetError("Unsupported global ledger schema")
        entries = []
        for entry in value["entries"]:
            if type(entry) is not dict or set(entry) != {
                "key", "binding", "admitted_day", "phase", "closed_day", "actual_cost"
            }:
                raise BudgetError("Invalid global reservation schema")
            entries.append(DailyEntry(**{**entry, "key": PRKey(**entry["key"]),
                                         "binding": Binding(**entry["binding"])}))
        return DailyLedger(DailyKey(**value["key"]), value["evidence"],
                           tuple(entries), value["revision"], value["quarantine"])
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError) as exc:
        raise BudgetError("Missing, corrupt, or unsupported global ledger") from exc
