"""Free PR scope reporting survives unavailable paid execution prerequisites."""

import copy
import json
import shutil
from unittest.mock import Mock

import pytest

from inferrsi.infra.artifacts import write_json
from tests.fixtures.skill_eval_compare_support import git
from tests.fixtures.skill_eval_pr_support import SimulatedGitHub, setup
from tests.test_skill_eval_pr import dispatch_event
from tools import skill_eval_auto as auto
from tools import skill_eval_pr as pr


def prepare_cli(tmp_path, monkeypatch, config, *, two_skills=False):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    if two_skills:
        shutil.copytree(repo / "library/selected", repo / "library/second")
        skill = repo / "library/second/SKILL.md"
        skill.write_text(skill.read_text().replace("name: selected", "name: second"))
        git(repo, "add", "library/second")
        git(repo, "commit", "--quiet", "-m", "Offline second mapped skill")
        identity["head"] = git(repo, "rev-parse", "HEAD")
        value = json.loads(mapping.read_text())
        value["skills"].append({**value["skills"][0], "skill": "second",
                                "entrypoint": "second/SKILL.md", "paths": ["library/second"]})
        write_json(mapping, value)
    identity["version"] = identity["base"]
    config_path = tmp_path / "trusted.json"
    if config is not None:
        config_path.write_text(config if isinstance(config, str) else json.dumps(config))
    monkeypatch.setattr(auto, "CONFIG", config_path)
    api = SimulatedGitHub(identity)
    monkeypatch.setattr(pr, "GitHub", lambda *args: api)
    monkeypatch.setattr(pr, "ROOT", repo)
    monkeypatch.setattr(pr, "MAPPING", mapping)
    original_git, original_run = pr.git, pr.subprocess.run
    monkeypatch.setattr(pr, "git", lambda root, *args: identity["base"].encode()
                        if args == ("rev-parse", "HEAD") else original_git(root, *args))
    monkeypatch.setattr(pr.subprocess, "run", lambda command, *a, **kw: None
                        if command[:2] == ["git", "fetch"] else original_run(command, *a, **kw))
    no_execution = Mock(side_effect=AssertionError("No paid execution or ledger mutation"))
    monkeypatch.setattr(auto, "controlled_execute", no_execution)
    monkeypatch.setattr(pr.compare, "execute", no_execution)
    output = tmp_path / "prepared"
    dispatch_event(monkeypatch, tmp_path, output, {}, "prepare")
    write_json(tmp_path / "event.json", {"pull_request": {"number": 7}})
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    pr.main()
    plan = pr.compare.read_json(output / "pr-plan.json")
    dispatch_event(monkeypatch, tmp_path, output, {}, "publish")
    write_json(tmp_path / "event.json", {"pull_request": {"number": 7}})
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    pr.main()
    assert "### Advisory:" in api.comments[0]["body"]
    assert not pr.compare.read_json(output / "control-status.json")["eligible"]
    assert "auto_candidate=false" in (tmp_path / "github-output").read_text()
    assert not (output / "execution-claim.json").exists()
    no_execution.assert_not_called()
    return plan, output, api


@pytest.fixture
def config():
    return json.loads(auto.CONFIG.read_text())


def test_two_mapped_skills_without_label_or_anchor_keep_free_advisory(
        tmp_path, monkeypatch, config):
    # PR7 has no configured anchor and the fixture supplies no label/permission API.
    plan, output, api = prepare_cli(tmp_path, monkeypatch, config, two_skills=True)
    assert plan["estimated_calls"] == 4 and len(plan["comparisons"]) == 2
    assert all("plan_sha256" in c for c in plan["comparisons"])
    assert "reservation" not in plan and plan["execution_blocked"]
    assert plan["provider_config"] == config["provider"]
    assert config["provider"]["spend_limit"]["amount"] == "200"
    with pytest.raises(ValueError, match="exceeds approved total"):
        pr.provider_reservation(plan, now=0)
    assert "Selected comparisons: **2**" in api.comments[0]["body"]
    assert "Paid execution blocked" in api.comments[0]["body"]
    assert not any("/git/" in path or "/collaborators/" in path for path in api.reads)
    with pytest.raises(ValueError, match="Planning-only"):
        auto.eligible(plan, config)
    with pytest.raises(ValueError, match="Planning-only"):
        pr.execute(output, {}, client=Mock())
    with pytest.raises(ValueError, match="Planning-only"):
        pr.authorize(plan, {}, "actor", "write", {})


@pytest.mark.parametrize("kind", ["config", "pricing"])
def test_expired_paid_configuration_preserves_provider_plan_and_free_publication(
        tmp_path, monkeypatch, config, kind):
    config = copy.deepcopy(config)
    if kind == "config":
        config["expires_at"] = 1
    else:
        config["provider"]["pricing"]["expires_at"] = 1
        config["provider_sha256"] = pr.fingerprint(config["provider"])
    plan, output, api = prepare_cli(tmp_path, monkeypatch, config)
    assert plan["provider_config"] == config["provider"]
    assert "reservation" in plan and "execution_blocked" not in plan
    assert "blocked" in api.comments[0]["body"]
    with pytest.raises(ValueError, match="expired"):
        auto.configuration()
    # Planning uses historical validation, not current eligibility. Stable fingerprints
    # keep P1's exact original-plan binding usable after provider/config expiry.
    identity = {key: plan[key] for key in ("repository", "pr", "base", "head", "version")}
    rebuilt = pr.prepare(pr.ROOT, pr.MAPPING, identity, tmp_path / "rebuilt",
                         provider=config["provider"])
    assert pr.fingerprint(plan) == pr.fingerprint(rebuilt)
    assert "expired" in pr.compare.read_json(output / "control-status.json")["reason"]


@pytest.mark.parametrize("broken", [None, "not JSON", "[]", '{"provider":{}}'])
def test_missing_or_corrupt_config_is_explicit_mapping_only_not_model_fallback(
        tmp_path, monkeypatch, broken):
    plan, output, api = prepare_cli(tmp_path, monkeypatch, broken)
    assert plan["execution_blocked"] and "provider_config" not in plan
    assert plan["model"]["name"] == "unconfigured"
    assert plan["estimated_calls"] == 0
    assert not any("plan_sha256" in c for c in plan["comparisons"])
    assert not (output / "selected/plan").exists()
    assert "no alternate provider/model is selected" in api.comments[0]["body"]
    with pytest.raises(ValueError, match="Planning-only"):
        pr.execute(output, {}, client=Mock())


@pytest.mark.parametrize("anchors", [None, [], "not a mapping"])
def test_malformed_anchor_container_keeps_mapping_only_summary(
        tmp_path, monkeypatch, config, anchors):
    config["anchors"] = anchors
    plan, output, api = prepare_cli(tmp_path, monkeypatch, config)
    assert plan["execution_blocked"] and plan["model"]["name"] == "unconfigured"
    assert "invalid" in api.comments[0]["body"]
    assert not (output / "selected/plan").exists()


@pytest.mark.parametrize("operators", ["Dong1017", {"Dong1017": True}, [123]])
def test_malformed_operator_allowlist_cannot_enable_substring_authorization(
        tmp_path, monkeypatch, config, operators):
    config["operators"] = operators
    plan, _, api = prepare_cli(tmp_path, monkeypatch, config)
    assert plan["execution_blocked"] and plan["model"]["name"] == "unconfigured"
    assert "invalid" in api.comments[0]["body"]
    with pytest.raises(ValueError):
        auto.configuration(now=0)


@pytest.mark.parametrize("field", ["model", "client", "pricing", "spend_limit", "limits"])
def test_malformed_nested_provider_policy_preserves_free_scope(
        tmp_path, monkeypatch, config, field):
    config["provider"][field] = []
    config["provider_sha256"] = pr.fingerprint(config["provider"])
    plan, _, api = prepare_cli(tmp_path, monkeypatch, config)
    assert plan["execution_blocked"] and plan["model"]["name"] == "unconfigured"
    assert "invalid" in api.comments[0]["body"]


@pytest.mark.parametrize("change", ["bad_limit", "extra_key"])
def test_invalid_provider_schema_cannot_abort_free_planning(
        tmp_path, monkeypatch, config, change):
    if change == "bad_limit":
        config["provider"]["limits"] = {"token_stop_new_trials": 0}
    else:
        config["provider"]["unknown"] = True
    config["provider_sha256"] = pr.fingerprint(config["provider"])
    plan, _, api = prepare_cli(tmp_path, monkeypatch, config)
    assert plan["execution_blocked"] and plan["model"]["name"] == "unconfigured"
    assert "invalid" in api.comments[0]["body"]
