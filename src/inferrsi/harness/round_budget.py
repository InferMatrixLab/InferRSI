"""Lane attempt budgets for one parallel round.

The transitions match ``tools/skill_eval_budget.py``: a reservation is a
permanent charge, and the same plan digest cannot be reserved twice. The
identity here is a lane, and each attempt mints its own plan digest from the
unchanged round digest, lane id and attempt ordinal. The cap comes from the
frozen round plan. This module does not authorize a skill-eval pull-request
budget, and it does not confine the filesystem.
"""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path


class BudgetError(ValueError):
    """Invalid, exhausted, expired, or unsafe lane-budget state."""


def _text(value: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 512:
        raise BudgetError("Expected a bounded nonempty identifier")


def _digest(value: str) -> None:
    digits = "0123456789abcdef"
    if type(value) is not str or len(value) != 64 or any(char not in digits for char in value):
        raise BudgetError("Expected SHA-256 digest")


def _amount(value: int, *, positive: bool = False) -> None:
    if type(value) is not int or value < int(positive):
        raise BudgetError("Expected nonnegative integer cost")


def attempt_plan_digest(round_digest: str, lane_id: str, attempt_ordinal: int) -> str:
    """One immutable plan identity per attempt. The round digest stays unchanged."""
    _digest(round_digest)
    _text(lane_id)
    _amount(attempt_ordinal, positive=True)
    payload = f"{round_digest}\n{lane_id}\n{attempt_ordinal}".encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class LaneKey:
    round_digest: str
    lane_id: str

    def __post_init__(self) -> None:
        _digest(self.round_digest)
        _text(self.lane_id)


@dataclass(frozen=True)
class Genesis:
    evidence: str
    legacy_charge: int

    def __post_init__(self) -> None:
        _text(self.evidence)
        _amount(self.legacy_charge)


@dataclass(frozen=True)
class Binding:
    plan_digest: str
    run_id: str
    worst_case: int

    def __post_init__(self) -> None:
        _digest(self.plan_digest)
        _text(self.run_id)
        _amount(self.worst_case, positive=True)


@dataclass(frozen=True)
class Entry:
    binding: Binding
    phase: str = "reserved"
    actual_cost: int | None = None

    def __post_init__(self) -> None:
        if type(self.binding) is not Binding or self.phase not in {
            "reserved", "claimed", "finished", "cancelled"
        }:
            raise BudgetError("Invalid reservation")
        if self.phase == "finished":
            _amount(self.actual_cost)
            if self.actual_cost > self.binding.worst_case:
                raise BudgetError("Actual cost exceeds reservation")
        elif self.actual_cost is not None:
            raise BudgetError("Only finished reservations have actual cost")


@dataclass(frozen=True)
class Ledger:
    key: LaneKey
    genesis: Genesis
    cap: int
    revision: int = 0
    entries: tuple[Entry, ...] = ()

    def __post_init__(self) -> None:
        if type(self.key) is not LaneKey or type(self.genesis) is not Genesis:
            raise BudgetError("Missing ledger identity")
        _amount(self.cap, positive=True)
        _amount(self.revision)
        entries_ok = type(self.entries) is tuple and all(
            type(entry) is Entry for entry in self.entries
        )
        if not entries_ok:
            raise BudgetError("Invalid ledger entries")
        expected = sum(
            {"reserved": 1, "claimed": 2, "finished": 3, "cancelled": 2}[entry.phase]
            for entry in self.entries
        )
        if self.revision != expected:
            raise BudgetError("Inconsistent transition revision")
        plans = [entry.binding.plan_digest for entry in self.entries]
        runs = [entry.binding.run_id for entry in self.entries]
        if len(set(plans)) != len(plans) or len(set(runs)) != len(runs):
            raise BudgetError("Duplicate plan or run binding")
        if self.charged > self.cap:
            raise BudgetError("lane cumulative budget exhausted")

    @property
    def charged(self) -> int:
        return self.genesis.legacy_charge + sum(
            entry.binding.worst_case for entry in self.entries
        )


def reserve(ledger: Ledger, binding: Binding) -> Ledger:
    """Idempotent for the exact binding only. Does not authorize execution."""
    if type(ledger) is not Ledger or type(binding) is not Binding:
        raise BudgetError("Invalid ledger or binding")
    for entry in ledger.entries:
        if entry.binding == binding:
            return ledger
        same_plan = entry.binding.plan_digest == binding.plan_digest
        same_run = entry.binding.run_id == binding.run_id
        if same_plan or same_run:
            raise BudgetError("Plan or run already bound differently")
    return replace(ledger, revision=ledger.revision + 1, entries=ledger.entries + (Entry(binding),))


def advance(
    ledger: Ledger, binding: Binding, phase: str, *, actual_cost: int | None = None
) -> Ledger:
    """Claim is not idempotent. Cancelling a reservation does not free capacity."""
    if type(ledger) is not Ledger or type(binding) is not Binding:
        raise BudgetError("Invalid ledger or binding")
    for index, entry in enumerate(ledger.entries):
        if entry.binding != binding:
            continue
        updated = Entry(binding, phase, actual_cost)
        if updated == entry and phase in {"finished", "cancelled"}:
            return ledger
        allowed = {"reserved": {"claimed", "cancelled"}, "claimed": {"finished"}}
        if phase not in allowed.get(entry.phase, set()):
            raise BudgetError("Unsafe or duplicate execution transition")
        entries = ledger.entries[:index] + (updated,) + ledger.entries[index + 1 :]
        return replace(ledger, revision=ledger.revision + 1, entries=entries)
    raise BudgetError("No exact reservation for this plan/run")


def ensure_open(deadline_utc: str, now: datetime) -> None:
    """Refuse a new attempt after the lane deadline. Reservation does not check time."""
    if type(deadline_utc) is not str:
        raise BudgetError("deadline must be a timezone-aware timestamp")
    try:
        deadline = datetime.fromisoformat(deadline_utc)
    except ValueError as exc:
        raise BudgetError("deadline must be a timezone-aware timestamp") from exc
    if deadline.tzinfo is None or now.tzinfo is None:
        raise BudgetError("deadline and now must be timezone-aware")
    if now > deadline:
        raise BudgetError("lane deadline passed")


def empty_ledger(round_digest: str, lane_id: str, cap: int) -> Ledger:
    return Ledger(
        LaneKey(round_digest, lane_id),
        Genesis("frozen-round-plan", 0),
        cap,
    )


def admit_attempt(
    plan: dict, ledger: Ledger, lane_id: str, now: datetime
) -> tuple[Ledger, Binding]:
    """Read the lane contract, enforce the deadline, then reserve the next attempt."""
    lanes = [lane for lane in plan.get("lanes", []) if lane.get("id") == lane_id]
    if len(lanes) != 1:
        raise BudgetError("lane is missing from the round plan")
    lane = lanes[0]
    ensure_open(lane["deadline_utc"], now)
    ordinal = len(ledger.entries) + 1
    binding = Binding(
        attempt_plan_digest(plan["round_digest"], lane_id, ordinal),
        f"{lane_id}#{ordinal}",
        lane["per_attempt_worst_case"],
    )
    return reserve(ledger, binding), binding


def admit_from_path(
    plan_path: Path, ledger: Ledger, lane_id: str, now: datetime
) -> tuple[Ledger, Binding]:
    """Re-read the frozen plan from disk so a restarted coordinator cannot skip expiry."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    return admit_attempt(plan, ledger, lane_id, now)
