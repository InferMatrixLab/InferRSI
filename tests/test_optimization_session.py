"""Run the current-Agent protocol using real child processes and synthetic work."""

import json

import pytest

from inferrsi.benchmark import registry
from inferrsi.cli import main
from inferrsi.harness import optimization_session
from inferrsi.harness.optimization import _locked


@pytest.fixture
def task(tmp_path, monkeypatch):
    library = tmp_path / "library"
    task = library / "test-work"
    task.mkdir(parents=True)
    (library / "index.json").write_text(
        json.dumps({"schema_version": 1, "packages": [task.name]}), encoding="utf-8")
    (task / "TASK.md").write_text("Synthetic protocol control\n", encoding="utf-8")
    (task / "baseline.py").write_text("FACTOR = 1\n", encoding="utf-8")
    (task / "optimization.py").write_text(
        "import json\n"
        "def validate_arguments(args):\n    assert not args\n    return {}\n"
        "def arguments(candidate, output, settings):\n"
        "    return [str(candidate), str(output)]\n"
        "def assess(directory, settings, execution):\n"
        "    return json.loads((directory / 'measurement/result.json').read_text())\n",
        encoding="utf-8",
    )
    (task / "benchmark.py").write_text(
        "import json, runpy, sys\nfrom pathlib import Path\n"
        "value = runpy.run_path(sys.argv[1])['FACTOR']\n"
        "output = Path(sys.argv[2])\noutput.mkdir()\n"
        "with Path('calls.log').open('a') as stream:\n    stream.write(str(value) + '\\n')\n"
        "status = 'completed' if value > 0 else 'candidate_failure'\n"
        "result = {'status': status, 'verdict': 'PASS' if value > 0 else 'FAIL',\n"
        "          'score': value if value > 0 else None}\n"
        "(output / 'result.json').write_text(json.dumps(result))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "_library_root", lambda: library)
    return task


@pytest.fixture
def session(tmp_path, task, capsys):
    root = tmp_path / "session"
    assert main([
        "benchmarks", "session", "start", task.name, "--session", str(root),
        "--rounds", "3", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
        "--condition", "synthetic-current-agent", "--evaluation-args", "",
    ]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["next_action"] == "edit_candidate_and_submit_round"
    assert "session final" in view["instructions"]
    return root


def submit(root, factor, capsys, usage=None):
    candidate = root / "work/candidate.py"
    candidate.write_text(f"FACTOR = {factor}\n", encoding="utf-8")
    args = ["benchmarks", "session", "round", "--session", str(root),
            "--candidate", str(candidate), "--hypothesis", f"Test factor {factor}"]
    if usage is not None:
        export = root / "usage-export.json"
        export.write_text(json.dumps(usage), encoding="utf-8")
        args += ["--usage-export", str(export)]
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def test_started_task_uses_frozen_protocol_without_registry(session, capsys, monkeypatch):
    def unavailable(*args):
        raise AssertionError("The running campaign must not rediscover its task")

    monkeypatch.setattr(registry, "task_resources", unavailable)
    monkeypatch.setattr(registry, "_library_root", unavailable)
    for factor in (2, 3, 4):
        submit(session, factor, capsys)
    assert main(["benchmarks", "session", "recover", "--session", str(session)]) == 0
    capsys.readouterr()
    assert main(["benchmarks", "session", "final", "--session", str(session)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "completed"
    assert (session / "calls.log").read_text().splitlines() == ["2", "3", "4", "4"]


def test_generic_job_precedes_child_start_and_collects_child_final(tmp_path, task, capsys):
    """Software control: synthetic host receipts, real task subprocesses, no Agent launch."""
    root, job = tmp_path / "child-campaign", tmp_path / "agent-job"
    prompt = tmp_path / "task.md"
    prompt.write_text(
        f"Read the RSI entry, optimize {task.name} in {root}, and run final. "
        "Return summary.json and the selected code. Do not delegate again.", encoding="utf-8")
    assert main(["agents", "prepare", "--job", str(job), "--workspace", str(tmp_path),
                 "--prompt-file", str(prompt), "--title", "Synthetic child workflow",
                 "--max-minutes", "10"]) == 0
    capsys.readouterr()
    assert main(["agents", "dispatch", "--job", str(job)]) == 0
    dispatch = json.loads(capsys.readouterr().out)
    assert dispatch["may_create"] is True
    assert dispatch["handoff"]["prompt"] == prompt.read_text(encoding="utf-8")
    assert not root.exists()  # No campaign state/deadline exists during host creation.
    receipt = tmp_path / "synthetic-host.json"
    receipt.write_text('{"synthetic": true}', encoding="utf-8")
    assert main(["agents", "bind", "--job", str(job), "--host", "synthetic",
                 "--session-id", "child", "--receipt", str(receipt)]) == 0
    capsys.readouterr()
    # The execution conversation owns start, search and independent final.
    assert main([
        "benchmarks", "session", "start", task.name, "--session", str(root),
        "--rounds", "1", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
        "--condition", "synthetic-child", "--evaluation-args", "",
    ]) == 0
    capsys.readouterr()
    submit(root, 2, capsys)
    assert main(["benchmarks", "session", "final", "--session", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "completed"
    assert (root / "calls.log").read_text().splitlines() == ["2", "2"]
    summary = json.loads((root / "summary.json").read_text())
    selected = root / summary["selected_candidate"]["path"]
    receipt.write_text(json.dumps({
        "host": "synthetic", "host_id": None, "session_id": "child",
        "state": "completed", "native_receipt": {"synthetic": True},
    }), encoding="utf-8")
    assert main(["agents", "record", "--job", str(job), "--observation", str(receipt),
                 "--artifact", str(root / "summary.json"), "--artifact", str(selected)]) == 0
    returned = json.loads(capsys.readouterr().out)
    assert returned["state"] == "completed"
    assert returned["task_acceptance"] == "not_assessed"
    assert len(returned["artifacts"]) == 2
    assert not (job / "plan.json").exists()  # Host job and optimization stay separate.


def test_real_loop_rejects_bad_round_keeps_best_and_retests_independently(session, capsys):
    observations = []
    for factor, input_tokens, output_tokens in ((2, 100, 20), (-1, 200, 10), (1.5, 20, 10)):
        observations.append(submit(session, factor, capsys, {
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cached_input_tokens": 10,
        }))
    assert observations[1]["latest_observation"]["assessment"]["status"] == "candidate_failure"
    assert observations[-1]["best"]["score"] == 2
    assert observations[-1]["next_action"].startswith("independently_retest")
    assert main(["benchmarks", "session", "final", "--session", str(session)]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["state"] == "completed"
    assert (session / "calls.log").read_text().splitlines() == ["2", "-1", "1.5", "2"]
    report = json.loads((session / "summary.json").read_text())
    assert report["optimization_speedup"] == 2
    assert report["completed_rounds"] == 3
    assert report["usage"]["total_tokens"] == 360
    assert [row["cumulative_usage"]["total_tokens"] for row in report["curve"]] == [120, 330, 360]
    assert report["curve"][1]["assessment"]["score"] is None
    assert all(row["best_score"] == 2 for row in report["curve"])
    assert report["wall_elapsed_seconds"] > 0


def test_final_cannot_skip_optimization_rounds(session):
    with pytest.raises(SystemExit) as error:
        main(["benchmarks", "session", "final", "--session", str(session)])
    assert error.value.code == 2
    assert not (session / "final").exists()


def test_missing_usage_remains_unknown_and_baseline_noise_is_not_a_gain(session, capsys):
    for _ in range(3):
        submit(session, 1, capsys)
    assert main(["benchmarks", "session", "final", "--session", str(session)]) == 0
    report = json.loads((session / "summary.json").read_text())
    assert report["usage"]["total_tokens"] is None
    assert report["selected_candidate"]["kind"] == "baseline"
    assert report["optimization_speedup"] == 1


def test_round_budget_is_enforced(session, capsys):
    for factor in (2, 3, 4):
        submit(session, factor, capsys)
    with pytest.raises(SystemExit):
        submit(session, 5, capsys)
    assert len((session / "calls.log").read_text().splitlines()) == 3


def test_frozen_task_drift_is_rejected_before_execution(session):
    (session / "frozen/baseline.py").write_text("FACTOR = 100\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["benchmarks", "session", "round", "--session", str(session),
              "--candidate", str(session / "work/candidate.py"), "--hypothesis", "drift"])
    assert not (session / "calls.log").exists()


def test_os_lock_prevents_concurrent_submissions(session, capsys):
    with _locked(session), pytest.raises(SystemExit):
        submit(session, 2, capsys)
    assert not (session / "calls.log").exists()


def test_recovery_collects_completed_execution_without_running_candidate_twice(
    session, monkeypatch, capsys,
):
    original = optimization_session._session_execute

    def crash_after_execution(*args):
        original(*args)
        raise KeyboardInterrupt("coordinator interrupted after child completion")

    monkeypatch.setattr(optimization_session, "_session_execute", crash_after_execution)
    with pytest.raises(KeyboardInterrupt):
        submit(session, 2, capsys)
    with pytest.raises(SystemExit):
        submit(session, 3, capsys)
    assert main(["benchmarks", "session", "recover", "--session", str(session)]) == 0
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["completed_rounds"] == 1 and recovered["best"]["score"] == 2
    assert (session / "calls.log").read_text().splitlines() == ["2"]


def test_executor_exception_without_receipt_blocks_without_claiming_cleanup(
    session, monkeypatch, capsys,
):
    def unavailable(*args):
        raise OSError("executor unavailable")

    monkeypatch.setattr(optimization_session, "_session_execute", unavailable)
    code = main(["benchmarks", "session", "round", "--session", str(session),
                 "--candidate", str(session / "work/candidate.py"), "--hypothesis", "probe"])
    view = json.loads(capsys.readouterr().out)
    assert code == 2 and view["state"] == "blocked" and view["pending"] is None
    assert view["latest_observation"]["execution"]["cleanup_verified"] is None
    assert view["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert not (session / "calls.log").exists()


def test_executor_exception_after_receipt_collects_without_relaunch(session, monkeypatch, capsys):
    original = optimization_session._session_execute

    def failed_after_execution(*args):
        original(*args)
        raise OSError("coordinator failed after child completion")

    monkeypatch.setattr(optimization_session, "_session_execute", failed_after_execution)
    view = submit(session, 2, capsys)
    assert view["pending"] is None and view["best"]["score"] == 2
    assert (session / "calls.log").read_text().splitlines() == ["2"]


def test_assessor_exception_preserves_type_and_settles_failed_attempt(session, monkeypatch, capsys):
    def broken_assessor(*args):
        raise TypeError("invalid task assessment")

    monkeypatch.setattr(optimization_session, "_session_assess", broken_assessor)
    candidate = session / "work/candidate.py"
    candidate.write_text("FACTOR = 2\n", encoding="utf-8")
    assert main(["benchmarks", "session", "round", "--session", str(session),
                 "--candidate", str(candidate), "--hypothesis", "Assessor error control"]) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["pending"] is None
    assert view["completed_rounds"] == 1 and view["best"]["kind"] == "baseline"
    record = view["latest_observation"]
    assessment = record["assessment"]
    assert assessment["reason"] == "TypeError: invalid task assessment"
    assert assessment["verdict"] == "INCONCLUSIVE" and assessment["score"] is None
    retained = json.loads((session / record["path"] / "observation.json").read_text())
    assert retained["assessment"] == assessment
    assert (session / "calls.log").read_text().splitlines() == ["2"]


def test_task_runner_does_not_expose_harness_as_top_level_modules(task, tmp_path):
    from inferrsi.benchmark_operations import run_task

    output = tmp_path / "imports.json"
    (task / "benchmark.py").write_text(
        "import importlib.util, json, sys\nfrom pathlib import Path\n"
        "assert importlib.util.find_spec('project') is None\n"
        "assert importlib.util.find_spec('candidates') is None\n"
        "assert importlib.util.find_spec('optimization').origin == "
        "str(Path(__file__).with_name('optimization.py'))\n"
        "Path(sys.argv[1]).write_text(json.dumps({'isolated': True}))\n", encoding="utf-8")
    assert run_task(task.name, [str(output)]) == 0
    assert json.loads(output.read_text())["isolated"]


def test_knowledge_delivery_is_retained_and_bound_to_round(session, monkeypatch, capsys):
    from inferrsi.knowledge_operations import KnowledgeReader

    def collect(self, query, **options):
        import hashlib

        assert query == "" and options["relevance"] == "normalization"
        assert options["context_bytes"] == 2048
        content = "source-grounded synthetic context"
        return {"contexts": [{"ref": "package:test", "revision": "0" * 64,
                              "content_bytes": len(content), "omissions": [],
                              "resources": [{"path": "SKILL.md", "role": "body",
                                             "content": content,
                                             "sha256": hashlib.sha256(content.encode()).hexdigest()}
                                            ]}]}

    monkeypatch.setattr(KnowledgeReader, "collect", collect)
    assert main(["benchmarks", "session", "knowledge", "--session", str(session),
                 "--query", "normalization", "--context-bytes", "2048"]) == 0
    delivered = json.loads(capsys.readouterr().out)
    result = submit(session, 2, capsys)
    assert result["latest_observation"]["contexts"] == [delivered["reference"]]
    assert (session / delivered["reference"]["path"]).is_file()
