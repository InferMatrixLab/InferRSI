"""Offline controller/workflow tests: synthetic identities, keys, stores and HTTP only."""

import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from inferrsi.harness import kv_reclamation as kv
from inferrsi.infra.artifacts import atomic_write_json
from inferrsi.model import anthropic_agent as provider
from inferrsi.model import anthropic_edit_agent as edit
from tests.test_anthropic_edit_agent import read_task, submit, work
from tests.test_kv_edit_workbench import BASELINE, CANDIDATE, TRACE, fake_sandbox, suite
from tests.test_kv_pilot_admission import World
from tests.test_kv_pilot_admission import policy as sample_policy
from tools import kv_live_job as job
from tools import kv_live_policy as policy
from tools import kv_live_worker as worker


def write(root, name, data):
    if not isinstance(data, bytes):
        data = provider.canonical(data).encode()
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": name, "bytes": len(data), "sha256": policy.sha(data)}


@pytest.fixture
def staged(tmp_path, monkeypatch):
    root, output = tmp_path / "checkout", tmp_path / "output"
    root.mkdir()
    output.mkdir()
    monkeypatch.setattr(job, "ROOT", root)
    monkeypatch.setattr(policy, "ROOT", root)
    visible = suite().read()
    common, prompt, _ = job.inputs.build_inputs(BASELINE, b"contract", visible["development"],
        visible["benchmark_events"], visible["benchmark_expected"], visible["min_improvement_pct"])
    paths = {"candidate.py": "tests/fixtures/kv_reclamation/candidate.py",
             "CONTRACT.md": "evidence/kv-reclamation-20261030/validator/independent/CONTRACT.md"}
    sources = {name: (paths.get(name, "fixture/" + name), data) for name, data in common.items()}
    sources.update({name: (job.KNOWLEDGE_ROOT + name[len("knowledge/"):], b"offline knowledge")
                    for name in job.KNOWLEDGE})
    records = {name: write(root, path, data) for name, (path, data) in sources.items()}
    provider_config = json.loads(sample_policy().provider_json)
    plan = {"actors": {}, "provider": provider_config, "execution_id": "offline-1",
            "expires_at": int(time.time()) + 7200, "arm_order": ["A2", "A3"],
            "suite": write(root, "fixture/suite.json", suite().serialized),
            "final_suite": write(root, "fixture/final.json", suite().serialized),
            "hidden_traces": write(root, "fixture/hidden.json", [{**TRACE, "split": "grader"}]),
            "charge_pr": 999, "charge_head": "2" * 40,
            "final_seconds": 180, "final_repetitions": 8}
    configs = {}
    for arm in ("A2", "A3"):
        names = job.COMMON | (job.KNOWLEDGE if arm == "A3" else set())
        workspace = tmp_path / f"freeze-{arm}"
        workspace.mkdir()
        for name in names:
            write(workspace, name, sources[name][1])
        ep = edit.EditPlan(edit.freeze_files(workspace, names),
            edit.EditLimits(65536, 8192, 8, 8, 4, 2, 600), (TRACE["id"],),
            "elapsed_seconds", "seconds", "minimize", "0" * 64)
        configs[arm] = worker.configuration(workspace, ep, suite(), BASELINE, arm=arm,
            model="claude-opus-5-5", spec=provider_config["client"], prompt=prompt)
        plan["actors"][arm] = {"config": write(root, f"fixture/{arm}.json", configs[arm]),
                              "workspace": [{"path": n, "source": records[n]}
                                            for n in sorted(names)]}
    job._stage(plan, output)
    atomic_write_json(output / "authorization.json", {"body": "offline frozen public fixture"})
    authorization = {"plan": plan, "plan_sha256": policy.fingerprint(plan)}
    locator = {"offline": True}
    prepared = {"schema": "kv-live-prepared-v1", "implementation_sha": "a" * 40,
        "run_id": "123", "plan_sha256": authorization["plan_sha256"],
        "locator_sha256": policy.fingerprint(locator), "cleanup": {"verdict": "PASS"},
        "runtime_profile": {"verdict": "PASS"},
        "replay": {a: {"verdict": "PASS", "model_calls": 0} for a in ("A2", "A3")},
        "inputs": kv.workspace_hashes(output)}
    atomic_write_json(output / "prepared.json", prepared)
    monkeypatch.setattr(policy, "frozen_authorization", lambda **_: (authorization, locator))
    monkeypatch.setattr(policy, "runtime", lambda: ("a" * 40, "123"))
    monkeypatch.setattr(policy, "verify_live", lambda *_: None)
    monkeypatch.setattr(job, "runway", lambda *_: None)
    monkeypatch.setenv(provider.KEY_ENV, "OFFLINE-FAKE-PROVIDER-KEY")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    world = World()
    root_policy = sample_policy(
        actor_sha256=tuple(configs[a]["actor_sha256"] for a in ("A2", "A3")),
        plan_sha256=authorization["plan_sha256"], execution_id=plan["execution_id"])
    monkeypatch.setattr(policy, "policy", lambda *_: root_policy)
    original_admit = job.admission.admit
    monkeypatch.setattr(job.admission, "admit", lambda *args, **kwargs:
        original_admit(*args, **kwargs, wall_clock=lambda: world.now))
    monkeypatch.setattr(kv, "invoke", fake_sandbox)
    monkeypatch.setattr(kv, "probe_isolation", lambda *_: {"offline": True})
    return SimpleNamespace(root=root, output=output, plan=plan, world=world,
                           configs=configs, authorization=authorization)


def launcher(scripts, seen):
    def execute(command, cwd, output, deadline, *, environment):
        assert environment[provider.KEY_ENV] == "OFFLINE-FAKE-PROVIDER-KEY"
        forbidden = {"GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN", "HOME", "PYTHONPATH"}
        assert not forbidden & set(environment)
        args = dict(zip(command[3::2], command[4::2]))
        assert float(args["--deadline"]) == deadline
        arm = Path(args["--inputs"]).parent.name
        seen.append(arm)
        responses = iter(copy.deepcopy(scripts))
        code = worker.live_worker(args["--inputs"], args["--workspace"], args["--output"],
            deadline, environment=environment, emit=lambda _: None,
            transport=lambda *a, **kw: next(responses))
        return {"status": "completed" if code == 0 else "failed", "returncode": code}

    return lambda *args, **kwargs: worker.run_supervised(*args, **kwargs, execute=execute)


def test_fake_pair_reserves_before_disclosure_and_grades_immutable_bytes(staged, monkeypatch):
    seen = []
    scripts = [read_task(), work(CANDIDATE), work(CANDIDATE + "# final\n", "2"), submit()]
    launch = launcher(scripts, seen)
    def checked_launch(*args, **kwargs):
        assert len(staged.world.events) == 4
        return launch(*args, **kwargs)
    result = job.execute(staged.output, api=SimpleNamespace(),
        stores=(staged.world.daily, staged.world.pr), launch=checked_launch)
    assert seen == ["A2", "A3"]
    assert all(a["status"] == "completed" for a in result["arms"].values())
    assert staged.world.pr.ledger.charged == 162720000
    assert staged.world.daily.ledger.charged_on("2026-10-30") == 654070000
    summary = job.package(staged.output)
    assert all(len(r) == 4 for r in summary["requests"].values())
    assert all(a["status"] == "submitted" for a in summary["artifacts"].values())
    assert all(len(v["revisions"]) == 3 and len(v["feedback"]) == 4
               for v in summary["evidence"].values())
    for arm in seen:
        (staged.output / arm / "workspace/candidate.py").write_text("changed after submission")
    monkeypatch.delenv(provider.KEY_ENV)
    graded = job.grade(staged.output / "public", staged.output / "grade")
    assert all(a["semantic"]["verdict"] == "PASS" for a in graded["arms"].values())
    public = b"".join(p.read_bytes() for p in (staged.output / "public").rglob("*") if p.is_file())
    assert b"OFFLINE-FAKE-PROVIDER-KEY" not in public


def test_unknown_usage_retains_attempt_and_does_not_disclose_other_arm(staged):
    seen = []
    result = job.execute(staged.output, api=SimpleNamespace(),
        stores=(staged.world.daily, staged.world.pr),
        launch=launcher([{**read_task(), "usage": None}], seen))
    assert seen == ["A2"]
    assert result["arms"]["A3"]["status"] == "not_started"
    summary = job.package(staged.output)
    assert summary["requests"]["A2"][0]["status"] == "unresolved"
    assert summary["requests"]["A2"][0]["usage"] is None
    assert staged.world.pr.ledger.charged == 162720000


def test_prepared_input_mutation_blocks_before_reservation(staged):
    (staged.output / "A2/workspace/task.json").write_text("changed")
    with pytest.raises(ValueError, match="inputs changed"):
        job.execute(staged.output, api=SimpleNamespace(),
            stores=(staged.world.daily, staged.world.pr), launch=Mock())
    assert staged.world.events == []


def test_stage_rejects_sibling_leak_or_nonidentical_common_bytes(staged, tmp_path):
    value = copy.deepcopy(staged.plan)
    value["actors"]["A2"]["workspace"].append({"path": "knowledge/SKILL.md"})
    with pytest.raises(ValueError, match="allowlist"):
        job._stage(value, tmp_path / "bad-stage")


@pytest.mark.parametrize("credential", [provider.KEY_ENV, "GITHUB_TOKEN"])
def test_final_grade_rejects_injected_authority(tmp_path, monkeypatch, credential):
    monkeypatch.setenv(credential, "OFFLINE-FAKE")
    with pytest.raises(ValueError, match="without injected"):
        job.grade(tmp_path / "input", tmp_path / "output")


def test_immutable_final_bundle_rejects_wrong_run_before_grading(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    monkeypatch.setenv("GITHUB_RUN_ID", "124")
    result = job.grade(staged.output / "public", staged.output / "grade")
    assert all(a["reason"] == "invalid_execution_identity" for a in result["arms"].values())


@pytest.mark.parametrize("now,seconds", [("2026-10-30T15:59:00", 7200),
                                          ("2026-10-30T12:00:00", 1319)])
def test_no_partial_pair_before_expiry_or_shanghai_midnight(now, seconds):
    now = datetime.fromisoformat(now).replace(tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="runway"):
        job.runway(now.timestamp() + seconds, now=now)


@pytest.mark.parametrize("method,path,data", [("POST", "/git/refs", {}),
    ("PATCH", "/git/refs/heads/main", {"sha": "a" * 40, "force": False}),
    ("PATCH", "/git/refs/heads/skill-eval-budget/1409534281/999",
     {"sha": "a" * 40, "force": True}), ("GET", "/pulls/1?x=1", None)])
def test_controller_api_rejects_scope_before_http(method, path, data):
    opener = Mock()
    api = job.DeadlineGitHub("OFFLINE-FAKE", time.monotonic() + 30, opener=opener)
    with pytest.raises(ValueError, match="scope"):
        api.request(method, path, data)
    opener.open.assert_not_called()


def test_workflow_manual_no_inputs_no_credential_binding_and_separate_pinned_grade():
    path = Path(__file__).parents[1] / ".github/workflows/kv-edit-pilot.yml"
    text = path.read_text()
    value = yaml.load(text, Loader=yaml.BaseLoader)
    assert value["on"] == {"workflow_dispatch": ""}
    assert value["permissions"] == {}
    assert value["concurrency"]["cancel-in-progress"] == "false"
    assert "secrets." not in text
    for name, job_value in value["jobs"].items():
        condition = job_value["if"]
        for guard in ("github.repository", "github.ref", "github.run_attempt", "github.actor",
                      "github.triggering_actor"):
            assert guard in condition
        for step in job_value["steps"]:
            if "uses" in step:
                assert policy._hex(step["uses"].split("@")[1], 40)
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
                assert step["with"]["ref"] == "${{ github.sha }}"
    grade = value["jobs"]["grade"]
    assert grade["permissions"]["contents"] == "read"
    download = next(s for s in grade["steps"] if s.get("uses", "").startswith("actions/download"))
    assert set(download["with"]) == {"name", "path"}  # Current-run only; no URL/run-id input.
    assert download["with"]["name"] == "kv-live-${{ github.run_id }}-${{ github.run_attempt }}"
    projection = next(s for s in grade["steps"] if "package-grade" in s.get("run", ""))
    assert projection["if"] == "always()" and "env -i" in projection["run"]
    upload = next(s for s in grade["steps"] if s.get("uses", "").startswith("actions/upload"))
    assert upload["with"]["path"] == "${{ runner.temp }}/kv-grade/public"
    operations = (path.parents[2] / "docs/operations.md").read_text()
    assert "`package-grade` never reruns candidates or models" in operations


def test_same_host_preflight_uses_real_scoped_scripted_loop_with_fake_sandbox(staged, monkeypatch):
    from tests.test_kv_edit_pilot import in_process_worker
    original = worker.scripted.run_supervised
    monkeypatch.setattr(worker.scripted, "run_supervised", lambda *a, **kw:
        original(*a, **kw, execute=in_process_worker))
    monkeypatch.delenv(provider.KEY_ENV)
    result = job.replay_preflight(staged.output, time.monotonic() + 120)
    assert set(result) == {"A2", "A3"}
    assert all(v["model_calls"] == 0 and v["verdict"] == "PASS" for v in result.values())


def test_grade_rejects_symlink_source_as_inconclusive(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    candidate = staged.output / "public/A2/candidate.py"
    candidate.unlink()
    candidate.symlink_to(staged.output / "A2/run/worker/final/candidate.py")
    monkeypatch.delenv(provider.KEY_ENV)
    result = job.grade(staged.output / "public", staged.output / "grade")
    assert result["arms"]["A2"]["verdict"] == "INCONCLUSIVE"
    assert result["arms"]["A3"]["semantic"]["verdict"] == "PASS"


def test_missing_entire_artifact_bundle_retains_both_arms_as_inconclusive(staged, monkeypatch):
    monkeypatch.delenv(provider.KEY_ENV)
    result = job.grade(staged.output / "missing", staged.output / "grade")
    assert set(result["arms"]) == {"A2", "A3"}
    assert all(v["verdict"] == "INCONCLUSIVE" for v in result["arms"].values())
    assert (staged.output / "grade/grade.json").is_file()


def test_uncertain_admission_retains_identity_without_zero_cost_claim(staged, monkeypatch):
    staged.world.daily.outcomes = ["unknown_commit"]
    with pytest.raises(job.policy.budget.BudgetError):
        job.execute(staged.output, api=SimpleNamespace(),
            stores=(staged.world.daily, staged.world.pr), launch=Mock())
    assert staged.world.daily.ledger.charged_on("2026-10-30") == 654070000
    assert staged.world.pr.ledger.charged == 0
    result = job.package(staged.output)
    assert result["execution"]["admission_outcome"].endswith("unknown_no_retry")
    assert result["execution"]["reserved_usd"] is None
    assert result["execution"]["actual_cost_usd"] is None
    monkeypatch.delenv(provider.KEY_ENV)
    grade = job.grade(staged.output / "public", staged.output / "grade")
    assert all(a["verdict"] == "INCONCLUSIVE" for a in grade["arms"].values())


@pytest.mark.parametrize("field,value", [("execution_id", "wrong-execution"), ("revision", 999),
    ("artifact", "wrong.py"), ("check_receipt", "0" * 64), ("benchmark_receipt", "0" * 64)])
def test_corrupt_final_receipt_cannot_be_packaged_or_graded(staged, monkeypatch, field, value):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    path = staged.output / "A2/run/worker/final/receipt.json"
    receipt = policy.read_json(path)
    receipt[field] = value
    atomic_write_json(path, receipt)
    summary = job.package(staged.output)
    assert summary["artifacts"]["A2"]["status"] == "missing_or_invalid"
    monkeypatch.delenv(provider.KEY_ENV)
    result = job.grade(staged.output / "public", staged.output / "grade")
    assert result["arms"]["A2"]["verdict"] == "INCONCLUSIVE"


def test_corrupted_feedback_bytes_are_not_current_revision_evidence(staged):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    path = staged.output / "A2/run/worker/feedback/0001.json"
    receipt = policy.read_json(path)
    receipt["feedback"]["reason"] = "check_failed"
    atomic_write_json(path, receipt)
    summary = job.package(staged.output)
    assert summary["artifacts"]["A2"]["status"] == "missing_or_invalid"


def test_final_grade_uses_captured_public_freeze_not_revoked_live_comment(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    def offline_only(*, fetch, now):
        assert now == 0
        assert fetch(123)["body"] == "offline frozen public fixture"
        return staged.authorization, {"offline": True}
    monkeypatch.setattr(policy, "frozen_authorization", offline_only)
    monkeypatch.setattr(policy, "fetch_comment", Mock(side_effect=AssertionError("no live fetch")))
    result = job.grade(staged.output / "public", staged.output / "grade")
    assert all(a["semantic"]["verdict"] == "PASS" for a in result["arms"].values())


@pytest.mark.parametrize("failure", ["exception", "duplicate_keys", "oversize", "late"])
def test_controller_http_response_failure_is_bounded_redacted_and_never_retried(failure):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def read1(self, size):
            if failure == "duplicate_keys":
                raw, self.raw = getattr(self, "raw", b'{"x":1,"x":2}'), b""
                return raw
            if failure == "late":
                api.deadline = time.monotonic() - 1
                return b"{}"
            return b"x" * size
    opener = Mock()
    opener.open.side_effect = (OSError("OFFLINE-FAKE never retain")
                              if failure == "exception" else None)
    opener.open.return_value = Response()
    api = job.DeadlineGitHub("OFFLINE-FAKE", time.monotonic() + 30, opener=opener)
    with pytest.raises(ValueError, match="response unavailable") as error:
        api.request("GET", "")
    assert "OFFLINE-FAKE" not in str(error.value)
    assert opener.open.call_count == 1


def test_pre_execution_rejection_retains_inconclusive_grade(staged, monkeypatch):
    summary = job.package(staged.output)  # Successful prepare but execute was never admitted.
    assert summary["execution"] == {}
    monkeypatch.delenv(provider.KEY_ENV)
    grader = Mock(side_effect=AssertionError("unbound candidates must not be graded"))
    monkeypatch.setattr(job.workbench, "grade_final", grader)
    result = job.grade(staged.output / "public", staged.output / "grade")
    assert all(a["reason"] == "invalid_execution_identity" for a in result["arms"].values())
    assert (staged.output / "grade/grade.json").is_file()
    grader.assert_not_called()


@pytest.mark.parametrize("change", ["none", "inventory", "mounts", "inconclusive"])
def test_same_host_runtime_must_match_actual_qualified_profile(tmp_path, monkeypatch, change):
    import sys

    import tools
    expected = {"verdict": "PASS", "inventory_sha256": "a" * 64, "mount_count": 4}
    actual = dict(expected)
    if change == "inventory":
        actual["inventory_sha256"] = "b" * 64
    elif change == "mounts":
        actual["mount_count"] = 5
    elif change == "inconclusive":
        actual["verdict"] = "INCONCLUSIVE"
    runtime = SimpleNamespace(qualify=lambda *a, **kw: actual)
    monkeypatch.setitem(sys.modules, "tools.kv_runtime_qualification", runtime)
    monkeypatch.setattr(tools, "kv_runtime_qualification", runtime, raising=False)
    monkeypatch.setattr(policy, "validate_qualification", lambda _: {"runtime_isolation": expected,
        "dependencies": {"src/inferrsi/harness/skill_eval_engineering.py": "c" * 64}})
    if change in {"none", "inventory"}:
        result = job.runtime_preflight(tmp_path, time.monotonic() + 30, {})
        assert result["verdict"] == "PASS"
        assert result["inventory_sha256"] == actual["inventory_sha256"]
        assert result["qualified_inventory_sha256"] == expected["inventory_sha256"]
        assert result["profile_source_sha256"] == "c" * 64
    else:
        with pytest.raises(ValueError, match="runtime/profile"):
            job.runtime_preflight(tmp_path, time.monotonic() + 30, {})


def retained_fake_sandbox(source, payload, output, deadline):
    record, actual = fake_sandbox(source, payload, output, deadline)
    # Mimic the real executor's fixed filenames, including deliberately excluded text.
    (output / "stdout.log").write_bytes(provider.canonical(actual).encode())
    (output / "stderr.log").write_text("OFFLINE-PRIVATE-CANARY")
    (output / "unrequested.json").write_text('"OFFLINE-PRIVATE-CANARY"')
    atomic_write_json(output / "execution.json", {"status": record["status"],
        "returncode": 0, "elapsed_seconds": record["elapsed_seconds"]})
    return {**record, "returncode": 0, "argv": ["OFFLINE-PRIVATE-CANARY"],
            "cwd": "OFFLINE-PRIVATE-CANARY", "error": "OFFLINE-PRIVATE-CANARY"}, actual


def test_final_artifact_reconstructs_original_semantics_and_abba_samples(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    monkeypatch.setattr(kv, "invoke", retained_fake_sandbox)
    result = job.grade(staged.output / "public", staged.output / "grade")
    public = staged.output / "grade/public"
    manifest = policy.read_json(public / "evidence.json")
    assert manifest["execution"]["run_id"] == "123"
    assert policy.read_json(public / "authorization.json")["body"].startswith("offline")
    assert policy.read_json(public / "grade.json") == result
    for arm in ("A2", "A3"):
        evidence = manifest["arms"][arm]
        assert evidence["raw_outputs_complete"]
        assert len(evidence["semantics"]) == 1 and len(evidence["performance"]) == 17
        assert evidence["semantics"][0]["check"] is True
        assert evidence["semantics"][0]["execution"] == {
            "status": "completed", "returncode": 0, "elapsed_seconds": 1.0}
        for row in evidence["semantics"] + evidence["performance"]:
            raw = (public / row["output"]["path"]).read_bytes()
            assert policy.sha(raw) == row["output"]["sha256"]
            assert len(raw) == row["output"]["bytes"]
            assert policy.fingerprint(json.loads(raw)) == row["output"]["data_sha256"]
        assert [r["side"] for r in evidence["performance"][:4]] == [
            "baseline", "candidate", "candidate", "baseline"]
        for side in ("baseline", "candidate"):
            observed = [r["execution"]["metric"] for r in evidence["performance"]
                        if r["side"] == side and r["phase"] == "measurement"]
            assert observed == result["arms"][arm]["performance"][side + "_values"]
        assert all(r["source_verified"] and r["execution"]["returncode"] == 0
                   for r in evidence["performance"])
        assert all(r["output"]["data_sha256"] == r["expected_sha256"]
                   for r in evidence["performance"])
    published = b"".join(p.read_bytes() for p in public.rglob("*") if p.is_file())
    assert b"OFFLINE-PRIVATE-CANARY" not in published
    assert b"OFFLINE-FAKE-PROVIDER-KEY" not in published
    assert str(staged.output).encode() not in published
    assert not list(public.rglob("*.log"))


@pytest.mark.parametrize("bad", [b'not JSON OFFLINE-PRIVATE-CANARY',
    b'{"observations":[],"pending":[],"extra":"OFFLINE-PRIVATE-CANARY"}',
    b'{"observations":[],"pending":[["OFFLINE-PRIVATE-CANARY",0,[]]]}',
    b'{"observations":[],"pending":[],"pending":[]}',
    b'{"observations":[],"pending":[[[],0,[]]]}'])
def test_raw_projection_never_uploads_arbitrary_or_malformed_output(tmp_path, bad):
    source, target = tmp_path / "raw", tmp_path / "published.json"
    source.write_bytes(bad)
    result = job._raw_kv_output(source, target, [], verify=True, remaining=[1024])
    assert result["status"] == "redacted_invalid_output"
    assert not target.exists()
    assert result["sha256"] == policy.sha(bad) and result["bytes"] == len(bad)
    assert result["truncated"] is False
    assert "OFFLINE-PRIVATE-CANARY" not in provider.canonical(result)


@pytest.mark.parametrize("unsafe", ["symlink", "oversize", "whole_budget"])
def test_raw_projection_file_and_total_limits(tmp_path, unsafe):
    source, target = tmp_path / "raw", tmp_path / "published.json"
    good = b'{"observations":[],"pending":[]}'
    if unsafe == "symlink":
        (tmp_path / "other").write_bytes(good)
        source.symlink_to(tmp_path / "other")
    else:
        source.write_bytes(good if unsafe == "whole_budget" else b" " * (4 * policy.MAX_JSON + 1))
    result = job._raw_kv_output(source, target, [], verify=True, remaining=[1])
    assert result["status"] != "retained" and not target.exists()


def test_all_frozen_hidden_expected_outputs_fit_public_projection(tmp_path):
    # Real frozen DATA only; this does not execute a candidate or re-author the oracle.
    root = Path(__file__).parents[1]
    frozen = policy.read_json(root / (
        "evidence/kv-reclamation-20261030/validator/independent/fixtures.json"))
    traces = [t for t in frozen["traces"] if t["split"] == "grader"]
    assert len(traces) == 77
    remaining = [32 * policy.MAX_JSON]
    for index, trace in enumerate(traces):
        expected = {"observations": trace["expected"],
                    "pending": trace["expected"][-1]["pending"] if trace["expected"] else []}
        raw = provider.canonical(expected).encode()
        source, target = tmp_path / "source", tmp_path / f"trace-{index:03d}.json"
        source.write_bytes(raw)
        result = job._raw_kv_output(source, target, trace["events"],
                                    verify=True, remaining=remaining)
        assert result["status"] == "retained", trace["id"]
        assert target.read_bytes() == raw


def test_partial_preflight_retains_failed_stage_without_exception_text(staged, monkeypatch):
    monkeypatch.delenv(provider.KEY_ENV)
    monkeypatch.setattr(policy, "fetch_comment", lambda _: {"id": 123, "body": "offline",
        "issue_url": "https://example.invalid/public", "user": {"login": "owner", "type": "User"}})
    def frozen(*, fetch=None, **kwargs):
        if fetch is not None:
            fetch(123)
        return staged.authorization, {"offline": True}
    monkeypatch.setattr(policy, "frozen_authorization", frozen)
    monkeypatch.setattr(kv, "probe_isolation",
                        Mock(side_effect=ValueError("OFFLINE-PRIVATE-CANARY")))
    fresh = staged.output.parent / "failed-prepare"
    with pytest.raises(ValueError):
        job.prepare(fresh)
    job.package(fresh)
    proof = policy.read_json(fresh / "public/preflight.json")
    assert proof["status"] == "partial" and proof["stages"]["stage"] == "completed"
    assert proof["stages"]["isolation"] == "failed_or_interrupted"
    assert proof["stages"]["cleanup"] == "not_started"
    assert "OFFLINE-PRIVATE-CANARY" not in provider.canonical(proof)


def test_preflight_projection_excludes_arbitrary_nested_text(staged):
    path = staged.output / "prepared.json"
    value = policy.read_json(path)
    value["runtime_profile"].update(inventory_sha256="a" * 64,
        error="OFFLINE-PRIVATE-CANARY", environment={"KEY": "OFFLINE-PRIVATE-CANARY"},
        probe={"network_blocked": True, "inaccessible": [True, False],
               "unexpected": "OFFLINE-PRIVATE-CANARY"})
    value["cleanup"]["cases"] = {mode: {"verdict": "FAIL", "surviving_descendants": 1,
        "error": "OFFLINE-PRIVATE-CANARY"} for mode in ("normal", "timeout", "cancel")}
    atomic_write_json(path, value)
    job.package(staged.output)
    proof = policy.read_json(staged.output / "public/preflight.json")
    assert proof["proofs"]["runtime_profile"]["probe"]["inaccessible"] == [True, False]
    assert proof["proofs"]["cleanup"]["cases"]["normal"]["surviving_descendants"] == 1
    assert "OFFLINE-PRIVATE-CANARY" not in provider.canonical(proof)


def test_interrupted_grader_keeps_first_outputs_and_explicit_unstarted_arm(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    monkeypatch.setattr(kv, "invoke", retained_fake_sandbox)
    original = job.workbench.grade_final
    def interrupted(*args):
        original(*args)
        raise KeyboardInterrupt
    monkeypatch.setattr(job.workbench, "grade_final", interrupted)
    with pytest.raises(KeyboardInterrupt):
        job.grade(staged.output / "public", staged.output / "grade")
    public = staged.output / "grade/public"
    result = policy.read_json(public / "grade.json")
    assert result["arms"]["A2"]["reason"] == "grading_interrupted"
    assert result["arms"]["A3"]["reason"] == "not_evaluated"
    evidence = policy.read_json(public / "evidence.json")["arms"]
    assert evidence["A2"]["semantics"][0]["output"]["status"] == "retained"
    assert not evidence["A3"]["raw_outputs_complete"]


def test_always_projection_recovers_failed_projection_without_any_reexecution(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    monkeypatch.setattr(kv, "invoke", retained_fake_sandbox)
    original = job._raw_kv_output
    monkeypatch.setattr(job, "_raw_kv_output",
                        Mock(side_effect=RuntimeError("projection interrupted")))
    with pytest.raises(RuntimeError, match="projection interrupted"):
        job.grade(staged.output / "public", staged.output / "grade")
    public = staged.output / "grade/public"
    assert policy.read_json(public / "projection.json")["status"] == "failed_or_interrupted"
    first = (staged.output / "grade/A2/semantics/trace-000/stdout.log").read_bytes()
    monkeypatch.setattr(job, "_raw_kv_output", original)
    monkeypatch.setattr(kv, "invoke", Mock(side_effect=AssertionError("no candidate rerun")))
    result = job.package_grade(staged.output / "public", staged.output / "grade")
    assert all(arm["raw_outputs_complete"] for arm in result["arms"].values())
    assert (public / "A2/semantics/trace-000.json").read_bytes() == first
    assert policy.read_json(public / "projection.json")["status"] == "completed"
    grade = policy.read_json(public / "grade.json")
    assert grade["arms"]["A2"]["semantic"]["verdict"] == "PASS"
    assert "verdict" not in grade["arms"]["A2"]  # No invented aggregate verdict.


def test_always_projection_keeps_raw_partial_output_without_finally(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    grade = staged.output / "grade"
    retained_fake_sandbox(BASELINE, {"mode": "verify", "events": []},
                         grade / "A2/semantics/trace-000", time.monotonic() + 10)
    monkeypatch.setattr(kv, "invoke", Mock(side_effect=AssertionError("no candidate rerun")))
    manifest = job.package_grade(staged.output / "public", grade)
    assert manifest["arms"]["A2"]["semantics"][0]["output"]["status"] == "retained"
    assert manifest["arms"]["A2"]["semantics"][0]["check"] is None
    assert not manifest["arms"]["A2"]["raw_outputs_complete"]
    assert all(arm["verdict"] == "INCONCLUSIVE"
               for arm in policy.read_json(grade / "public/grade.json")["arms"].values())


def test_grade_projection_retains_failed_and_skipped_timing_rows(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    def failed(source, payload, output, deadline):
        record, actual = retained_fake_sandbox(source, payload, output, deadline)
        if payload["mode"] == "benchmark":
            record.update(status="timeout", returncode=-9)
        return record, actual
    monkeypatch.setattr(kv, "invoke", failed)
    result = job.grade(staged.output / "public", staged.output / "grade")
    assert result["arms"]["A2"]["performance"]["verdict"] == "INCONCLUSIVE"
    rows = policy.read_json(staged.output / "grade/public/evidence.json")["arms"]["A2"]
    assert len(rows["performance"]) == 17
    assert rows["performance"][0]["execution"]["status"] == "timeout"
    assert rows["performance"][0]["execution"]["returncode"] == -9
    assert all(row["execution"]["status"] == "unavailable" for row in rows["performance"][1:])
    assert not rows["raw_outputs_complete"]


@pytest.mark.parametrize("corruption", ["run", "locator", "workspace"])
def test_preflight_projection_rejects_unbound_or_private_prepared_fields(staged, corruption):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    path = staged.output / "prepared.json"
    value = policy.read_json(path)
    if corruption == "run":
        value["run_id"] = "9999"
    elif corruption == "locator":
        value["locator_sha256"] = "0" * 64
    else:
        value["inputs"]["A2/workspace/task.json"] = "OFFLINE-PRIVATE-CANARY"
    atomic_write_json(path, value)
    job.package(staged.output)
    projected = policy.read_json(staged.output / "public/preflight.json")
    assert projected["status"] != "prepared"
    assert "OFFLINE-PRIVATE-CANARY" not in provider.canonical(projected)


def test_always_projection_rejects_corrupt_grade_text_and_false_pass(staged, monkeypatch):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    output = staged.output / "grade"
    output.mkdir()
    atomic_write_json(output / "grade.json", {"schema": "kv-live-final-grade-v1",
        "plan_sha256": staged.authorization["plan_sha256"], "scope": "OFFLINE-PRIVATE-CANARY",
        "arms": {a: {"reason": "OFFLINE-PRIVATE-CANARY", "semantic": {
            "verdict": "PASS", "checks": {TRACE["id"]: False}, "artifact_sha256": "a" * 64,
            "environment": "OFFLINE-PRIVATE-CANARY"}} for a in ("A2", "A3")}})
    monkeypatch.setattr(kv, "invoke", Mock(side_effect=AssertionError("no candidate rerun")))
    job.package_grade(staged.output / "public", output)
    raw = (output / "public/grade.json").read_bytes()
    assert b"OFFLINE-PRIVATE-CANARY" not in raw
    assert all(a["verdict"] == "INCONCLUSIVE" for a in json.loads(raw)["arms"].values())


@pytest.mark.parametrize("credential", [provider.KEY_ENV, "GITHUB_TOKEN"])
def test_always_projection_rejects_injected_secrets(tmp_path, monkeypatch, credential):
    monkeypatch.setenv(credential, "OFFLINE-FAKE")
    with pytest.raises(ValueError, match="without injected"):
        job.package_grade(tmp_path / "bundle", tmp_path / "output")


@pytest.mark.parametrize("receipt", ["failed", "absent", "unexpected_fields"])
def test_trace_exit_failure_cannot_be_upgraded_by_correct_stdout(staged, monkeypatch, receipt):
    job.execute(staged.output, api=SimpleNamespace(), stores=(staged.world.daily, staged.world.pr),
        launch=launcher([read_task(), work(CANDIDATE), submit()], []))
    job.package(staged.output)
    monkeypatch.delenv(provider.KEY_ENV)
    def failure(source, payload, output, deadline):
        record, actual = retained_fake_sandbox(source, payload, output, deadline)
        if payload["mode"] != "verify":
            return record, actual
        record.update(status="failed", returncode=1)
        path = output / "execution.json"
        if receipt == "failed":
            atomic_write_json(path, {k: record[k] for k in
                ("status", "returncode", "elapsed_seconds")})
        elif receipt == "absent":
            path.unlink()  # Process loss before first receipt cannot imply successful exit.
        else:
            atomic_write_json(path, {**record, "secret": "OFFLINE-PRIVATE-CANARY"})
        return record, None  # Real invoke rejects a nonzero exit even with valid JSON.
    monkeypatch.setattr(kv, "invoke", failure)
    result = job.grade(staged.output / "public", staged.output / "grade")
    assert result["arms"]["A2"]["semantic"]["verdict"] == "FAIL"
    row = policy.read_json(staged.output / "grade/public/evidence.json")[
        "arms"]["A2"]["semantics"][0]
    assert row["output"]["status"] == "retained" and row["check"] is False
    assert row["execution"]["status"] == ("failed" if receipt == "failed" else "unavailable")
    if receipt == "failed":
        assert row["execution"]["returncode"] == 1
    assert "OFFLINE-PRIVATE-CANARY" not in provider.canonical(row)
