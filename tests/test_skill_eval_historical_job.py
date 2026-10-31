"""Offline admission/orchestration controls; no provider, ledger or network calls."""
import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from inferrsi.infra.artifacts import sha256, write_json
from tools import skill_eval_historical_job as job


@pytest.fixture
def case(tmp_path, monkeypatch):
    config = copy.deepcopy(job.read(job.CONFIG))
    config["expires_at"] = config["provider"]["pricing"]["expires_at"] = 4102444800
    config["provider_sha256"] = job.pr.fingerprint(config["provider"])
    policy = {"schema_version": 1, "experiment_id": "offline-fixture", "repository_id":
              config["repository_id"], "issue": 9, "charge_pr": 7, "charge_head": "b" * 40,
              "baseline": "c" * 40, "candidate": "d" * 40, "expires_at": 4102444800,
              "max_requests": 2, "currency": "USD", "amount": "20.34",
              "qualification_run": 456, "qualification_head": "e" * 40,
              "limits": {"repeats": 1, "max_task_calls": 2, "timeout_seconds": 180,
                         "campaign_seconds": 600, "token_stop_new_trials": 200000},
              "skill": "selected", "skill_root": "skills", "task_id": "fixture",
              "approval_evidence": "https://github.com/example/repo/issues/9",
              "effective_group_attestation": "Offline synthetic attestation",
              "scope_note": "Offline prospective test only"}
    config["anchors"] = {"7": {"ref": f"refs/heads/skill-eval-budget/{config['repository_id']}/7",
                               "genesis_commit": "a" * 40, "checkpoint_commit": "a" * 40}}
    locator_path, config_path = tmp_path / "locator.json", tmp_path / "config.json"
    body = job.AUTH_PREFIX + json.dumps(policy) + "\n```"
    locator = {"schema_version": 1, "repository_id": config["repository_id"], "issue": 9,
               "comment_id": 99, "author_login": "Dong1017",
               "body_sha256": hashlib.sha256(body.encode()).hexdigest()}
    comment = {"id": 99, "body": body,
               "issue_url": f"https://api.github.com/repos/{job.REPOSITORY}/issues/9",
               "user": {"login": "Dong1017", "type": "User"}}
    write_json(locator_path, locator)
    write_json(config_path, config)
    monkeypatch.setattr(job, "AUTHORIZATION", locator_path)
    monkeypatch.setattr(job, "CONFIG", config_path)
    monkeypatch.setattr(job, "fetch_comment", lambda comment_id: comment)
    monkeypatch.setattr(job.subprocess, "check_output", lambda *a, **k: "a" * 40)
    fetch = Mock()
    monkeypatch.setattr(job.subprocess, "check_call", fetch)
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
           "repository": {"id": config["repository_id"]},
           "actor": {"login": "Dong1017"}, "triggering_actor": {"login": "Dong1017"}}
    qualification = {"head_sha": policy["qualification_head"],
                     "path": ".github/workflows/skill-eval-qualify.yml",
                     "status": "completed", "conclusion": "success"}
    api = SimpleNamespace(request=lambda method, path: run if path.endswith("/123")
                          else qualification)
    monkeypatch.setattr(job.pr, "GitHub", lambda *a: api)
    launch = Mock()
    monkeypatch.setattr(job.accounting, "controlled_execute", launch)
    return SimpleNamespace(output=tmp_path / "prepared", policy=policy, config=config,
                           run=run, qualification=qualification, launch=launch, api=api,
                           comment=comment, locator=locator, fetch=fetch)


def test_presecret_freeze_then_exact_bounded_admission(case, monkeypatch):
    manifest = job.prepare(case.output)
    assert manifest["approval_sha256"] == sha256(case.output / "approval.json")
    approval = job.read(case.output / "approval.json")
    assert approval["charge_pr"] == 7
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
    ("candidate", "not-a-sha"), ("max_requests", 3), ("amount", "20.35"),
    ("charge_pr", 8), ("expires_at", 1), ("effective_group_attestation", ""),
])
def test_reviewed_policy_is_not_dispatch_scope(case, key, value):
    case.policy[key] = value
    case.comment["body"] = job.AUTH_PREFIX + json.dumps(case.policy) + "\n```"
    case.locator["body_sha256"] = hashlib.sha256(case.comment["body"].encode()).hexdigest()
    write_json(job.AUTHORIZATION, case.locator)
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


@pytest.mark.parametrize("field", ["body", "issue_url", "author", "id"])
def test_issue_artifact_identity_and_hash_are_not_interchangeable(case, field):
    if field == "author":
        case.comment["user"]["login"] = "other"
    elif field == "id":
        case.comment["id"] = 100
    else:
        case.comment[field] += "changed"
    with pytest.raises(ValueError, match="authorization identity"):
        job.prepare(case.output)
    assert not case.fetch.called


def test_duplicate_authorization_keys_rejected_even_if_hash_matches(case):
    case.comment["body"] = job.AUTH_PREFIX + '{"schema_version":1,"schema_version":1}' + "\n```"
    case.locator["body_sha256"] = hashlib.sha256(case.comment["body"].encode()).hexdigest()
    write_json(job.AUTHORIZATION, case.locator)
    with pytest.raises(ValueError, match="Duplicate"):
        job.prepare(case.output)


def test_comment_is_revalidated_by_request_gate(case, monkeypatch):
    job.prepare(case.output)
    monkeypatch.setenv("GITHUB_TOKEN", "offline-canary")
    job.execute(case.output)
    check = case.launch.call_args.kwargs["live_authorization_check"]
    check()
    case.comment["body"] += " "
    with pytest.raises(ValueError, match="authorization identity"):
        check()


def test_git_fetch_uses_only_validated_argv_before_secrets(case):
    job.prepare(case.output)
    args = case.fetch.call_args.args[0]
    assert args[-2:] == [case.policy["baseline"], case.policy["candidate"]]
    assert "shell" not in case.fetch.call_args.kwargs
