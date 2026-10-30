"""Fixed actor qualifier controls; fake worker outputs are not host qualification."""

import json
import zipfile

import pytest
import yaml

from inferrsi.model import anthropic_edit_agent as edit
from tools import qualify_kv_edit_actor as qualify

PLAN = qualify.ROOT / "evidence/kv-actor-qualification-20261030/plan/qualification-plan.json"


def identity():
    return {"available": True, "head": "a" * 40, "snapshot_hash": "exact", "dirty": False}


def fake_worker(inputs, workspace, output, deadline):
    config = json.loads((inputs / "worker.json").read_text())
    scripts = json.loads((inputs / "responses.json").read_text())
    source = scripts[-2]["content"][0]["input"]["source"].encode()
    final = output / "worker/final"
    final.mkdir(parents=True)
    (final / "candidate.py").write_bytes(source)
    # Parent final grader must use final bytes, not this later live-path mutation.
    (workspace / "candidate.py").write_bytes(b"# later live actor path\n")
    for i in (0, 1, 2):
        directory = output / f"worker/workbench/revisions/revision-{i:04d}"
        directory.mkdir(parents=True)
        (directory / "candidate.py").write_bytes(source)
    return {
        "execution": {"status": "completed"},
        "worker": {
            "status": "completed",
            "artifact": {"sha256": edit.digest(source), "revision": 2},
        },
        "simulated_slots_consumed": 4,
        "request_completion_known": True,
        "config": config,
    }


def test_fixed_actual_owner_exposure_and_separate_final_grade(tmp_path, monkeypatch):
    monkeypatch.setattr(qualify, "repository_identity", lambda *_: identity())
    monkeypatch.setattr(qualify.runtime, "qualify", lambda *a, **k: {"verdict": "PASS"})
    monkeypatch.setattr(qualify.cleanup, "qualify", lambda *_: {"verdict": "PASS"})
    monkeypatch.setattr(qualify.pilot, "run_supervised", fake_worker)
    monkeypatch.setattr(qualify, "visible_receipts", lambda *_: True)
    seen = []

    def grade(source, digest, hidden, output, deadline):
        assert edit.digest(source) == digest
        assert b"later live actor path" not in source
        assert all(t["split"] == "grader" for t in hidden)
        seen.append(source)
        return {"verdict": "PASS"}

    monkeypatch.setattr(qualify.workbench, "grade_final", grade)
    result = qualify.qualify(PLAN, "a" * 40, tmp_path / "out")
    assert result["verdict"] == "PASS" and result["software_checks_passed"]
    assert result["model_calls"] == 0 and len(seen) == 2
    assert not any(f["path"].startswith("knowledge/") for f in result["arms"]["A2"]["exposure"])
    names = {f["path"] for f in result["arms"]["A3"]["exposure"]}
    assert names == {
        "task.json",
        "candidate.py",
        "CONTRACT.md",
        "workbench.md",
        "development.json",
        "knowledge/SKILL.md",
        "knowledge/metadata.json",
        "knowledge/references/source-notes.md",
    }
    common = qualify.shared_inputs.COMMON
    a2 = {f["path"]: f for f in result["arms"]["A2"]["exposure"]}
    a3 = {f["path"]: f for f in result["arms"]["A3"]["exposure"]}
    assert {p: a2[p] for p in common} == {p: a3[p] for p in common}
    assert result["arms"]["A2"]["prompt_sha256"] == result["arms"]["A3"]["prompt_sha256"]
    assert all(f["bytes"] <= qualify.checked_plan(PLAN)["client"]["max_read_bytes"]
               for f in a3.values())
    with zipfile.ZipFile(tmp_path / "out/raw-evidence.zip") as archive:
        raw = "\n".join(archive.read(name).decode() for name in archive.namelist())
        assert str(tmp_path) not in raw
        assert "<QUALIFICATION_WORK>" in raw or "scripted" in raw
        assert any(name.endswith("candidate.py") for name in archive.namelist())


def test_unavailable_worker_is_not_pass_and_does_not_grade(tmp_path, monkeypatch):
    monkeypatch.setattr(qualify, "repository_identity", lambda *_: identity())
    monkeypatch.setattr(qualify.runtime, "qualify", lambda *a, **k: {"verdict": "PASS"})
    monkeypatch.setattr(qualify.cleanup, "qualify", lambda *_: {"verdict": "INCONCLUSIVE"})
    monkeypatch.setattr(
        qualify.pilot,
        "run_supervised",
        lambda *_: {
            "execution": {"status": "failed"},
            "worker": {"status": "inconclusive", "reason": "sandbox_unavailable"},
            "simulated_slots_consumed": 0,
            "request_completion_known": True,
        },
    )
    monkeypatch.setattr(qualify.workbench, "grade_final", lambda *_: pytest.fail("not submitted"))
    result = qualify.qualify(PLAN, "a" * 40, tmp_path / "out")
    assert result["verdict"] == "INCONCLUSIVE" and not result["software_checks_passed"]
    assert all(a["simulated_slots_consumed"] == 0 for a in result["arms"].values())


def test_worker_receipt_cannot_override_failed_outer_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(qualify, "repository_identity", lambda *_: identity())
    monkeypatch.setattr(qualify.runtime, "qualify", lambda *a, **k: {"verdict": "PASS"})
    monkeypatch.setattr(qualify.cleanup, "qualify", lambda *_: {"verdict": "PASS"})
    monkeypatch.setattr(qualify, "visible_receipts", lambda *_: True)
    monkeypatch.setattr(qualify.workbench, "grade_final", lambda *_: {"verdict": "PASS"})

    def failed_worker(*args):
        return {**fake_worker(*args), "execution": {"status": "failed"}}

    monkeypatch.setattr(qualify.pilot, "run_supervised", failed_worker)
    result = qualify.qualify(PLAN, "a" * 40, tmp_path / "out")
    assert result["verdict"] == "INCONCLUSIVE" and not result["software_checks_passed"]


def test_current_clean_exact_revision_is_required(tmp_path, monkeypatch):
    monkeypatch.setattr(qualify, "repository_identity", lambda *_: {**identity(), "dirty": True})
    with pytest.raises(ValueError, match="clean Git revision"):
        qualify.qualify(PLAN, "a" * 40, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_outbound_owner_links_cannot_expand_allowlist(tmp_path):
    plan = json.loads(PLAN.read_text())
    plan["knowledge_files_sha256"]["../SKILL.md"] = "a" * 64
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="complete pinned K owner"):
        qualify.checked_plan(path)


def test_qualification_reuses_1800_workload_not_a_post_outcome_choice():
    plan = qualify.checked_plan(PLAN)
    task_plan = qualify.task.checked_plan(qualify.TASK_PLAN)
    assert plan["visible_workload_count"] == task_plan["timing"]["lease_count"] == 1800
    assert plan["actor_limits"]["max_seconds"] == 600


def test_existing_ready_job_only_adds_secret_free_separate_receipt():
    workflow = yaml.safe_load((qualify.ROOT / ".github/workflows/ci-ready.yml").read_text())
    job = workflow["jobs"]["kv-task-qualification"]
    assert job["runs-on"] == "ubuntu-22.04" and job["permissions"] == {"contents": "read"}
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "tools.qualify_kv_edit_actor" in commands and "env -i" in commands
    assert "secrets." not in commands and "send_message" not in commands
    assert "--privileged" not in commands and "sysctl" not in commands
    uploads = [s["with"] for s in job["steps"] if "upload-artifact" in s.get("uses", "")]
    assert len(uploads) == 2 and uploads[0]["name"].startswith("kv-qualification-")
    assert uploads[1]["name"].startswith("kv-actor-qualification-")


def receipt_fixture(tmp_path):
    actor = "a" * 64
    revisions = tmp_path / "revisions"
    sources = {r: f"# Scripted revision {r}\n".encode() for r in (0, 1, 2)}
    for revision, source in sources.items():
        directory = revisions / f"revision-{revision:04d}"
        directory.mkdir(parents=True)
        (directory / "candidate.py").write_bytes(source)
    artifact = {
        "revision": 2,
        "sha256": edit.digest(sources[2]),
        "plan_sha256": "c" * 64,
        "execution_id": "fixture",
        "arm": "A2",
    }
    events = []
    for revision, source in sources.items():
        metadata = {"revision": revision, "sha256": edit.digest(source),
                    "actor_sha256": actor, "artifact": "candidate.py",
                    **{k: artifact[k] for k in ("plan_sha256", "execution_id", "arm")}}
        (revisions / f"revision-{revision:04d}/receipt.json").write_text(json.dumps(metadata))
        events.append({"type": "edit.artifact", "bytes": len(source), **metadata})
    for revision in (1, 2):
        for kind in ("checks", "benchmark"):
            feedback = (
                {"verdict": "PASS"}
                if kind == "checks"
                else {
                    "verdict": "FAIL",
                    "quality_verdict": "PASS",
                    "baseline_values": [1, 1],
                    "candidate_values": [1, 1],
                    "improvement_pct": 0,
                }
            )
            receipt = {
                "revision": revision,
                "kind": kind,
                "feedback": feedback,
                "artifact_sha256": edit.digest(sources[revision]),
                **{k: artifact[k] for k in ("plan_sha256", "execution_id", "arm")},
            }
            receipt["receipt_sha256"] = edit.fingerprint({**receipt, "actor_sha256": actor})
            events.append({"type": "agent.tool", "receipt": receipt})
            if revision == 2:
                artifact["check_receipt" if kind == "checks" else "benchmark_receipt"] = receipt[
                    "receipt_sha256"
                ]
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))
    return path, artifact, actor, revisions, events


def test_numeric_gain_is_not_required_by_receipt_readback(tmp_path):
    path, artifact, actor, revisions, events = receipt_fixture(tmp_path)
    assert qualify.visible_receipts(path, artifact, actor, 2, revisions)
    events[-1]["receipt"]["feedback"]["quality_verdict"] = "FAIL"
    path.write_text("\n".join(json.dumps(e) for e in events))
    assert not qualify.visible_receipts(path, artifact, actor, 2, revisions)


@pytest.mark.parametrize("variant", ["duplicate_final", "wrong_binding", "retained_drift",
                                    "retained_receipt_drift", "initial_source_drift"])
def test_receipt_readback_requires_both_bound_revisions_and_retained_bytes(tmp_path, variant):
    path, artifact, actor, revisions, events = receipt_fixture(tmp_path)
    if variant == "duplicate_final":
        events[3:5] = events[5:]
    elif variant == "wrong_binding":
        receipt = events[3]["receipt"]
        receipt["arm"] = "A3"
        body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        receipt["receipt_sha256"] = edit.fingerprint({**body, "actor_sha256": actor})
    elif variant == "retained_drift":
        (revisions / "revision-0001/candidate.py").write_text("# changed retained bytes\n")
    elif variant == "retained_receipt_drift":
        (revisions / "revision-0001/receipt.json").write_text("{}")
    else:
        (revisions / "revision-0000/candidate.py").write_text("# changed initial source\n")
    path.write_text("\n".join(json.dumps(e) for e in events))
    assert not qualify.visible_receipts(path, artifact, actor, 2, revisions)


def test_runtime_visibility_failure_cannot_be_hidden_by_good_scripted_arms(tmp_path, monkeypatch):
    monkeypatch.setattr(qualify, "repository_identity", lambda *_: identity())
    monkeypatch.setattr(qualify.cleanup, "qualify", lambda *_: {"verdict": "PASS"})
    monkeypatch.setattr(qualify.runtime, "qualify", lambda *a, **k: {"verdict": "FAIL"})
    monkeypatch.setattr(qualify.pilot, "run_supervised", fake_worker)
    monkeypatch.setattr(qualify, "visible_receipts", lambda *_: True)
    monkeypatch.setattr(qualify.workbench, "grade_final", lambda *_: {"verdict": "PASS"})
    result = qualify.qualify(PLAN, "a" * 40, tmp_path / "out")
    assert result["verdict"] == "FAIL" and not result["software_checks_passed"]
    assert result["dependencies_sha256"] == edit.fingerprint(result["dependencies"])


def test_dependency_receipt_binds_transitive_identity_metrics_budget_and_initializers():
    assert {
        "src/inferrsi/infra/targets/git.py", "src/inferrsi/infra/targets/__init__.py",
        "src/inferrsi/model/protocols/metrics.py", "src/inferrsi/harness/scenarios/external.py",
        "tools/skill_eval_budget.py", "tools/kv_edit_inputs.py", "tools/kv_worker_supervisor.py",
        "src/inferrsi/__init__.py",
    } <= qualify.dependencies().keys()
