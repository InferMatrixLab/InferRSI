"""Formal two-arm plumbing with authored producers, not agent/skill efficacy.

The producer is a real local subprocess. These controller tests replace the
artifact verifier; they do not establish that Linux/NumPy sandbox execution ran.
The separate benchmark verifier tests own real sandbox software controls.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from inferrsi.harness import skill_eval_benchmark as benchmark
from inferrsi.harness.benchmarks.contract import load_builtin_task, load_task
from inferrsi.infra.artifacts import sha256, write_json
from tests.fixtures.skill_eval_compare_support import configuration
from tools import skill_eval_compare as compare
from tools import skill_eval_local as local

PRODUCER = """import json, pathlib, sys
work, final = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
source, mode = sys.argv[3:]
artifact = work / 'implementation.py'
artifact.write_text(source, encoding='utf-8', newline='')
answer = {'artifact': 'implementation.py', 'summary': 'Authored software control, no model'}
if mode == 'changed-input': (work / 'task.json').write_text('{}')
if mode == 'extra-file': (work / 'unexpected.txt').write_text('unexpected')
if mode == 'missing-artifact': artifact.unlink()
if mode == 'oversized': artifact.write_bytes(b'x' * 65537)
if mode == 'invalid-answer': answer['passed'] = True
final.write_text(json.dumps(answer), encoding='utf-8')
event = {'type': 'turn.completed'}
if mode != 'unknown-usage': event['usage'] = {'input_tokens': 3, 'output_tokens': 2}
print(json.dumps(event), flush=True)
"""


class AuthoredProducer:
    """Write candidate bytes without importing or executing them on the host."""

    timeout_seconds = 30

    def __init__(self, modes=None):
        self.modes = modes or {}
        self.calls = []

    def command(self, workspace, final, schema, prompt):
        task = compare.read_json(workspace / "task.json")
        role = "baseline" if "-baseline-" in final.parent.name else "candidate"
        mode = self.modes.get((task["id"], role), "correct")
        source = ("import numpy as np\ndef compute(x, *, eps): return np.zeros_like(x)\n"
                  if mode == "wrong-output" else benchmark.starter(task).decode("utf-8"))
        self.calls.append({
            "task": task, "role": role, "workspace": workspace,
            "schema_sha256": sha256(schema), "source": source,
            "inputs": {p.relative_to(workspace).as_posix(): p.read_bytes()
                       for p in workspace.rglob("*") if p.is_file()},
        })
        return (sys.executable, "-B", "-c", PRODUCER, str(workspace), str(final), source, mode)


def prepared(tmp_path, names=("rmsnorm-cpu",), repeats=1):
    compare.require_git_version(subprocess.check_output(("git", "--version"), text=True))
    config_path, repo = configuration(tmp_path, ids=names, repeats=repeats)
    config = compare.read_json(config_path)
    config["adapter"] = benchmark.ADAPTER
    write_json(config_path, config)
    tasks = [benchmark.task_descriptor(name) for name in names]
    write_json(tmp_path / "cases.json", tasks)
    output = tmp_path / "run"
    digest = compare.prepare(config_path, repo, output)
    return output, digest, config["snapshots"]["candidate"]["git_revision"]


def software_control_verifier(task, answer):
    """A source-identity stub, deliberately not presented as numerical grading."""
    benchmark.validate_task(task)
    passed = answer["artifact_source"] == benchmark.starter(task).decode("utf-8")
    return {
        "passed": passed, "assertions": {"authored_source_control": passed},
        "benchmark": {"scope": "mocked controller test only; no sandbox execution"},
    }


def test_real_authored_processes_use_frozen_task_and_retain_both_sources(tmp_path, monkeypatch):
    output, digest, _ = prepared(tmp_path, names=("rmsnorm-cpu", "softmax-cpu"))
    monkeypatch.setattr(benchmark, "verify", software_control_verifier)
    client = AuthoredProducer({("rmsnorm-cpu", "baseline"): "wrong-output"})
    result = compare.execute(output, digest, client=client)
    assert result["adapter"] == benchmark.ADAPTER
    assert result["counts"]["fix"] == result["counts"]["unchanged_correct"] == 1
    assert len(client.calls) == 4
    assert [call["role"] for call in client.calls] == [
        "baseline", "candidate", "candidate", "baseline"]
    for left, right in (client.calls[:2], client.calls[2:]):
        assert left["task"] == right["task"]
        assert left["inputs"]["task.json"] == right["inputs"]["task.json"]
        assert left["inputs"]["implementation.py"] == right["inputs"]["implementation.py"]
        assert left["schema_sha256"] == right["schema_sha256"]
        assert left["inputs"]["knowledge/selected/SKILL.md"] != (
            right["inputs"]["knowledge/selected/SKILL.md"])
    assert len({call["workspace"] for call in client.calls}) == 4
    assert all(not call["workspace"].exists() for call in client.calls)
    for pair in result["pairs"]:
        for role in compare.ROLES:
            trial = pair[role]
            artifact = output / trial["evidence"]["implementation.py"]
            assert sha256(artifact) == trial["artifact_sha256"]
            answer = json.loads(trial["output"])
            assert artifact.read_text(encoding="utf-8") == answer["artifact_source"]
            assert trial["artifact_kind"] == benchmark.ADAPTER
            assert trial["inputs_unchanged"] is True
            assert trial["grader_trust"] == "reverified"
            assert set(trial["checks"]) == {"passed", "assertions"}
            assert "metrics" not in trial
    before = (output / "report.json").read_bytes()
    compare.report(output)
    assert len(client.calls) == 4
    assert (output / "report.json").read_bytes() == before
    assert str(tmp_path) not in before.decode("utf-8")


@pytest.mark.parametrize("kind", ["task", "schema", "starter"])
def test_changed_frozen_input_prevents_any_producer_call(tmp_path, kind):
    output, digest, _ = prepared(tmp_path)
    plan = compare.load_plan(output)
    name = {"task": "plan/tasks.json", "schema": "plan/schema.json"}.get(kind)
    if name is None:
        name = next(name for name in plan["files"] if name.endswith("/implementation.py"))
    path = output / name
    path.write_bytes(path.read_bytes() + b"\n")
    client = AuthoredProducer()
    with pytest.raises(ValueError, match="Frozen input changed"):
        compare.execute(output, digest, client=client)
    assert client.calls == []


def test_task_grader_and_oracle_dependencies_are_frozen_before_producer(tmp_path, monkeypatch):
    output, digest, _ = prepared(tmp_path)
    plan = compare.load_plan(output)
    names = (
        "src/inferrsi/harness/skill_eval_benchmark.py",
        "src/inferrsi/harness/benchmarks/numpy_task.py",
        "src/inferrsi/data/engineering_benchmarks/rmsnorm-cpu/task.json",
    )
    for name in names:
        assert plan["controllers"][name] == sha256(compare.ROOT / name)
        changed_path = compare.ROOT / name

        def modified_digest(path):
            return "0" * 64 if path == changed_path else sha256(path)

        client = AuthoredProducer()
        with monkeypatch.context() as scope:
            scope.setattr(compare, "sha256", modified_digest)
            with pytest.raises(ValueError, match="Controller changed after freeze"):
                compare.execute(output, digest, client=client)
        assert client.calls == []


def test_prepare_and_revalidation_use_packaged_task_despite_cwd_shadow(tmp_path, monkeypatch):
    canonical = load_builtin_task("softmax-cpu")
    shadow = tmp_path / "softmax-cpu"
    shutil.copytree(canonical.root, shadow, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest = canonical.manifest
    manifest["oracle"]["atol"] = 1
    write_json(shadow / "task.json", manifest)
    (shadow / "candidate.py").write_text("# substituted starter\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    output, _, _ = prepared(tmp_path, names=("softmax-cpu",))
    plan = compare.load_plan(output)
    frozen = load_task(output / "plan/benchmark-tasks/softmax-cpu")
    assert frozen.task_sha256 == canonical.task_sha256
    assert frozen.manifest["oracle"] == canonical.manifest["oracle"]
    assert (output / "plan/starters/softmax-cpu/implementation.py").read_bytes() == (
        canonical.root / "candidate.py").read_bytes()
    name = "src/inferrsi/data/engineering_benchmarks/softmax-cpu/task.json"
    assert plan["controllers"][name] == sha256(canonical.root / "task.json")
    assert not any(name.startswith("softmax-cpu/") for name in plan["controllers"])
    # A later cwd change cannot make the frozen package validate against a new rubric.
    manifest["oracle"]["atol"] = 2
    write_json(shadow / "task.json", manifest)
    assert compare.load_plan(output) == plan


@pytest.mark.parametrize("mode,error", [
    ("changed-input", "inputs_changed"),
    ("extra-file", "inputs_changed"),
    ("missing-artifact", "missing_or_invalid_artifact"),
    ("oversized", "missing_or_invalid_artifact"),
    ("invalid-answer", "invalid_artifact_answer"),
])
def test_invalid_handoff_is_not_a_clean_comparison(tmp_path, monkeypatch, mode, error):
    output, digest, _ = prepared(tmp_path)
    monkeypatch.setattr(benchmark, "verify", software_control_verifier)
    client = AuthoredProducer({("rmsnorm-cpu", "candidate"): mode})
    result = compare.execute(output, digest, client=client)
    trial = result["pairs"][0]["candidate"]
    assert trial["verdict"] == "INCONCLUSIVE"
    retained = compare.read_json(output / trial["evidence"]["result.json"])
    assert retained["evaluation_error"] == error
    # Report prioritizes missing artifact integrity over the original capture
    # error, which remains available in the unchanged result.json record.
    expected_report_error = ("missing_retained_artifact" if mode in {
        "missing-artifact", "oversized", "invalid-answer"} else error)
    assert trial["evaluation_error"] == expected_report_error
    assert result["counts"]["inconclusive"] == 1


def test_no_unsafe_default_launch_or_silent_sandbox_fallback(tmp_path, monkeypatch):
    output, digest, _ = prepared(tmp_path)
    with pytest.raises(ValueError, match="confined local client"):
        compare.execute(output, digest)
    assert not (output / "results/start.json").exists()

    def unavailable(*_):
        raise benchmark.SandboxUnavailable("authored unsupported-host control")

    monkeypatch.setattr(benchmark, "verify", unavailable)
    result = compare.execute(output, digest, client=AuthoredProducer())
    for role in compare.ROLES:
        trial = result["pairs"][0][role]
        assert trial["verdict"] == "INCONCLUSIVE"
        assert trial["evaluation_error"] == "artifact_sandbox_unavailable"
        assert trial["artifact_sha256"] is not None


def test_retained_source_tamper_invalidates_report_without_rerunning_producer(
        tmp_path, monkeypatch):
    output, digest, _ = prepared(tmp_path)
    monkeypatch.setattr(benchmark, "verify", software_control_verifier)
    client = AuthoredProducer()
    result = compare.execute(output, digest, client=client)
    trial = result["pairs"][0]["candidate"]
    artifact = output / trial["evidence"]["implementation.py"]
    artifact.write_text("# substituted source\n", encoding="utf-8")
    report = compare.read_report(output)
    assert report["pairs"][0]["candidate"]["verdict"] == "INCONCLUSIVE"
    assert report["pairs"][0]["candidate"]["evaluation_error"] == "retained_artifact_hash_mismatch"
    assert len(client.calls) == 2


def test_unknown_usage_stops_new_trials_without_inventing_cost(tmp_path, monkeypatch):
    output, digest, _ = prepared(tmp_path)
    monkeypatch.setattr(benchmark, "verify", software_control_verifier)
    client = AuthoredProducer({("rmsnorm-cpu", "baseline"): "unknown-usage"})
    result = compare.execute(output, digest, client=client)
    assert len(client.calls) == 1
    assert result["status"]["stop_reason"] == "unknown_usage"
    assert result["counts"]["missing_pair"] == 1
    assert result["conditions"]["baseline"]["cost"] is None


def test_manual_handoff_keeps_author_reports_distinct_from_artifact_checks(tmp_path, monkeypatch):
    output, digest, head = prepared(tmp_path)
    monkeypatch.setattr(benchmark, "verify", software_control_verifier)
    submission = tmp_path / "author-logs"
    submission.mkdir()
    write_json(submission / "execution.json", {
        "model": compare.load_plan(output)["model"], "environment": "authored software control",
        "access": "not a real agent run", "resources": "no model calls", "usage": None,
        "elapsed_seconds": 1.0, "agent_exit_code": 0, "summary": "controller test only",
    })
    for name in ("stdout.log", "stderr.log"):
        (submission / name).write_text("authored control\n", encoding="utf-8")
    for role in compare.ROLES:
        workspace = tmp_path / role
        local.stage(output, digest, "rmsnorm-cpu", role, 1, workspace, head)
        if role == "baseline":
            (workspace / benchmark.ARTIFACT).write_bytes(b"# authored bad control\r\n")
        result = local.capture(output, digest, "rmsnorm-cpu", role, 1, workspace, head, submission)
    assert result["counts"]["artifact_improved"] == 1
    pair = result["pairs"][0]
    assert pair["comparability"] == "unverified_author_reported"
    assert pair["baseline"]["verdict"] == "FAIL"
    assert pair["candidate"]["verdict"] == "PASS"
    assert pair["candidate"]["author_reported_execution"] is True
    assert pair["candidate"]["observations"]["usage"] is None
    artifact = output / pair["baseline"]["evidence"]["implementation.py"]
    assert artifact.read_bytes() == b"# authored bad control\r\n"
    assert pair["baseline"]["artifact_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", [
    {"adapter": "unregistered-benchmark"},
    {"execution_mode": "generation-only"},
    {"schema": "custom-schema.json"},
    {"grader": "custom-grader.py"},
])
def test_adapter_does_not_accept_unfrozen_alternate_paths(tmp_path, change):
    config_path, _ = configuration(tmp_path, ids=("rmsnorm-cpu",))
    config = compare.read_json(config_path)
    config.update(adapter=benchmark.ADAPTER)
    config.update(change)
    with pytest.raises(ValueError):
        compare.validate(config, [benchmark.task_descriptor("rmsnorm-cpu")])


def test_real_benchmark_sandbox_two_arm_handoff_or_explicit_unavailable(tmp_path):
    """Actual authored source replay; never represents an LLM or skill benefit."""
    output, digest, _ = prepared(tmp_path)
    client = AuthoredProducer({("rmsnorm-cpu", "baseline"): "wrong-output"})
    result = compare.execute(output, digest, client=client)
    pair = result["pairs"][0]
    if any(pair[role]["evaluation_error"] == "artifact_sandbox_unavailable"
           for role in compare.ROLES):
        if os.environ.get("INFERRSI_REQUIRE_BENCHMARK_SANDBOX") == "1":
            pytest.fail("Required benchmark sandbox unavailable; no host fallback")
        pytest.skip("Benchmark sandbox unavailable; two-arm numerical execution unqualified")
    assert len(client.calls) == 2
    assert pair["baseline"]["verdict"] == "FAIL"
    assert pair["candidate"]["verdict"] == "PASS"
    assert result["counts"]["fix"] == 1
    assert len(pair["candidate"]["checks"]["assertions"]) == 164
    assert not all(pair["baseline"]["checks"]["assertions"].values())
    for role in compare.ROLES:
        trial = pair[role]
        assert trial["evaluation_error"] is None
        assert trial["grader_trust"] == "reverified"
        assert "suite_latency_ms" not in json.dumps(trial["checks"])
        artifact = output / trial["evidence"]["implementation.py"]
        assert sha256(artifact) == trial["artifact_sha256"]
