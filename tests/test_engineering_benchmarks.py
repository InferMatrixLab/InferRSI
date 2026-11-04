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
    checked = []
    measurement = task.manifest["measurement"]
    expected_calls = len(task.manifest["workloads"]) + len(measurement["case_ids"]) * (
        measurement["warmups"] + measurement["samples"]
    )
    for role in ("baseline", "candidate"):
        candidate = task.root / (role + ".py")
        grade = grade_artifact(task, candidate, tmp_path / role, timeout_seconds=20)
        assert grade["verdict"] == "PASS"
        assert len(grade["checks"]["assertions"]) == 4 * expected_calls
        checked.append(json.loads((tmp_path / role / "result.json").read_text()))
    candidate = task.root / "candidate.py"
    measured = read_result(
        run_action(task, candidate, "measure", tmp_path / "timed", timeout_seconds=20)
    )
    assert measured["passed"]
    assert measured["metrics"]["suite_latency_ms"] > 0
    assert [case["id"] for case in measured["cases"]] == measurement["case_ids"]
    assert all(len(c["samples_ms"]) == 5 for c in measured["cases"])
    profile = read_result(
        run_action(task, candidate, "profile", tmp_path / "profile", timeout_seconds=20)
    )
    assert "metrics" not in profile
    assert profile["diagnostic"]["performance_verdict"] is None
    assert "compute" in (tmp_path / "profile/profile.txt").read_text()
    for result in [*checked, profile, measured]:
        assert result["workloads"] == measured["workloads"]
        assert result["input_sequence"] == measured["input_sequence"]
        assert result["executed_calls"] == measured["executed_calls"]
        assert len(result["executed_calls"]) == expected_calls
        hashes = [call["input_sha256"] for call in result["executed_calls"]]
        assert len(hashes) == len(set(hashes))
    assert "zeros" not in measurement["case_ids"]
    assert any(call["id"] == "zeros" for call in measured["executed_calls"])
    for case in measured["cases"]:
        assert case["sample_input_sha256"] == [
            call["input_sha256"]
            for call in measured["input_sequence"]
            if call["id"] == case["id"] and call["phase"] == "measurement"
        ]


@pytest.mark.parametrize("name", ["softmax-cpu", "rmsnorm-cpu"])
@pytest.mark.parametrize("key", ["id(x)", "x.tobytes()"])
def test_timed_calls_cannot_hit_precheck_or_warmup_memo(name, key, tmp_path, numpy_runtime):
    task = load_task(name)
    candidate = tmp_path / "implementation.py"
    operation = (
        "y = np.exp(x-x.max(axis=1,keepdims=True)); y /= y.sum(axis=1,keepdims=True)"
        if name == "softmax-cpu"
        else "y = x / np.sqrt(np.mean(x*x,axis=1,keepdims=True) + np.float32(eps))"
    )
    candidate.write_text(
        "import numpy as np\nfrom pathlib import Path\ncache = {}\n"
        "def compute(x, *, eps):\n"
        f"    key = {key}\n"
        "    if key in cache:\n"
        "        Path(__file__).with_suffix('.hits').write_text('cache hit')\n"
        "        return cache[key]\n"
        f"    {operation}\n"
        "    cache[key] = y\n"
        "    return y\n"
    )
    execution = run_action(task, candidate, "measure", tmp_path / "run", timeout_seconds=20)
    result = read_result(execution)
    assert execution["status"] == "completed" and result["passed"]
    assert result["metrics"]["suite_latency_ms"] > 0
    # Correct memoization remains valid, but every timed call must be a miss.
    assert not candidate.with_suffix(".hits").exists()


@pytest.mark.parametrize("name", ["softmax-cpu", "rmsnorm-cpu"])
def test_shape_cached_output_replay_is_rejected_after_precheck(name, tmp_path, numpy_runtime):
    task = load_task(name)
    candidate = tmp_path / "implementation.py"
    operation = (
        "y = np.exp(x-x.max(axis=1,keepdims=True)); y /= y.sum(axis=1,keepdims=True)"
        if name == "softmax-cpu"
        else "y = x / np.sqrt(np.mean(x*x,axis=1,keepdims=True) + np.float32(eps))"
    )
    candidate.write_text(
        "import numpy as np\ncache = {}\ndef compute(x, *, eps):\n"
        "    key = (x.shape, x.strides)\n"
        "    if key in cache: return cache[key]\n"
        f"    {operation}\n"
        "    cache[key] = y\n"
        "    return y\n"
    )
    execution = run_action(task, candidate, "measure", tmp_path / "run", timeout_seconds=20)
    result = read_result(execution)
    assert execution["status"] == "failed" and not result["passed"]
    assert "metrics" not in result
    assert result["failed_call"]["case"] == "normal"
    assert result["failed_call"]["phase"] == "warmup"
    assert all(value for key, value in result["assertions"].items() if ".call-" not in key)


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
        ("adapter", "numpy-axis1-v1"),
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
    assert set(builtin_tasks()) == {"softmax-cpu", "rmsnorm-cpu", "rmsnorm-npu"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_sequence", "repeated"),
        ("case_ids", []),
        ("case_ids", ["missing"]),
        ("case_ids", ["normal", "normal"]),
        ("case_ids", ["normal", "zeros"]),
        ("samples", 1000),
    ],
)
def test_invalid_input_sequence_contract_rejected(field, value, tmp_path):
    root = tmp_path / "package"
    shutil.copytree(load_task("softmax-cpu").root, root)
    document = json.loads((root / "task.json").read_text())
    document["measurement"][field] = value
    (root / "task.json").write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_task(root)


def test_duplicate_generated_input_bytes_refuse_measurement(tmp_path, numpy_runtime):
    root = tmp_path / "package"
    shutil.copytree(load_task("softmax-cpu").root, root)
    document = json.loads((root / "task.json").read_text())
    # Same values under different layouts still prime a bytes-keyed memo.
    document["workloads"][1]["seed"] = document["workloads"][0]["seed"]
    (root / "task.json").write_text(json.dumps(document))
    task = load_task(root)
    execution = run_action(
        task, root / "candidate.py", "measure", tmp_path / "run", timeout_seconds=20
    )
    result = read_result(execution)
    assert execution["status"] == "failed"
    assert result["status"] == "error" and "metrics" not in result
    assert result["error_type"] == "ValueError"


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
    baseline = json.loads((run / "baseline/trial-001/result.json").read_text())
    for side in ("baseline", "candidate"):
        for path in (run / side).glob("trial-*/result.json"):
            result = json.loads(path.read_text())
            assert result["input_sequence"] == baseline["input_sequence"]
            assert result["executed_calls"] == baseline["executed_calls"]


@pytest.mark.parametrize(
    "case,expected_code,expected_state,expected_verdict",
    [
        ("unmet-gain", 1, "completed", "FAIL"),
        ("wrong-output", 2, "failed", "INCONCLUSIVE"),
        ("timeout", 2, "timeout", "INCONCLUSIVE"),
    ],
)
def test_compare_cli_reports_retained_workbench_outcome(
    case, expected_code, expected_state, expected_verdict, tmp_path, numpy_runtime, capsys
):
    from inferrsi.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    candidate = repo / "implementation.py"
    candidate.write_text(
        "import numpy as np\ndef compute(x, *, eps): return np.zeros_like(x)\n"
        if case == "wrong-output"
        else (load_task("softmax-cpu").root / "candidate.py").read_text(),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    code = main(
        [
            "benchmarks", "compare", "softmax-cpu", "--candidate", str(candidate),
            "--repo", str(repo), "--output-dir", str(tmp_path / "runs"),
            "--repetitions", "1", "--max-minutes", "1e-10" if case == "timeout" else "1",
            # A complete positive-latency comparison cannot reach a 100% reduction.
            "--min-improvement-pct", "100",
        ]
    )
    response = json.loads(capsys.readouterr().out)
    run_dir = Path(response["run_dir"])
    retained = json.loads((run_dir / "status.json").read_text())
    evaluation = json.loads((run_dir / "evaluation.json").read_text())
    assert response["status"] == retained
    assert retained["state"] == expected_state
    assert retained["verdict"] == evaluation["verdict"] == expected_verdict
    assert code == expected_code


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
