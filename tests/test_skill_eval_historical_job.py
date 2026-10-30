"""Offline admission/orchestration controls; no provider, ledger or network calls."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from inferrsi.infra.artifacts import sha256, write_json
from tools import skill_eval_historical_job as job


@pytest.fixture
def case(tmp_path, monkeypatch):
    policy = copy.deepcopy(job.read(job.POLICY))
    config = copy.deepcopy(job.read(job.CONFIG))
    policy["expires_at"] = config["expires_at"] = 4102444800
    config["provider"]["pricing"]["expires_at"] = 4102444800
    config["provider_sha256"] = job.pr.fingerprint(config["provider"])
    policy_path, config_path = tmp_path / "policy.json", tmp_path / "config.json"
    write_json(policy_path, policy)
    write_json(config_path, config)
    monkeypatch.setattr(job, "POLICY", policy_path)
    monkeypatch.setattr(job, "CONFIG", config_path)
    monkeypatch.setattr(job.subprocess, "check_output", lambda *a, **k: "a" * 40)
    monkeypatch.delenv("SKILL_EVAL_YIBUAPI_KEY", raising=False)
    for key, value in {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                       "GITHUB_REPOSITORY": job.REPOSITORY, "GITHUB_RUN_ATTEMPT": "1",
                       "GITHUB_ACTOR": "Dong1017", "GITHUB_TRIGGERING_ACTOR": "Dong1017",
                       "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}.items():
        monkeypatch.setenv(key, value)
    def prepare(config_path, repo, output):
        comparison = job.read(config_path)
        assert comparison["snapshots"] == {role: {"git_revision": policy[role]}
                                            for role in ("baseline", "candidate")}
        assert comparison["execution_mode"] == "provider-generation-only-v1"
        assert comparison["limits"]["max_task_calls"] == 2
        (output / "plan").mkdir(parents=True)
        (output / "results").mkdir()
        write_json(output / "plan/freeze.json", {"offline": True})
        return sha256(output / "plan/freeze.json")
    monkeypatch.setattr(job.compare, "prepare", prepare)
    run = {"event": "workflow_dispatch", "head_branch": "main", "head_sha": "a" * 40,
           "run_attempt": 1, "status": "in_progress", "path": job.WORKFLOW,
           "repository": {"id": job.FIXED["repository_id"]},
           "actor": {"login": "Dong1017"}, "triggering_actor": {"login": "Dong1017"}}
    qualification = {"head_sha": job.QUALIFICATION_HEAD,
                     "path": ".github/workflows/skill-eval-qualify.yml",
                     "status": "completed", "conclusion": "success"}
    api = SimpleNamespace(request=lambda method, path: run if path.endswith("/123")
                          else qualification)
    monkeypatch.setattr(job.pr, "GitHub", lambda *a: api)
    launch = Mock()
    monkeypatch.setattr(job.accounting, "controlled_execute", launch)
    return SimpleNamespace(output=tmp_path / "prepared", policy=policy, config=config,
                           run=run, qualification=qualification, launch=launch, api=api)


def test_presecret_freeze_then_exact_bounded_admission(case, monkeypatch):
    manifest = job.prepare(case.output)
    assert manifest["approval_sha256"] == sha256(case.output / "approval.json")
    approval = job.read(case.output / "approval.json")
    assert approval["charge_pr"] == 267
    assert approval["candidate"] != approval["charge_head"]
    assert approval["implementation_sha"] == "a" * 40
    assert approval["protocol_sha256"] == sha256(case.output / "protocol.json")
    assert not case.launch.called
    monkeypatch.setenv("GITHUB_TOKEN", "offline-controller-canary")
    monkeypatch.setenv("SKILL_EVAL_YIBUAPI_KEY", "offline-provider-canary")
    job.execute(case.output)
    assert case.launch.call_count == 1
    assert case.launch.call_args.kwargs["attempt"] == 1
    assert case.launch.call_args.kwargs["approval_sha256"] == manifest["approval_sha256"]


def test_prepare_refuses_secret_injection(case, monkeypatch):
    monkeypatch.setenv("SKILL_EVAL_YIBUAPI_KEY", "offline-canary")
    with pytest.raises(ValueError, match="before provider-secret"):
        job.prepare(case.output)
    assert not case.output.exists()


@pytest.mark.parametrize("key,value", [
    ("GITHUB_EVENT_NAME", "pull_request_target"), ("GITHUB_REF", "refs/heads/feature"),
    ("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_ACTOR", "other"),
    ("GITHUB_TRIGGERING_ACTOR", "other"), ("GITHUB_SHA", "b" * 40),
    ("GITHUB_REPOSITORY", "other/repo"), ("GITHUB_RUN_ID", "1;command"),
])
def test_runtime_rejects_scope_and_retry_changes(case, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        job.prepare(case.output)
    assert not case.launch.called


@pytest.mark.parametrize("key,value", [
    ("candidate", "b" * 40), ("max_requests", 3), ("amount", "20.35"),
    ("charge_pr", 133), ("expires_at", 1), ("effective_group_attestation", ""),
])
def test_reviewed_policy_is_not_dispatch_scope(case, key, value):
    case.policy[key] = value
    write_json(job.POLICY, case.policy)
    with pytest.raises(ValueError):
        job.prepare(case.output)


@pytest.mark.parametrize("name", ["protocol.json", "approval.json", "run/plan/freeze.json"])
def test_frozen_bytes_change_blocks_before_ledger(case, monkeypatch, name):
    job.prepare(case.output)
    with (case.output / name).open("a") as stream:
        stream.write(" ")
    monkeypatch.setenv("GITHUB_TOKEN", "offline-canary")
    with pytest.raises(ValueError, match="freeze changed"):
        job.execute(case.output)
    assert not case.launch.called


@pytest.mark.parametrize("key,value", [("event", "pull_request_target"), ("run_attempt", 2),
                                       ("path", "other.yml"), ("head_sha", "b" * 40),
                                       ("status", "completed")])
def test_live_run_must_match_exact_manual_main(case, monkeypatch, key, value):
    job.prepare(case.output)
    case.run[key] = value
    monkeypatch.setenv("GITHUB_TOKEN", "offline-canary")
    with pytest.raises(ValueError, match="Live workflow"):
        job.execute(case.output)
    assert not case.launch.called


def test_qualification_failure_stops_admission(case, monkeypatch):
    job.prepare(case.output)
    case.qualification["conclusion"] = "failure"
    monkeypatch.setenv("GITHUB_TOKEN", "offline-canary")
    with pytest.raises(ValueError, match="qualification"):
        job.execute(case.output)
    assert not case.launch.called


def test_package_without_preparation_retains_failure_only(case):
    job.package(case.output)
    assert job.read(case.output / "public/capture.json") == {"state": "not_prepared"}
    assert not case.launch.called


def test_workflow_has_no_inputs_and_only_one_secret_consumer():
    raw = (job.ROOT / job.WORKFLOW).read_text()
    value = yaml.safe_load(raw)
    assert value.get("on", value.get(True)) == {"workflow_dispatch": None}
    assert value["permissions"] == {}
    steps = value["jobs"]["generate"]["steps"]
    assert "github.run_attempt == 1" in value["jobs"]["generate"]["if"]
    assert sum("secrets.SKILL_EVAL_YIBUAPI_KEY" in json.dumps(s) for s in steps) == 1
    checkout = steps[0]
    assert checkout["with"]["persist-credentials"] is False
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert "prepare" in steps[3]["run"] and "SKILL_EVAL_YIBUAPI_KEY" not in str(steps[3])
    assert "execute" in steps[4]["run"]
    assert "env -i" in steps[5]["run"]
    assert "replay" not in steps[4]["run"]
