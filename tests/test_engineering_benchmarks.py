"""Real payload checks and consumer regressions; no model/device calls."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferrsi.harness.benchmarks import builtin_tasks, load_task, skill_verifier
from inferrsi.harness.benchmarks.consumers import grade_artifact, run_action
from inferrsi.harness.runner import run_experiment
from inferrsi.harness.scenarios.external import execute_trial
from inferrsi.harness.skill_evaluation import run_trial


@pytest.fixture
def numpy_runtime():
    return pytest.importorskip("numpy")


def read_result(execution):
    return json.loads(Path(execution["result_path"]).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["softmax-cpu", "rmsnorm-cpu"])
def test_real_baseline_candidate_measurement_and_profile(name, tmp_path, numpy_runtime):
    task = load_task(name)
    for role in ("baseline", "candidate"):
        candidate = task.root / (role + ".py")
        grade = grade_artifact(task, candidate, tmp_path / role, timeout_seconds=20)
        assert grade["verdict"] == "PASS"
        assert len(grade["checks"]["assertions"]) == 24
    candidate = task.root / "candidate.py"
    measured = read_result(
        run_action(task, candidate, "measure", tmp_path / "timed", timeout_seconds=20)
    )
    assert measured["passed"]
    assert measured["metrics"]["suite_latency_ms"] > 0
    assert len(measured["cases"]) == len(task.manifest["workloads"])
    assert all(len(c["samples_ms"]) == 5 for c in measured["cases"])
    profile = read_result(
        run_action(task, candidate, "profile", tmp_path / "profile", timeout_seconds=20)
    )
    assert "metrics" not in profile
    assert profile["diagnostic"]["performance_verdict"] is None
    assert "compute" in (tmp_path / "profile/profile.txt").read_text()


@pytest.mark.parametrize(
    "body",
    [
        "return np.zeros_like(x)",
        "return np.full_like(x, np.nan)",
        "return np.ones_like(x, dtype=np.float64)",
        "return np.ones((1,), dtype=np.float32)",
        "y = np.exp(x); return y / y.sum(axis=1, keepdims=True)",
        "x[:] = 0; return np.full_like(x, 1 / x.shape[1])",
        "y = np.exp(x - x.max(axis=0, keepdims=True)); return y / y.sum(axis=0, keepdims=True)",
    ],
)
def test_bad_candidates_cannot_supply_performance(body, tmp_path, numpy_runtime):
    candidate = tmp_path / "implementation.py"
    candidate.write_text("import numpy as np\ndef compute(x, *, eps):\n    " + body + "\n")
    task = load_task("softmax-cpu")
    grade = grade_artifact(task, candidate, tmp_path / "grade", timeout_seconds=20)
    assert grade["verdict"] == "FAIL"
    execution = run_action(task, candidate, "measure", tmp_path / "measure", timeout_seconds=20)
    assert execution["status"] == "failed"
    assert "metrics" not in read_result(execution)


def test_rmsnorm_last_axis_bug_detected(tmp_path, numpy_runtime):
    candidate = tmp_path / "implementation.py"
    candidate.write_text(
        "import numpy as np\ndef compute(x, *, eps):\n"
        "    return x / np.sqrt(np.mean(x*x, axis=-1, keepdims=True) + eps)\n"
    )
    assert (
        grade_artifact(load_task("rmsnorm-cpu"), candidate, tmp_path / "grade", timeout_seconds=20)[
            "verdict"
        ]
        == "FAIL"
    )


def test_checks_repeated_timed_calls_not_only_initial_call(tmp_path, numpy_runtime):
    candidate = tmp_path / "implementation.py"
    candidate.write_text(
        "import numpy as np\nn = 0\ndef compute(x, *, eps):\n"
        "    global n\n    n += 1\n"
        "    if n > 6: return np.zeros_like(x)\n"
        "    y = np.exp(x-x.max(axis=1,keepdims=True))\n"
        "    return y/y.sum(axis=1,keepdims=True)\n"
    )
    execution = run_action(
        load_task("softmax-cpu"), candidate, "measure", tmp_path / "run", timeout_seconds=20
    )
    assert execution["status"] == "failed"
    result = read_result(execution)
    assert not result["passed"] and "metrics" not in result


def test_frozen_package_and_candidate_drift(tmp_path, numpy_runtime):
    root = tmp_path / "package"
    shutil.copytree(load_task("softmax-cpu").root, root)
    task = load_task(root)
    candidate = root / "candidate.py"
    command = task.command("check", candidate)
    candidate.write_text(candidate.read_text() + "\n# changed\n")
    with pytest.raises(ValueError, match="changed"):
        task.command("check", candidate)
    execution = execute_trial(command, root, tmp_path / "run", time.monotonic() + 20, None)
    assert execution["status"] == "failed"
    assert read_result(execution)["status"] == "error"


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("adapter", "unknown"),
        ("environment", {"backend": "cuda", "runtime": "numpy", "dtype": "float32"}),
        ("coverage", []),
        ("workloads", []),
    ],
)
def test_unsupported_contract_rejected(field, value, tmp_path):
    root = tmp_path / "package"
    shutil.copytree(load_task("softmax-cpu").root, root)
    document = json.loads((root / "task.json").read_text(encoding="utf-8"))
    document[field] = value
    (root / "task.json").write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_task(root)


def test_descriptor_does_not_mutate_task():
    task = load_task("softmax-cpu")
    manifest = task.manifest
    manifest["oracle"]["axis"] = 0
    assert task.manifest["oracle"]["axis"] == 1
    assert set(builtin_tasks()) == {"softmax-cpu", "rmsnorm-cpu"}


def test_real_workbench_reuses_frozen_task(tmp_path, numpy_runtime):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    task = load_task("softmax-cpu")
    candidate = repo / "implementation.py"
    shutil.copyfile(task.root / "candidate.py", candidate)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    spec = task.runspec(
        candidate,
        repo=repo,
        output_dir=tmp_path / "runs",
        repetitions=2,
        max_minutes=1,
        min_improvement_pct=0,
    )
    run = run_experiment(spec, {"scope": "CPU software integration"})
    evaluation = json.loads((run / "evaluation.json").read_text())
    assert evaluation["source_integrity"]["verified"]
    assert evaluation["baseline"]["excluded_trials"] == 0
    assert evaluation["candidate"]["excluded_trials"] == 0
    assert evaluation["statistical_significance"] == "not established"
    events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
    assert [e["side"] for e in events if e["phase"] == "measurement"] == [
        "baseline",
        "candidate",
        "candidate",
        "baseline",
    ]
    identity = json.loads((run / "candidate/trial-001/result.json").read_text())["identity"]
    assert identity == task.identity(candidate)


class RetainedControl:
    """Local authored control for the real trial machinery; no model or token usage."""

    timeout_seconds = 20

    def __init__(self, identity):
        self.identity = identity

    def command(self, workspace, final, schema, prompt):
        script = (
            "import json, pathlib, sys; "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'candidate_sha256':sys.argv[2]})); "
            "print(json.dumps({'type':'turn.completed'}))"
        )
        return sys.executable, "-B", "-c", script, str(final), self.identity


@pytest.mark.parametrize("good", [True, False])
def test_actual_skilleval_trial_uses_same_oracle(good, tmp_path, numpy_runtime):
    package = load_task("softmax-cpu")
    candidate = tmp_path / "implementation.py"
    candidate.write_text(
        (package.root / "candidate.py").read_text()
        if good
        else "import numpy as np\ndef compute(x, *, eps): return np.zeros_like(x)\n"
    )
    task = skill_verifier.task_descriptor(package, candidate)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "task.json").write_text(json.dumps(task))
    client = RetainedControl(task["benchmark"]["identity"]["candidate_sha256"])
    record = run_trial(
        client,
        task,
        "N",
        1,
        workspace,
        tmp_path / "trial",
        tmp_path / "unused-schema.json",
        Path(skill_verifier.__file__),
        "Offline authored control",
        time.monotonic() + 30,
    )
    assert record["verdict"] == ("PASS" if good else "FAIL")
    assert record["inputs_unchanged"]
    assert record["observations"]["usage"] is None
    raw = json.loads((tmp_path / "trial/verification/artifact/result.json").read_text())
    assert raw["identity"] == task["benchmark"]["identity"]


def test_missing_numpy_has_no_fallback(tmp_path):
    # An import blocker exercises dependency failure in a real worker process.
    blocker = tmp_path / "numpy.py"
    blocker.write_text("raise ImportError('numpy deliberately unavailable')\n")
    task = load_task("softmax-cpu")
    result = tmp_path / "result.json"
    env = {**os.environ, "PYTHONPATH": str(tmp_path), "INFERRSI_RESULT_PATH": str(result)}
    process = subprocess.run(
        task.command("measure", task.root / "candidate.py"),
        env=env,
        cwd=tmp_path,
        capture_output=True,
    )
    assert process.returncode == 1
    document = json.loads(result.read_text())
    assert document["status"] == "error" and "metrics" not in document


def test_timeout_is_incomplete_and_retains_execution(tmp_path, numpy_runtime):
    candidate = tmp_path / "implementation.py"
    candidate.write_text("import time\ndef compute(x, *, eps):\n    time.sleep(10)\n")
    result = grade_artifact(
        load_task("softmax-cpu"), candidate, tmp_path / "timeout", timeout_seconds=0.5
    )
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["execution_status"] == "timeout"
    assert result["checks"] is None
    assert (tmp_path / "timeout/execution.json").is_file()


def test_runtime_and_grader_drift_rejected(tmp_path, numpy_runtime):
    task = load_task("softmax-cpu")
    for field in ("--runtime-sha256", "--grader-sha256", "--candidate-sha256"):
        command = list(task.command("check", task.root / "candidate.py"))
        command[command.index(field) + 1] = "0" * 64
        execution = execute_trial(
            tuple(command), task.root, tmp_path / field[2:], time.monotonic() + 20, None
        )
        assert execution["status"] == "failed"
        assert read_result(execution)["status"] == "error"


def test_skill_verifier_binds_answer_to_retained_artifact(tmp_path, numpy_runtime):
    package = load_task("softmax-cpu")
    candidate = package.root / "candidate.py"
    descriptor = skill_verifier.task_descriptor(package, candidate)
    result = skill_verifier.verify(descriptor, {"candidate_sha256": "0" * 64}, tmp_path / "unused")
    assert result == {"passed": False, "assertions": {"artifact_identity": False}}
    assert not (tmp_path / "unused").exists()
