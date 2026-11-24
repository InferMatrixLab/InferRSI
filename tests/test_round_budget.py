"""Lane attempt budgets. Costs in these tests are plan fields, not campaign gates."""

import json
from datetime import datetime, timezone

import pytest

from inferrsi.harness.round_budget import (
    BudgetError,
    admit_from_path,
    advance,
    attempt_plan_digest,
    empty_ledger,
)

ROUND = "a" * 64
WHEN = datetime(2026, 10, 30, tzinfo=timezone.utc)


def _plan(path, *, cap=2, worst=1, deadline="2099-01-01T00:00:00+00:00"):
    document = {
        "round_digest": ROUND,
        "lanes": [
            {
                "id": "L1",
                "cap": cap,
                "per_attempt_worst_case": worst,
                "deadline_utc": deadline,
            }
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def test_retry_with_budget_remaining_keeps_both_charges(tmp_path):
    plan = _plan(tmp_path / "round-plan.json", cap=2, worst=1)
    ledger = empty_ledger(ROUND, "L1", cap=2)
    first, binding = admit_from_path(tmp_path / "round-plan.json", ledger, "L1", WHEN)
    cancelled = advance(first, binding, "cancelled")
    second, _ = admit_from_path(tmp_path / "round-plan.json", cancelled, "L1", WHEN)
    assert second.charged == 2
    assert len(second.entries) == 2
    assert second.entries[0].phase == "cancelled"
    assert second.entries[1].phase == "reserved"
    assert attempt_plan_digest(ROUND, "L1", 1) != attempt_plan_digest(ROUND, "L1", 2)
    assert plan["round_digest"] == ROUND


def test_exhausted_budget_rejects_the_next_attempt(tmp_path):
    _plan(tmp_path / "round-plan.json", cap=1, worst=1)
    ledger = empty_ledger(ROUND, "L1", cap=1)
    reserved, binding = admit_from_path(tmp_path / "round-plan.json", ledger, "L1", WHEN)
    cancelled = advance(reserved, binding, "cancelled")
    with pytest.raises(BudgetError, match="exhausted"):
        admit_from_path(tmp_path / "round-plan.json", cancelled, "L1", WHEN)


def test_past_deadline_rejects_even_when_budget_remains(tmp_path):
    plan_path = tmp_path / "round-plan.json"
    _plan(plan_path, cap=5, worst=1, deadline="2020-01-01T00:00:00+00:00")
    ledger = empty_ledger(ROUND, "L1", cap=5)
    before = ledger.charged
    with pytest.raises(BudgetError, match="deadline"):
        admit_from_path(plan_path, ledger, "L1", WHEN)
    reloaded = json.loads(plan_path.read_text(encoding="utf-8"))
    assert reloaded["lanes"][0]["deadline_utc"].startswith("2020-")
    assert ledger.charged == before
