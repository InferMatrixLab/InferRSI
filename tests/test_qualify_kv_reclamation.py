"""Model-free controller tests; mocked timing values are not performance evidence."""

import json
import os
import subprocess
import sys
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from tools import qualify_kv_reclamation as qualify

PLAN = qualify.EVIDENCE / "plan/qualification-plan.json"


def control_results():
    plan = qualify.checked_plan(PLAN)
    return ([{"verdict": "PASS", "checks": {"fixture": True}}
             for _ in plan["required_good"]]
            + [{"verdict": "FAIL", "checks": {"fixture": False}}
               for _ in plan["required_bad"]])


def module(name, path):
    if name == "kv_independent_verifier":
        return SimpleNamespace(load_traces=lambda: [{"split": "development"}], compare=lambda: True)
    if name == "kv_workload":
        return SimpleNamespace(workload=lambda count: [])
    return SimpleNamespace(benchmark_expected=lambda count: {"observations": [], "pending": []})


def measurement(name, *args):
    gain = 50 if name == "reference" else 0
    return {"evaluation": {"verdict": "PASS" if gain else "FAIL", "improvement_pct": gain},
            "records": []}


def test_full_qualification_requires_good_bad_integrity_deadline_and_headroom(tmp_path):
    identity = {"available": True, "head": "a" * 40, "snapshot_hash": "frozen", "dirty": False}
    with patch.object(qualify, "repository_identity", return_value=identity), \
         patch.object(qualify.kv, "probe_isolation", return_value={"readonly": True}), \
         patch.object(qualify.kv, "verify_source", side_effect=control_results()), \
         patch.object(qualify.kv, "invoke", return_value=(
             {"status": "timeout", "elapsed_seconds": 0.3}, None)), \
         patch.object(qualify.kv, "process_group_gone", return_value=True), \
         patch.object(qualify, "load_module", side_effect=module), \
         patch.object(qualify, "file_hash", wraps=qualify.file_hash) as hashes, \
         patch.object(qualify, "measure", side_effect=measurement):
        result = qualify.qualify(PLAN, "a" * 40, tmp_path / "output")
    assert result["verdict"] == "PASS"
    assert result["software_checks_passed"]
    assert len(result["control_source_sha256"]) == 9
    assert hashes.call_count > 5


def test_unavailable_is_retained_inconclusive_and_no_controls_run(tmp_path):
    identity = {"available": True, "head": "a" * 40, "snapshot_hash": "frozen", "dirty": False}
    with patch.object(qualify, "repository_identity", return_value=identity), \
         patch.object(qualify.kv, "probe_isolation", side_effect=qualify.kv.SandboxUnavailable(
             "unavailable")), patch.object(qualify.kv, "verify_source") as verify:
        result = qualify.qualify(PLAN, "a" * 40, tmp_path / "output")
    verify.assert_not_called()
    assert result["verdict"] == "INCONCLUSIVE"
    assert not result["software_checks_passed"]
    assert json.loads((tmp_path / "output/qualification.json").read_text()) == result
    assert result["model_calls"] == 0 and result["provider_charges_usd"] == 0


def test_wrong_revision_is_rejected_before_execution(tmp_path):
    with pytest.raises(ValueError, match="exact"):
        qualify.qualify(PLAN, "b" * 40, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_frozen_plan_changed_input_fails(tmp_path):
    plan = json.loads(PLAN.read_text())
    plan["starter_sha256"] = "0" * 64
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="changed"):
        qualify.checked_plan(path)


def test_cli_does_not_turn_numeric_gate_into_general_ci_gate(tmp_path):
    result = {"verdict": "FAIL", "software_checks_passed": True}
    with patch("sys.argv", ["qualify", "--plan", str(PLAN), "--revision", "a" * 40,
                            "--output", str(tmp_path / "output")]), \
         patch.object(qualify, "qualify", return_value=result):
        assert qualify.main() == 0
        result["software_checks_passed"] = False
        assert qualify.main() == 1


def test_existing_ready_job_security_and_parser_default_preserved():
    root = qualify.ROOT
    workflow = yaml.safe_load((root / ".github/workflows/ci-ready.yml").read_text())
    job = workflow["jobs"]["kv-task-qualification"]
    assert job["runs-on"] == "ubuntu-22.04"
    assert job["permissions"] == {"contents": "read"}
    assert job["if"] == "github.event.pull_request.draft == false"
    assert job["steps"][0]["with"]["persist-credentials"] is False
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "env -i" in commands and "secrets." not in commands
    assert "sysctl" not in commands and "--privileged" not in commands
    assert "--plan evidence/kv-reclamation-20261030/plan/qualification-plan.json" in commands
    assert "/qualification.json" in job["steps"][-1]["with"]["path"]
    assert "/raw-evidence.zip" in job["steps"][-1]["with"]["path"]
    parser = (root / ".github/workflows/skill-eval-qualify.yml").read_text()
    assert "tools.skill_eval_qualify" in parser
    assert "kv_reclamation" not in parser


def test_independently_frozen_verifier_suite():
    result = subprocess.run([sys.executable, "-m", "pytest", "-q",
                             str(qualify.INDEPENDENT / "test_verifier.py")],
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_independently_frozen_benchmark_suite():
    result = subprocess.run([sys.executable, "-m", "pytest", "-q",
                             str(qualify.EVIDENCE / "validator/test_benchmark.py")],
                            env={**os.environ,
                                 "KV_FROZEN_ORACLE": str(qualify.INDEPENDENT / "oracle.py")},
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_retained_actual_outputs_have_labelled_path_redactions(tmp_path):
    private, output = tmp_path / "private", tmp_path / "output"
    private.mkdir()
    output.mkdir()
    original = {"source": str(qualify.ROOT / "candidate.py"), "output": str(private / "trial"),
                "cwd": "/tmp/kv-replay-example", "observations": [{"reclaimed": [1, 2]}]}
    (private / "actual.json").write_text(json.dumps(original))
    (private / "not-evidence.txt").write_text("not retained")
    receipt = qualify.retain_raw_evidence(private, output)
    with zipfile.ZipFile(output / receipt["path"]) as archive:
        value = json.loads(archive.read("actual.json"))
        assert value["observations"] == original["observations"]
        assert value["source"] == "<CHECKOUT>/candidate.py"
        assert value["output"] == "<RUN_OUTPUT>/trial"
        assert value["cwd"] == "<REPLAY_WORK>"
        assert "not-evidence.txt" not in archive.namelist()
    assert receipt["sha256"] == qualify.file_hash(output / receipt["path"])
