"""Credential-free label/controller acceptance controls."""
import copy
import json
from unittest.mock import Mock

import pytest
import yaml

from inferrsi.model import anthropic_agent as agent
from tools import skill_eval_auto as auto
from tools import skill_eval_pr as pr
from tools.skill_eval_budget import BudgetError


@pytest.fixture
def config():
    provider = {
        "model": {"name": "claude-opus-5-5", "effort": "not_applicable"},
        "client": {"kind": agent.KIND, "provider": "yibuapi", "endpoint": agent.ENDPOINT,
                   "api_version": "2023-06-01", "max_requests": 2, "max_output_tokens": 100,
                   "max_request_bytes": 8192, "max_read_bytes": 1024, "max_tool_calls": 8},
        "pricing": {"currency": "USD", "unit": "per_million_tokens",
                    "model": "claude-opus-5-5", "group": "offline-reviewed-fixture",
                    "rates": {"input": "8", "output": "40", "cache_read": "0.4",
                              "cache_write": "8"},
                    "request_fee": "0", "max_input_tokens": 1000000,
                    "rate_evidence": "https://github.com/example/repo/issues/1#issuecomment-1",
                    "expires_at": 4102444800},
        "spend_limit": {"currency": "USD", "amount": "200"}}
    return {"schema_version": 1, "repository_id": 123, "label": "skill-eval:execute",
            "operators": ["operator"], "expires_at": 4102444800, "provider": provider,
            "provider_sha256": pr.fingerprint(provider), "review_evidence": "offline fixture",
            "anchors": {}}


@pytest.fixture
def plan(config):
    result = {"pr": 7, "repository": "example/repo", "base": "a" * 40, "head": "b" * 40,
              "version": "e" * 40,
              "estimated_calls": 2, "comparisons": [{"plan_sha256": "c" * 64, "calls": 2}],
              "coverage": [{"coverage": "covered"}], "provider_config": config["provider"]}
    result["reservation"] = pr.provider_reservation(result)
    return result


class API:
    def __init__(self, plan, config):
        self.current = {"state": "open", "base": {"sha": plan["base"], "ref": "main",
                                                   "repo": {"id": 123}},
                        "head": {"sha": plan["head"]}, "labels": [{"name": config["label"]}]}
        self.events = [{"id": 1, "event": "labeled", "label": {"name": config["label"]},
                        "actor": {"login": "operator"}, "created_at": "2026-01-01T00:00:00Z"}]
        self.main = plan["version"]
        self.permission = "write"
        self.calls = []

    def request(self, method, path):
        assert method == "GET"
        self.calls.append(path)
        if not path:
            return {"id": 123}
        if path == "/git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": self.main}}
        if path.startswith("/pulls/"):
            return copy.deepcopy(self.current)
        if path.startswith("/issues/"):
            return copy.deepcopy(self.events)
        if path.startswith("/collaborators/"):
            return {"permission": self.permission}
        raise AssertionError(path)


def test_current_label_actor_and_permission(plan, config):
    api = API(plan, config)
    assert auto.live_label(api, plan, config) == {"actor": "operator", "label_event_id": 1}
    api.permission = "read"
    with pytest.raises(ValueError, match="permission"):
        auto.live_label(api, plan, config)


@pytest.mark.parametrize("change", ["closed", "draft", "head", "base", "removed",
                                    "untrusted_actor", "readded", "no_history", "unordered",
                                    "target_branch", "target_repo"])
def test_revocation_and_incomplete_authorization_block(plan, config, change):
    api = API(plan, config)
    if change == "target_branch":
        api.current["base"]["ref"] = "other"
    elif change == "target_repo":
        api.current["base"]["repo"]["id"] = 456
    elif change == "closed":
        api.current["state"] = "closed"
    elif change == "draft":
        api.current["draft"] = True
    elif change in {"head", "base"}:
        api.current[change]["sha"] = "d" * 40
    elif change == "removed":
        api.current["labels"] = []
    elif change == "untrusted_actor":
        api.events[0]["actor"]["login"] = "untrusted"
    elif change == "readded":
        api.events += [{**api.events[0], "id": 2, "event": "unlabeled"},
                       {**api.events[0], "id": 3, "actor": {"login": "untrusted"}}]
    elif change == "no_history":
        api.events = []
    elif change == "unordered":
        api.events *= 2
    with pytest.raises(ValueError):
        auto.live_label(api, plan, config)


def test_incomplete_full_page_history_blocks(plan, config):
    api = API(plan, config)
    api.events = [{**api.events[0], "id": n} for n in range(1, 101)]
    with pytest.raises(ValueError, match="Ambiguous"):
        auto.live_label(api, plan, config)


def test_trusted_configuration_validates_identity_rates_expiry(tmp_path, config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    assert auto.configuration(path, now=1) == config
    for change in ("expired", "hash", "rate", "cache_missing", "group_missing"):
        altered = copy.deepcopy(config)
        if change == "expired":
            altered["expires_at"] = 1
        elif change == "hash":
            altered["provider_sha256"] = "f" * 64
        elif change == "rate":
            altered["provider"]["pricing"]["rates"]["input"] = "1"
        elif change == "cache_missing":
            del altered["provider"]["pricing"]["rates"]["cache_write"]
        else:
            del altered["provider"]["pricing"]["group"]
        if change != "hash":
            altered["provider_sha256"] = pr.fingerprint(altered["provider"])
        path.write_text(json.dumps(altered))
        with pytest.raises((ValueError, KeyError)):
            auto.configuration(path, now=2)


def test_missing_legacy_spend_audit_cannot_bootstrap(plan, config):
    with pytest.raises(BudgetError, match="genesis"):
        auto.ledger_store(Mock(), config, plan["pr"])


@pytest.mark.parametrize("change", ["none", "unsupported", "provider", "stale_cost", "old_policy"])
def test_eligibility_fails_closed(plan, config, change):
    api = API(plan, config)
    if change == "old_policy":
        api.main = "f" * 40
    elif change == "none":
        plan["estimated_calls"] = 0
    elif change == "unsupported":
        plan["coverage"][0]["coverage"] = "unsupported"
    elif change == "provider":
        plan["provider_config"] = {}
    else:
        plan["reservation"]["amount"] = "0"
    with pytest.raises(ValueError):
        auto.eligible(api, plan, config)


def test_workflow_is_opt_in_and_controller_is_only_budget_writer():
    workflow = yaml.safe_load((pr.ROOT / pr.WORKFLOW).read_text())
    trigger = workflow.get("on", workflow.get(True))["pull_request_target"]
    assert {"labeled", "unlabeled", "closed", "synchronize"} <= set(trigger["types"])
    assert trigger["paths"] and "**" not in trigger["paths"]
    job = workflow["jobs"]["execute"]
    assert "auto_candidate == 'true'" in job["if"]
    assert job["permissions"]["contents"] == "write"
    control = [s for s in job["steps"] if "control --output" in s.get("run", "")]
    assert len(control) == 1
    assert not any(" execute --output" in s.get("run", "") for s in job["steps"])
    assert workflow["jobs"]["publish"]["permissions"]["contents"] == "read"


def test_claim_once_launch_scrubs_tokens_and_rechecks_every_request(
        plan, config, tmp_path, monkeypatch):
    import contextlib
    import sys
    import types

    from tools.skill_eval_budget import Genesis, Ledger, PRKey, Snapshot, WriteResult

    class Store:
        def __init__(self):
            self.ledger = Ledger(PRKey(123, 7), Genesis("audited offline history", 0))

        def read_verified(self, key):
            assert key == self.ledger.key
            return Snapshot(str(self.ledger.revision), self.ledger)

        def compare_and_swap(self, before, after):
            assert before.ledger == self.ledger
            self.ledger = after
            return WriteResult.COMMITTED

    store, api = Store(), API(plan, config)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    (tmp_path / "pr-plan.json").write_text(json.dumps(plan))
    monkeypatch.setattr(auto, "ledger_store", lambda *args: (store, store.ledger.key))
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-worker")
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "must-not-reach-worker")
    monkeypatch.setenv("SKILL_EVAL_YIBUAPI_KEY", "offline-only")
    checks = []

    @contextlib.contextmanager
    def broker(check, max_requests, *, context):
        assert max_requests == plan["reservation"]["requests"]
        assert context == pr.fingerprint(plan) + ":42.1"
        checks.append(check)
        yield {"SKILL_EVAL_GUARD_TEST": "offline-only"}

    monkeypatch.setitem(sys.modules, "inferrsi.model.request_guard",
                        types.SimpleNamespace(authorization_broker=broker))

    def launch(command, *, env, cwd, check):
        assert "GITHUB_TOKEN" not in env and "ACTIONS_RUNTIME_TOKEN" not in env
        assert env["SKILL_EVAL_YIBUAPI_KEY"] == "offline-only"
        assert store.ledger.entries[0].phase == "claimed"
        checks[0]()  # First provider call succeeds.
        api.main = "f" * 40
        with pytest.raises(ValueError, match="current trusted main"):
            checks[0]()  # Main advanced after prepare/reservation: no next paid call.
        api.main = plan["version"]
        api.current["labels"] = []
        with pytest.raises(ValueError, match="absent"):
            checks[0]()  # Next provider call cannot proceed.

    auto.controlled_execute(api, tmp_path, config_path=config_path,
                            run_id=42, attempt=1, launch=launch)
    charged = store.ledger.charged
    api.current["labels"] = [{"name": config["label"]}]
    with pytest.raises(BudgetError, match="Duplicate"):
        auto.controlled_execute(api, tmp_path, config_path=config_path,
                                run_id=42, attempt=1, launch=Mock(side_effect=AssertionError))
    with pytest.raises(BudgetError):
        auto.controlled_execute(api, tmp_path, config_path=config_path,
                                run_id=43, attempt=1, launch=Mock(side_effect=AssertionError))
    assert store.ledger.charged == charged
    plan["head"] = "d" * 40
    api.current["head"]["sha"] = plan["head"]
    (tmp_path / "pr-plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="reruns"):
        auto.controlled_execute(api, tmp_path, config_path=config_path,
                                run_id=43, attempt=2, launch=Mock(side_effect=AssertionError))
    assert store.ledger.charged == charged  # Head changes never reset the PR ledger.


def test_configured_unmapped_pr_prepares_without_paid_reservation(tmp_path, config):
    from tests.fixtures.skill_eval_pr_support import setup

    repo, mapping, identity = setup(tmp_path, "addition", ids=("one",))
    mapping_value = json.loads(mapping.read_text())
    mapping_value["skills"] = []
    mapping.write_text(json.dumps(mapping_value))
    output = tmp_path / "unmapped"
    plan = pr.prepare(repo, mapping, identity, output, provider=config["provider"])
    assert plan["estimated_calls"] == 0 and plan["comparisons"] == []
    assert "reservation" not in plan and pr.budget(plan)["reservation"] is None
    report = pr.summary(plan, [], "https://example.invalid/evidence", 100, 1)
    assert "obtain missing evidence" in report
    with pytest.raises(ValueError):
        auto.eligible(API(plan, config), plan, config)


def test_missing_provider_key_does_not_reserve(plan, config, tmp_path, monkeypatch):
    monkeypatch.delenv("SKILL_EVAL_YIBUAPI_KEY", raising=False)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    (tmp_path / "pr-plan.json").write_text(json.dumps(plan))
    ledger = Mock(side_effect=AssertionError("Must not reserve or claim"))
    monkeypatch.setattr(auto, "ledger_store", ledger)
    with pytest.raises(ValueError, match="credential is unavailable"):
        auto.controlled_execute(API(plan, config), tmp_path, config_path=config_path,
                                run_id=42, attempt=1, launch=Mock(side_effect=AssertionError))
    ledger.assert_not_called()


def test_policy_freshness_is_independent_of_historical_comparison(plan, config):
    api = API(plan, config)
    assert len({plan["version"], plan["base"], plan["head"]}) == 3
    auto.eligible(api, plan, config)
    auto.live_label(api, plan, config)
    # Reproduce old-policy checkout before prepare: PR comparison base can remain
    # identical to old policy while main has already advanced.
    plan["version"] = plan["base"]
    with pytest.raises(ValueError, match="current trusted main"):
        auto.eligible(api, plan, config)


@pytest.mark.parametrize("response", [None, {}, {"ref": "refs/heads/other"},
    {"ref": "refs/heads/main", "object": {"type": "tag", "sha": "e" * 40}},
    {"ref": "refs/heads/main", "object": {"type": "commit", "sha": "bad"}}])
def test_invalid_main_response_fails_closed(plan, config, response):
    api = API(plan, config)
    request = api.request
    api.request = lambda method, path: response if path == "/git/ref/heads/main" else request(
        method, path)
    with pytest.raises(ValueError):
        auto.eligible(api, plan, config)


def test_stale_policy_before_controller_never_reserves(plan, config, tmp_path, monkeypatch):
    api = API(plan, config)
    api.main = "f" * 40
    (tmp_path / "pr-plan.json").write_text(json.dumps(plan))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    ledger = Mock(side_effect=AssertionError("No reservation for stale policy"))
    monkeypatch.setattr(auto, "ledger_store", ledger)
    with pytest.raises(ValueError, match="current trusted main"):
        auto.controlled_execute(api, tmp_path, config_path=path, run_id=42, attempt=1)
    ledger.assert_not_called()
