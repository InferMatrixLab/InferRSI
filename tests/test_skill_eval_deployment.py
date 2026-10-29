"""Offline regression checks for the issue-scoped reviewed deployment configuration."""

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest

from inferrsi.model import anthropic_agent as agent
from tools import skill_eval_auto as auto
from tools import skill_eval_pr as pr
from tools.skill_eval_budget import Binding, BudgetError, Genesis, Ledger, reserve

# Freeze observation time: an expired deployment must not make CI depend on wall time.
OBSERVED = 1793184828


@pytest.fixture
def deployed():
    return auto.configuration(now=OBSERVED)


def test_deployment_identity_and_expiry_are_closed(deployed):
    assert deployed["repository_id"] == 1409534281
    assert deployed["operators"] == ["Dong1017"]
    assert deployed["label"] == "skill-eval:execute"
    expected = {"133": "be3164546eb76d073ccd3ddd29cfd18794955bd0",
                "159": "727d31e55f496c53fbf02cf4f624008487de27cb",
                "160": "1fdbd8adc35e2df7439c3cd74780f869d2d6e668"}
    assert set(deployed["anchors"]) == set(expected)
    for number, sha in expected.items():
        assert deployed["anchors"][number] == {
            "ref": f"refs/heads/skill-eval-budget/1409534281/{number}",
            "genesis_commit": sha, "checkpoint_commit": sha}
    assert deployed["schema_version"] == 2
    assert deployed["daily_budget"] == {
        "currency": "USD", "amount": "1000", "timezone": "Asia/Shanghai",
        "anchor": {
            "ref": "refs/heads/skill-eval-budget/1409534281/daily",
            "genesis_commit": "1d3df4ea3924c2b4ce92f051becf566839d66c9c",
            "checkpoint_commit": "1d3df4ea3924c2b4ce92f051becf566839d66c9c"}}
    assert deployed["expires_at"] == OBSERVED + 86400
    assert deployed["provider"]["pricing"]["expires_at"] == deployed["expires_at"]
    assert deployed["provider_sha256"] == pr.fingerprint(deployed["provider"])
    with pytest.raises(ValueError, match="expired"):
        auto.configuration(now=deployed["expires_at"])
    with pytest.raises(BudgetError, match="genesis"):
        auto.ledger_store(Mock(), deployed, 161)


def test_deployment_uses_existing_client_and_no_secret_config(deployed):
    provider = deployed["provider"]
    agent.validate_spec(provider["model"], provider["client"])
    assert provider["model"] == {"name": "claude-opus-5-5", "effort": "not_applicable"}
    assert provider["client"]["endpoint"] == agent.ENDPOINT
    assert provider["client"]["max_requests"] == 6
    assert provider["client"]["max_output_tokens"] == 4096
    assert provider["client"]["max_request_bytes"] == 131072
    assert provider["client"]["max_read_bytes"] == 32768
    assert provider["client"]["max_tool_calls"] == 12
    assert provider["limits"] == {"token_stop_new_trials": 200000}
    assert provider["pricing"]["group"] == "default"
    assert provider["pricing"]["max_input_tokens"] == agent.MODEL_CONTEXT["claude-opus-5-5"]
    assert provider["pricing"]["rates"] == {
        "input": "8", "output": "40", "cache_read": "0.4", "cache_write": "10"}
    assert provider["pricing"]["request_fee"] == "0"
    assert "key" not in json.dumps(deployed).lower()


def test_pair_reservation_fits_both_audited_residuals(deployed):
    value = pr.provider_reservation({"provider_config": deployed["provider"],
                                    "estimated_calls": 2,
                                    "comparisons": [{"plan_sha256": "a" * 64, "calls": 2}]},
                                   now=OBSERVED)
    assert value["per_request"] == "10.17"  # ceil cents of 10 + 4096 * 40 / 1M
    assert value["requests"] == 12 and value["amount"] == "122.04"
    total_remaining = 0
    for number, legacy, remaining in [(159, 680000, 199320000), (160, 63530000, 136470000)]:
        store, key = auto.ledger_store(Mock(), deployed, number)
        assert store.anchor.genesis_commit == store.anchor.checkpoint_commit
        ledger = Ledger(key, Genesis(deployed["review_evidence"], legacy))
        assert ledger.remaining == remaining
        total_remaining += remaining
        binding = Binding("a" * 64, "offline.1", int(Decimal(value["amount"]) * 1000000))
        charged = reserve(ledger, binding)
        assert charged.remaining == remaining - 122040000
        # Even a new plan cannot reset the cumulative PR allowance.
        with pytest.raises(BudgetError, match="exhausted"):
            reserve(charged, Binding("b" * 64, "offline.2", binding.worst_case))
    assert total_remaining == 335790000 < 400000000


@pytest.mark.parametrize("mode", ["addition", "update"])
def test_deployment_provider_prepares_a_complete_pair_without_execution(tmp_path, deployed, mode):
    from tests.fixtures.skill_eval_pr_support import setup

    repo, mapping, identity = setup(tmp_path, mode, ids=("one",))
    plan = pr.prepare(repo, mapping, identity, tmp_path / "planned",
                      provider=deployed["provider"])
    assert plan["estimated_calls"] == 2
    assert plan["reservation"]["amount"] == "122.04"
    assert plan["limits"]["token_stop_new_trials"] == 200000
    assert plan["provider_config"] == deployed["provider"]
    assert plan["comparisons"][0]["mode"] == mode
    assert not list((tmp_path / "planned/selected/results").iterdir())
