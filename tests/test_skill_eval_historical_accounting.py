"""Offline controls; no credentials, provider calls or external ledger writes."""
import json
from types import SimpleNamespace

import pytest

from tools import skill_eval_historical_accounting as historical
from tools.skill_eval_budget import BudgetError, WriteResult


@pytest.fixture
def case(tmp_path, monkeypatch):
    (tmp_path / "results").mkdir()
    approval = {"schema_version": 1, "experiment_id": "offline-history", "repository_id": 123,
                "issue": 9, "charge_pr": 7, "charge_head": "a" * 40,
                "implementation_sha": "b" * 40, "plan_sha256": "c" * 64,
                "protocol_sha256": "c" * 64,
                "baseline": "d" * 40, "candidate": "e" * 40, "expires_at": 4102444800,
                "max_requests": 2, "currency": "USD", "amount": "20.34",
                "approval_evidence": "offline owner approval fixture"}
    config = {"repository_id": 123, "provider": {"model": {"name": "fixture"},
              "client": {"max_requests": 1}, "pricing": {}, "spend_limit": {}}}
    bound = {"requests": 2, "currency": "USD", "amount": "20.34"}
    plan = {"execution_mode": "provider-generation-only-v1", "retry_policy": "none",
            "schedule": [{"condition": "baseline"}, {"condition": "candidate"}],
            "arms": {"baseline": {"git_revision": "d" * 40},
                     "candidate": {"git_revision": "e" * 40}},
            "model": config["provider"]["model"], "client": {
                "settings": {"max_requests": 1}, "pricing": {}, "spend_limit": {}},
            "reservation": bound}
    current = {"number": 7, "base": {"ref": "main", "repo": {"id": 123}},
               "head": {"sha": "a" * 40}, "state": "closed", "merged": True}
    def request(method, path):
        assert method == "GET"
        if path == "":
            return {"id": 123}
        if path == "/git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": "b" * 40}}
        assert path == "/pulls/7"
        return current
    monkeypatch.setattr(historical.compare, "sha256", lambda p: "c" * 64)
    monkeypatch.setattr(historical.compare, "load_plan", lambda p: plan)
    monkeypatch.setattr(historical.compare, "provider_client", lambda p: SimpleNamespace(
        require_live_readiness=lambda count: bound))
    monkeypatch.setattr(historical.auto, "daily_anchor", lambda c: None)
    return SimpleNamespace(approval=approval, config=config, plan=plan, current=current,
                           api=SimpleNamespace(request=request), output=tmp_path)


def test_charge_pr_never_impersonates_historical_arms(case):
    assert historical.validate(case.api, case.output, case.approval, case.config,
                               "protocol") == case.plan
    assert case.current["head"]["sha"] != case.approval["candidate"]
    case.current["head"]["sha"] = case.approval["candidate"]
    with pytest.raises(ValueError, match="Accounting PR"):
        historical.validate(case.api, case.output, case.approval, case.config, "protocol")


@pytest.mark.parametrize("change", ["mode", "retry", "arms", "schedule", "provider", "bound"])
def test_plan_scope_is_frozen(case, change):
    if change == "mode":
        case.plan["execution_mode"] = "local"
    elif change == "retry":
        case.plan["retry_policy"] = "retry"
    elif change == "arms":
        case.plan["arms"]["candidate"]["git_revision"] = "f" * 40
    elif change == "schedule":
        case.plan["schedule"] *= 2
    elif change == "provider":
        case.plan["client"]["settings"] = {"max_requests": 2}
    else:
        case.plan["reservation"]["amount"] = "20.35"
    with pytest.raises(ValueError):
        historical.validate(case.api, case.output, case.approval, case.config, "protocol")


def test_receipt_hash_and_expiry(case, monkeypatch):
    path = case.output / "approval.json"
    path.write_text(json.dumps(case.approval))
    assert historical.receipt(path, "c" * 64) == case.approval
    with pytest.raises(ValueError, match="changed"):
        historical.receipt(path, "f" * 64)
    case.approval["expires_at"] = 1
    path.write_text(json.dumps(case.approval))
    with pytest.raises(ValueError, match="expired"):
        historical.receipt(path, "c" * 64)


@pytest.mark.parametrize("failure", ["missing_key", "daily_conflict", "pr_conflict", "retry"])
def test_no_launch_on_failed_admission(case, monkeypatch, failure):
    calls = []
    monkeypatch.setattr(historical.auto, "configuration", lambda p: case.config)
    monkeypatch.setattr(historical, "receipt", lambda *a: case.approval)
    monkeypatch.setattr(historical, "validate", lambda *a: case.plan)
    monkeypatch.setenv("SKILL_EVAL_YIBUAPI_KEY", "offline-fixture-not-a-credential")
    if failure == "missing_key":
        monkeypatch.delenv("SKILL_EVAL_YIBUAPI_KEY")
    def store(name):
        return SimpleNamespace(read_verified=lambda k: SimpleNamespace(ledger=name),
                               compare_and_swap=lambda *a: (
                                   calls.append(name) or
                                   (WriteResult.CONFLICT if failure == name + "_conflict"
                                    else WriteResult.COMMITTED)))
    monkeypatch.setattr(historical.auto, "ledger_store", lambda *a: (store("pr"), "pr"))
    monkeypatch.setattr(historical.auto, "daily_store", lambda *a: (store("daily"), "daily"))
    monkeypatch.setattr(historical, "reserve", lambda *a: "successor")
    monkeypatch.setattr(historical, "daily_reserve", lambda *a: "successor")
    with pytest.raises((ValueError, BudgetError)):
        historical.controlled_execute(case.api, case.output, config_path="fixture",
                                      approval_path="fixture", approval_sha256="c" * 64,
                                      protocol_path="protocol", run_id="offline",
                                      attempt=2 if failure == "retry" else 1,
                                      launch=lambda *a, **kw: pytest.fail("must not launch"))
    assert calls == ({"daily_conflict": ["daily"], "pr_conflict": ["daily", "pr"]}
                     .get(failure, []))


def test_real_ledger_claims_preserve_prior_day_and_pre_request_receipt(case, monkeypatch):
    from contextlib import contextmanager

    from tools import skill_eval_budget as budget

    key, global_key = budget.PRKey(123, 7), budget.DailyKey(123)
    old = budget.DailyEntry(budget.PRKey(123, 8), budget.Binding("f" * 64, "old", 471_010_000),
                           "2026-10-29", phase="claimed")
    class Store:
        def __init__(self, ledger, daily=False):
            self.ledger, self.daily = ledger, daily

        def read_verified(self, key):
            assert self.ledger.key == key
            cls = budget.DailySnapshot if self.daily else budget.Snapshot
            return cls(str(self.ledger.revision), self.ledger)

        def compare_and_swap(self, before, after):
            assert before.ledger == self.ledger
            validator = budget.validate_daily_successor if self.daily else budget.validate_successor
            validator(self.ledger, after)
            self.ledger = after
            return WriteResult.COMMITTED
    local = Store(budget.Ledger(key, budget.Genesis("offline audited zero", 0)))
    daily = Store(budget.DailyLedger(global_key, "offline audit", entries=(old,)), True)
    monkeypatch.setattr(historical.auto, "configuration", lambda p: case.config)
    monkeypatch.setattr(historical, "receipt", lambda *a: case.approval)
    monkeypatch.setattr(historical, "validate", lambda *a: case.plan)
    monkeypatch.setattr(historical.auto, "ledger_store", lambda *a: (local, key))
    monkeypatch.setattr(historical.auto, "daily_store", lambda *a: (daily, global_key))
    monkeypatch.setattr(historical, "shanghai_day", lambda: "2026-10-30")
    monkeypatch.setenv("SKILL_EVAL_YIBUAPI_KEY", "offline-fixture-not-a-credential")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-enter-child")
    @contextmanager
    def broker(check, max_requests, *, context):
        assert max_requests == 2
        assert (case.output / "historical-execution-approval.json").is_file()
        check()
        yield {"OFFLINE_GATE": "fixture"}
    monkeypatch.setattr(historical, "authorization_broker", broker)
    launched = []
    def launch(command, **kwargs):
        assert "GITHUB_TOKEN" not in kwargs["env"]
        assert kwargs["env"]["OFFLINE_GATE"] == "fixture"
        launched.append(command)
    args = dict(config_path="fixture", approval_path="fixture", approval_sha256="c" * 64,
                protocol_path="fixture", run_id="offline", attempt=1, launch=launch)
    historical.controlled_execute(case.api, case.output, **args)
    assert len(launched) == 1
    assert daily.ledger.entries[0] == old
    assert daily.ledger.charged_on("2026-10-30") == 491_350_000
    assert local.ledger.entries[0].phase == "claimed"
    assert local.ledger.entries[0].binding.plan_digest == "c" * 64
    with pytest.raises(BudgetError):
        historical.controlled_execute(case.api, case.output, **{**args, "run_id": "retry"})
    assert len(launched) == 1

    # A changed receipt cannot replenish the same logical experiment.
    with pytest.raises(BudgetError):
        historical.controlled_execute(case.api, case.output,
                                      **{**args, "approval_sha256": "d" * 64})
    # Nor can changing the experiment identity replenish the same approved plan.
    case.approval["experiment_id"] = "renamed-offline-history"
    with pytest.raises(BudgetError):
        historical.controlled_execute(case.api, case.output, **args)
    assert len(launched) == 1
