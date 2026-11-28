"""Run the current-Agent protocol using real child processes and synthetic work."""

import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.apps.cli import main
from inferrsi.benchmark import registry
from inferrsi.harness import evaluator, executor, manager
from inferrsi.harness.manager import _runtime, session_runtime_identity
from inferrsi.harness.manager import _state as optimization
from inferrsi.harness.manager._state import _locked
from tests.fixtures.diagnosis import diagnosis_args
from tests.fixtures.session_process import kill_controller, target_python


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
    assert view["next_action"] == "record_bottleneck_diagnosis"
    assert "session final" in view["instructions"]
    diagnose(root, capsys)
    return root


def diagnose(root, capsys):
    assert main(diagnosis_args(root, "benchmarks", "session")) == 0
    capsys.readouterr()


def submit(root, factor, capsys, usage=None):
    args = round_arguments(root, factor)
    if usage is not None:
        export = root / "usage-export.json"
        export.write_text(json.dumps(usage), encoding="utf-8")
        args += ["--usage-export", str(export)]
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def round_arguments(root, factor):
    candidate = root / "work/candidate.py"
    candidate.write_text(f"FACTOR = {factor}\n", encoding="utf-8")
    return ["benchmarks", "session", "round", "--session", str(root),
            "--candidate", str(candidate), "--hypothesis", f"Test factor {factor}"]


def test_manager_round_and_cli_status_share_the_committed_observation(session, capsys, monkeypatch):
    from inferrsi.knowledge.ranking_policy import managed_ranking_policy

    command = round_arguments(session, 2)
    candidate = session / "work/candidate.py"

    def retained(*, lock_held=False):
        return {path.relative_to(session): path.read_bytes() for path in session.rglob("*")
                if path.is_file() and not (lock_held and path.name == ".session.lock")}

    def assess_while_cli_competes(root, directory, plan, execution):
        before = retained(lock_held=True)
        package_root = str(Path(manager.__file__).resolve().parents[3])
        child_path = os.pathsep.join(filter(None, [package_root, os.environ.get("PYTHONPATH")]))
        competing = subprocess.run(
            [sys.executable, "-m", "inferrsi", *command], cwd=session.parent,
            env={**os.environ, "PYTHONPATH": child_path},
            capture_output=True, text=True, timeout=30,
        )
        assert competing.returncode == 2, competing.stderr
        assert f"[Errno {errno.EAGAIN}]" in competing.stderr, competing.stderr
        assert retained(lock_held=True) == before
        return executor.assess_packaged_task(root, directory, plan, execution)

    ports = {"assess_packaged": assess_while_cli_competes,
             "ranking_policy_for": managed_ranking_policy}
    result = manager.run_session(
        manager.EvaluateSessionRound(
            session=session, candidate=candidate, hypothesis="Test factor 2",
        ),
        **ports,
    )
    observation = result["latest_observation"]
    assert observation["assessment"]["score"] == 2
    assert (session / "calls.log").read_text().splitlines() == ["2"]

    before = retained()
    instant = time.time()
    monkeypatch.setattr(optimization, "time", SimpleNamespace(time=lambda: instant))
    direct = manager.run_session(manager.SessionStatus(session=session), **ports)
    assert main(["benchmarks", "session", "status", "--session", str(session)]) == 0
    assert json.loads(capsys.readouterr().out) == direct
    plan, state, _ = manager.read_session_records(session)
    assert plan["round_limit"] == 3 and len(state["rounds"]) == 1
    assert direct["latest_observation"] == observation
    assert retained() == before


@pytest.mark.parametrize(("field", "value"), [
    ("rounds", True), ("rounds", False), ("rounds", 1.5), ("rounds", "2"),
    ("max_minutes", float("nan")), ("max_minutes", 1e308),
    ("evaluation_timeout_seconds", 10**400), ("final_reserve_seconds", -1),
])
def test_manager_rejects_invalid_budget_before_creating_session(task, tmp_path, field, value):
    from inferrsi.knowledge.ranking_policy import managed_ranking_policy

    root = tmp_path / "new-session"
    budget = {"rounds": 3, "max_minutes": 5, "evaluation_timeout_seconds": 15, field: value}
    request = manager.StartBenchmarkSession(session=root, task=task.name, evaluation_args="",
                                            condition="test", **budget)
    with pytest.raises(ValueError, match="budget"):
        manager.run_session(request, task_source=task, ranking_policy_for=managed_ranking_policy,
                            assess_packaged=executor.assess_packaged_task)
    assert not root.exists()


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


def test_packaged_round_uses_target_dependencies(task, tmp_path, capsys, monkeypatch):
    python = target_python(tmp_path, monkeypatch)
    benchmark = task / "benchmark.py"
    benchmark.write_text(
        "from session_target_dependency import VALUE\nassert VALUE == 2\n"
        + benchmark.read_text(encoding="utf-8"), encoding="utf-8",
    )
    root = tmp_path / "session"
    assert main([*start_args(task, root), "--python", str(python)]) == 0
    capsys.readouterr()
    diagnose(root, capsys)
    assert submit(root, 2, capsys)["latest_observation"]["assessment"]["score"] == 2


@pytest.mark.parametrize("recorded,current,probe,result", [
    (("boot", "pid:[123]"), ("boot", "pid:[123]"), ProcessLookupError, "observed_empty"),
    (("other", "pid:[123]"), ("boot", "pid:[123]"), None, "unobservable"),
    ((None, "pid:[123]"), ("boot", "pid:[123]"), None, "unobservable"),
    (("boot", "pid:[123]"), (None, "pid:[123]"), None, "unobservable"),
    (("boot", "pid:[456]"), ("boot", "pid:[123]"), None, "unobservable"),
    (("boot", None), ("boot", "pid:[123]"), None, "unobservable"),
    (("boot", "pid:[123]"), ("boot", None), None, "unobservable"),
    (("boot", "pid:[123]"), ("boot", "pid:[123]"), PermissionError, "unobservable"),
    (("boot", "pid:[123]"), ("boot", "pid:[123]"), None, "live"),
])
def test_group_observation_requires_the_recorded_boot_and_namespace(
    monkeypatch, recorded, current, probe, result,
):
    from inferrsi.harness.executor import launch_records

    calls = []

    def killpg(group, signal):
        calls.append((group, signal))
        if probe:
            raise probe()

    monkeypatch.setattr(launch_records, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(launch_records, "os", SimpleNamespace(killpg=killpg))
    monkeypatch.setattr(launch_records, "linux_process_domain", lambda: current)
    assert launch_records.observe({
        "state": "launched", "spawned": True, "pid": 42, "process_group_id": 42,
        "platform": "linux", "boot_id": recorded[0], "pid_namespace": recorded[1],
    }) == result
    assert calls == ([(42, 0)] if all(recorded) and recorded == current else [])
    assert launch_records.observe({"state": "ended", "pid": None}) == "launch_unconfirmed"
    assert launch_records.observe({"state": "ended", "spawned": False}) == "not_spawned"


@pytest.mark.skipif(sys.platform != "linux", reason="requires a Linux process-group observation")
def test_killed_controller_does_not_restart_live_assessor(task, tmp_path, capsys):
    marker, release = tmp_path / "assessor-started", tmp_path / "release-assessor"
    protocol = task / "optimization.py"
    header = "def assess(directory, settings, execution):\n"
    protocol.write_text(protocol.read_text(encoding="utf-8").replace(
        header, header + (
            "    import time\n    from pathlib import Path\n"
            f"    with Path({str(marker)!r}).open('a') as stream:\n"
            "        stream.write('assess\\n')\n"
            "    deadline = time.monotonic() + 30\n"
            f"    while not Path({str(release)!r}).exists() and time.monotonic() < deadline:\n"
            "        time.sleep(0.02)\n"
        )
    ), encoding="utf-8")
    root = tmp_path / "session"
    assert main(start_args(task, root)) == 0
    capsys.readouterr()
    diagnose(root, capsys)
    args = round_arguments(root, 2)
    driver = "import sys; from inferrsi.apps.cli import main; sys.exit(main(sys.argv[1:]))"
    try:
        kill_controller(driver, args, marker)
        attempt, = (root / "rounds/round-01").iterdir()
        launch = attempt / "protocol-assess-0001.json"
        original = launch.read_bytes()
        assert json.loads(original)["state"] in ("intent", "launched")
        assert (attempt / "execution/execution.json").is_file()
        recover = ["benchmarks", "session", "recover", "--session", str(root)]
        for _ in range(2):
            assert main(recover) == 2
            view = json.loads(capsys.readouterr().out)
            assert view["cleanup_unconfirmed"]["stages"] == ["protocol-assess-0001"]
        assert list(attempt.glob("protocol-assess-*.json")) == [launch]
        assert launch.read_bytes() == original
        assert marker.read_text(encoding="utf-8").splitlines() == ["assess"]
        assert not (root / "recoveries").exists()
    finally:
        release.touch()


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
    diagnose(root, capsys)
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


@pytest.mark.parametrize("factors", [(2, -1, 1.5), (2, 1.5, -1)])
def test_real_loop_rejects_bad_round_keeps_best_and_retests_independently(session, capsys, factors):
    observations = []
    for factor, (input_tokens, output_tokens) in zip(factors, ((100, 20), (200, 10), (20, 10))):
        observations.append(submit(session, factor, capsys, {
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cached_input_tokens": 10,
        }))
    rejected = factors.index(-1)
    assert observations[rejected]["latest_observation"]["assessment"]["status"] == (
        "candidate_failure")
    assert observations[-1]["best"]["score"] == 2
    assert observations[-1]["next_action"].startswith("independently_retest")
    failed_record = (session / observations[rejected]["latest_observation"]["path"]
                     / "observation.json")
    failed_bytes = failed_record.read_bytes()
    assert main(["benchmarks", "session", "final", "--session", str(session)]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["state"] == "completed"
    from inferrsi.apps.delivery import read_bundle

    assert final["delivery"]["status"] == "published"
    delivery = read_bundle(session / "delivery" / final["delivery"]["export_id"])
    assert delivery["acceptance"]["verdict"] == "PASS"
    assert delivery["outcome"]["kind"] == "improved"
    assert (session / "calls.log").read_text().splitlines() == [*map(str, factors), "2"]
    assert failed_record.read_bytes() == failed_bytes
    state = json.loads((session / "state.json").read_text())
    assert state["final"]["candidate_sha256"] == observations[0]["best"]["sha256"]
    report = json.loads((session / "summary.json").read_text())
    assert report["optimization_speedup"] == 2
    assert report["completed_rounds"] == 3
    assert report["usage"]["total_tokens"] == 360
    assert [row["cumulative_usage"]["total_tokens"] for row in report["curve"]] == [120, 330, 360]
    assert report["curve"][rejected]["assessment"]["score"] is None
    assert all(row["best_score"] == 2 for row in report["curve"])
    assert report["wall_elapsed_seconds"] > 0


@pytest.mark.parametrize("status,code", [
    ("timeout", 0), ("cancelled", 0), ("error", None), ("failed", -9),
])
def test_interrupted_execution_cannot_resume_using_a_written_candidate_rejection(
    session, capsys, monkeypatch, status, code,
):
    best = submit(session, 2, capsys)["best"]
    original = executor.execute_ordinary

    def interrupted(*args):
        record = original(*args)
        record.update(status=status, returncode=code)
        (args[1] / "execution/execution.json").write_text(json.dumps(record), encoding="utf-8")
        return record

    monkeypatch.setattr(executor, "execute_ordinary", interrupted)
    candidate = session / "work/candidate.py"
    candidate.write_text("FACTOR = -1\n", encoding="utf-8")
    assert main(["benchmarks", "session", "round", "--session", str(session),
                 "--candidate", str(candidate), "--hypothesis", "Interrupted rejection"]) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["best"] == best
    assert view["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert not view["can_finalize"]
    assert main(["benchmarks", "session", "recover", "--session", str(session)]) == 2
    assert json.loads(capsys.readouterr().out)["state"] == "blocked"
    with pytest.raises(SystemExit):
        main(["benchmarks", "session", "final", "--session", str(session)])
    assert (session / "calls.log").read_text().splitlines() == ["2", "-1"]


def test_final_cannot_skip_optimization_rounds(session):
    with pytest.raises(SystemExit) as error:
        main(["benchmarks", "session", "final", "--session", str(session)])
    assert error.value.code == 2
    assert not (session / "final").exists()


def test_final_report_error_preserves_execution_outcome_and_can_be_exported_later(
    session, capsys, monkeypatch,
):
    from inferrsi.apps import delivery

    for factor in (2, 3, 4):
        submit(session, factor, capsys)
    original = delivery.export_bundle

    def fail(*args, **kwargs):
        raise OSError("Synthetic publication failure")

    monkeypatch.setattr(delivery, "export_bundle", fail)
    assert main(["benchmarks", "session", "final", "--session", str(session)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "completed" and result["delivery"]["status"] == "error"
    assert main(["benchmarks", "session", "status", "--session", str(session)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "completed"
    calls = (session / "calls.log").read_bytes()
    monkeypatch.setattr(delivery, "export_bundle", original)
    assert main(["export", "--input", str(session),
                 "--output", str(session / "delivery" / "retry")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "published"
    assert (session / "calls.log").read_bytes() == calls


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
    original = executor.execute_ordinary

    def crash_after_execution(*args):
        original(*args)
        raise KeyboardInterrupt("coordinator interrupted after child completion")

    monkeypatch.setattr(executor, "execute_ordinary", crash_after_execution)
    with pytest.raises(KeyboardInterrupt):
        submit(session, 2, capsys)
    with pytest.raises(SystemExit):
        submit(session, 3, capsys)
    assert main(["benchmarks", "session", "recover", "--session", str(session)]) == 0
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["completed_rounds"] == 1 and recovered["best"]["score"] == 2
    assert (session / "calls.log").read_text().splitlines() == ["2"]


@pytest.fixture
def held_child():
    children = []

    def start(log):
        command = [sys.executable, "-c",
                   "from pathlib import Path; import sys, time; "
                   "Path(sys.argv[1]).write_text('started\\n'); "
                   "print('ready', flush=True); time.sleep(60)", str(log)]
        child = subprocess.Popen(command, stdout=subprocess.PIPE)
        children.append(child)
        assert child.stdout.readline().strip() == b"ready"
        return child, command

    yield start
    for child in children:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)
        child.stdout.close()


def test_launch_intent_appears_only_after_flush_and_cannot_replace_prior_intent(
    tmp_path, monkeypatch,
):
    from inferrsi.harness.executor.launch_records import LaunchRecord

    path = tmp_path / "launch-step.json"

    def fail_before_publication(_descriptor):
        assert not path.exists()
        raise OSError("launch record flush failed")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_before_publication)
        with pytest.raises(OSError, match="launch record flush failed"):
            LaunchRecord(path, ["first"])
    assert not list(tmp_path.iterdir())

    LaunchRecord(path, ["first"])
    intent = path.read_bytes()
    with pytest.raises(FileExistsError):
        LaunchRecord(path, ["second"])
    assert path.read_bytes() == intent


def test_missing_executable_is_recorded_as_never_spawned(tmp_path):
    from inferrsi.harness.executor.launch_records import observe
    from inferrsi.harness.executor.trials.external import execute_trial

    execution = tmp_path / "execution"
    launch_path = execution / "launch-01.json"
    result = execute_trial(
        (str(tmp_path / "missing-executable"),), tmp_path, execution,
        time.monotonic() + 30, None, launch_path=launch_path,
    )
    assert result["status"] == "error"
    record = json.loads(launch_path.read_bytes())
    assert record["state"] == "ended"
    assert record["spawned"] is False
    assert record["pid"] is None and record["process_group_id"] is None
    assert observe(record) == "not_spawned"


def test_recovery_counts_an_interrupted_round_once_and_keeps_every_step(
    session, capsys, monkeypatch, held_child,
):
    from inferrsi.apps.delivery import read_bundle
    from inferrsi.apps.views.dashboard import dashboard_snapshot
    from inferrsi.harness.executor import launch_records

    best = submit(session, 2, capsys)["best"]
    calls = session / "step-calls.log"
    child = None

    def stop_during_second_step(root, attempt, plan, deadline):
        nonlocal child
        execution = attempt / "execution"
        execution.mkdir()
        first = launch_records.LaunchRecord(execution / "launch-first.json", ["first"])
        first.ended({"pid": 42, "process_group_id": None, "started_at": None,
                     "ended_at": None, "status": "completed", "domain_empty": True}, True)
        marker = execution / "launch-second.json"
        launch_records.LaunchRecord(marker, ["second"])
        child, _ = held_child(calls)
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(executor, "execute_ordinary", stop_during_second_step)
        with pytest.raises(KeyboardInterrupt):
            submit(session, 9, capsys)
    command = ["benchmarks", "session"]
    target = ["--session", str(session)]
    assert main([*command, "recover", *target]) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["completed_rounds"] == 2
    assert view["pending"] is None and view["best"] == best
    assert view["recovery_command"] == "recover --confirm-domain-empty"
    gate = view["cleanup_unconfirmed"]
    assert gate["stages"] == ["launch-second"]
    record = view["latest_observation"]
    assert record["execution"] is None and record["assessment"]["score"] is None
    assert record["assessment"]["status"] == record["selection"]["outcome"] == "interrupted"
    assert record["assessment"]["verdict"] == "INCONCLUSIVE"
    receipt = session / record["recovery"]["path"]
    proof = json.loads(receipt.read_bytes())
    assert [entry["observation"] for entry in proof["launches"]] == [
        "recorded_empty", "launch_unconfirmed",
    ]
    before = (session / "state.json").read_bytes(), receipt.read_bytes()
    for action in ("status", "recover"):
        assert main([*command, action, *target]) == 2
        assert json.loads(capsys.readouterr().out)["completed_rounds"] == 2
        assert ((session / "state.json").read_bytes(), receipt.read_bytes()) == before
    attempt = session / record["path"]
    assert not (attempt / "execution/execution.json").exists()
    assert not list(attempt.rglob("*cleanup*"))
    dashboard = dashboard_snapshot(session)["data"]
    assert dashboard["candidates"][1]["state"] == "interrupted"
    assert dashboard["candidates"][1]["measured_score"] is None
    output = session / "delivery" / "interrupted"
    assert main(["export", "--input", str(session), "--output", str(output)]) == 0
    capsys.readouterr()
    delivery = read_bundle(output)
    assert delivery["rounds"][1]["execution_state"] == "interrupted"
    assert delivery["rounds"][1]["record_verified"]
    assert not delivery["acceptance"]["delivery_accepted"]
    assert child is not None and child.poll() is None
    child.terminate()
    child.wait(timeout=10)
    assert main([*command, "recover", *target, "--confirm-domain-empty"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "active" and view["completed_rounds"] == 2
    confirmation, = (session / "recoveries").glob("confirm-*.json")
    confirmation = json.loads(confirmation.read_bytes())
    assert confirmation["recovery_sha256"] == gate["recovery_sha256"]
    assert confirmation["basis"] == "manual"
    assert [entry["stage"] for entry in confirmation["confirmed_stages"]] == ["launch-second"]
    assert calls.read_text().splitlines() == ["started"]
    assert (session / "calls.log").read_text().splitlines() == ["2"]
    submit(session, 3, capsys)
    assert main([*command, "final", *target]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "completed"
    summary = json.loads((session / "summary.json").read_bytes())
    assert summary["completed_rounds"] == 3
    assert summary["curve"][1]["assessment"]["score"] is None
    assert (session / "calls.log").read_text().splitlines() == ["2", "3", "3"]


def test_recover_never_spawns_a_second_assessor_with_a_receipt(
    session, capsys, monkeypatch, held_child,
):
    from inferrsi.harness.executor import launch_records

    execute = executor.execute_ordinary
    calls = session / "assessor-calls.log"

    def stop_after_execution(*args):
        execute(*args)
        raise KeyboardInterrupt

    def stop_after_assessor_spawn(root, attempt, plan, execution, *, assess_packaged):
        launch_records.LaunchRecord.numbered(attempt, "protocol-assess", ["assess"])
        held_child(calls)
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(executor, "execute_ordinary", stop_after_execution)
        with pytest.raises(KeyboardInterrupt):
            submit(session, 2, capsys)
    pending = json.loads((session / "state.json").read_bytes())["pending"]
    attempt = session / pending["path"]
    receipt = attempt / "execution/execution.json"
    before = receipt.read_bytes()
    command = ["benchmarks", "session", "recover", "--session", str(session)]
    monkeypatch.setattr(evaluator, "assess_ordinary", stop_after_assessor_spawn)
    with pytest.raises(KeyboardInterrupt):
        main(command)
    launch = attempt / "protocol-assess-0001.json"
    marker = launch.read_bytes()
    for _ in range(2):
        assert main(command) == 2
        view = json.loads(capsys.readouterr().out)
        assert view["pending"]["path"] == pending["path"]
        assert view["completed_rounds"] == 0
        assert view["cleanup_unconfirmed"]["stages"] == ["protocol-assess-0001"]
        assert launch.read_bytes() == marker
        assert not (attempt / "protocol-assess-0002.json").exists()
        assert not list(attempt.rglob("*cleanup*"))
    assert receipt.read_bytes() == before
    assert calls.read_text().splitlines() == ["started"]
    assert (session / "calls.log").read_text().splitlines() == ["2"]


def test_interrupted_final_requires_an_explicit_retry(session, capsys, monkeypatch):
    from inferrsi.apps.delivery import read_bundle

    for factor in (2, 3, 4):
        submit(session, factor, capsys)

    def stop(*args):
        raise KeyboardInterrupt

    command = ["benchmarks", "session"]
    target = ["--session", str(session)]
    with monkeypatch.context() as patch:
        patch.setattr(executor, "execute_ordinary", stop)
        with pytest.raises(KeyboardInterrupt):
            main([*command, "final", *target])
    assert main([*command, "recover", *target]) == 2
    state = json.loads((session / "state.json").read_bytes())
    assert state["final"] is None and len(state["rounds"]) == 3
    attempt, = state["final_attempts"]
    assert attempt["assessment"]["status"] == "interrupted"
    assert attempt["execution"] is None
    assert (session / attempt["recovery"]["path"]).is_file()
    assert not (session / "delivery").exists()
    capsys.readouterr()
    assert main([*command, "recover", *target, "--confirm-domain-empty"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["can_finalize"] and view["next_action"].endswith("with_final")
    assert (session / "calls.log").read_text().splitlines() == ["2", "3", "4"]
    assert main([*command, "final", *target]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "completed"
    assert view["delivery"]["status"] == "published", view["delivery"]
    delivery = read_bundle(Path(view["delivery"]["output"]))
    interrupted, = delivery["final_attempts"]
    assert interrupted["status"] == "interrupted"
    assert interrupted["recovery_ref"] == f"source:{attempt['recovery']['path']}"
    assert delivery["completion"]["status"] == "completed"
    state = json.loads((session / "state.json").read_bytes())
    assert state["final_attempts"] == [attempt] and state["final"]["path"] != attempt["path"]
    assert (session / "calls.log").read_text().splitlines() == ["2", "3", "4", "4"]


@pytest.mark.parametrize("operation", ["status", "recover"])
@pytest.mark.parametrize("has_receipt", [False, True])
def test_frozen_drift_settles_a_pending_attempt(
    session, monkeypatch, capsys, operation, has_receipt,
):
    execute = executor.execute_ordinary

    def stop(*args):
        if has_receipt:
            execute(*args)
        raise KeyboardInterrupt

    def should_not_assess(*args, **kwargs):
        pytest.fail("Frozen drift cannot start an assessment")

    monkeypatch.setattr(executor, "execute_ordinary", stop)
    monkeypatch.setattr(evaluator, "assess_ordinary", should_not_assess)
    with pytest.raises(KeyboardInterrupt):
        submit(session, 2, capsys)
    (session / "frozen/TASK.md").write_text("Changed task\n", encoding="utf-8")
    assert main(["benchmarks", "session", operation, "--session", str(session)]) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["pending"] is None
    assert not view["can_finalize"] and view["summary"] is None
    assert "Frozen task resources changed" in view["integrity_error"]
    state = json.loads((session / "state.json").read_bytes())
    record, = state["rounds"]
    assert record["assessment"]["verdict"] == "INCONCLUSIVE"
    assert record["assessment"]["score"] is None
    assert (session / record["path"] / "execution/execution.json").exists() == has_receipt


@pytest.mark.parametrize("operation", ["status", "recover"])
@pytest.mark.parametrize("recorded_gate", [False, True])
def test_frozen_drift_retains_unconfirmed_launch(
    session, monkeypatch, capsys, operation, recorded_gate,
):
    from inferrsi.harness.executor.launch_records import LaunchRecord

    def stop_during_assessment(root, attempt, plan, execution, *, assess_packaged):
        LaunchRecord.numbered(attempt, "protocol-assess", ["assess"])
        raise KeyboardInterrupt

    def unexpected_restart(*args, **kwargs):
        pytest.fail("Invalid frozen inputs cannot start an execution or assessment")

    with monkeypatch.context() as patch:
        patch.setattr(evaluator, "assess_ordinary", stop_during_assessment)
        with pytest.raises(KeyboardInterrupt):
            submit(session, 2, capsys)
    monkeypatch.setattr(executor, "execute_ordinary", unexpected_restart)
    monkeypatch.setattr(evaluator, "assess_ordinary", unexpected_restart)

    state_path = session / "state.json"
    pending = json.loads(state_path.read_bytes())["pending"]
    command = ["benchmarks", "session"]
    target = ["--session", str(session)]
    if recorded_gate:
        assert main([*command, "recover", *target]) == 2
        before = json.loads(capsys.readouterr().out)
        assert before["pending"] == pending

    (session / "frozen/TASK.md").write_text("Changed task\n", encoding="utf-8")
    assert main([*command, operation, *target]) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["pending"] is None
    assert "Frozen task resources changed" in view["integrity_error"]
    assert not view["can_finalize"] and view["summary"] is None
    assert "recovery_command" not in view
    gate = view["cleanup_unconfirmed"]
    assert gate["attempt"] == pending["path"]
    assert gate["stages"] == ["protocol-assess-0001"]
    if recorded_gate:
        assert gate == before["cleanup_unconfirmed"]
    receipt = (session / gate["path"]).read_bytes()
    assert hashlib.sha256(receipt).hexdigest() == gate["recovery_sha256"]
    assert json.loads(receipt)["execution_receipt_present"]

    settled = state_path.read_bytes()
    state = json.loads(settled)
    assert state["cleanup_unconfirmed"] == gate
    record, = state["rounds"]
    assert record["assessment"]["verdict"] == "INCONCLUSIVE"
    assert main([*command, "recover", *target, "--confirm-domain-empty"]) == 2
    assert json.loads(capsys.readouterr().out) == view
    assert state_path.read_bytes() == settled
    assert (session / gate["path"]).read_bytes() == receipt
    assert (session / "calls.log").read_text().splitlines() == ["2"]


@pytest.mark.parametrize("operation,args", [
    ("arguments", "candidate, output, settings"), ("assess", "directory, settings, execution"),
])
@pytest.mark.parametrize("code", ["", "7"])
def test_child_system_exit_settles_as_a_protocol_failure(
    task, tmp_path, capsys, operation, args, code,
):
    path = task / "optimization.py"
    header = f"def {operation}({args}):\n"
    path.write_text(path.read_text(encoding="utf-8").replace(
        header, f"{header}    raise SystemExit({code})\n"), encoding="utf-8")
    root = tmp_path / "session"
    assert main(start_args(task, root)) == 0
    capsys.readouterr()
    diagnose(root, capsys)
    assert main(round_arguments(root, 2)) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["pending"] is None
    assert "cleanup_unconfirmed" not in view
    assessment = view["latest_observation"]["assessment"]
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert assessment["reason"].startswith("SystemExit:")
    assert (root / "calls.log").is_file() == (operation == "assess")
    command = ["benchmarks", "session", "recover", "--session", str(root)]
    assert main(command) == 2
    capsys.readouterr()
    with pytest.raises(SystemExit) as error:
        main([*command, "--confirm-domain-empty"])
    assert error.value.code == 2


@pytest.mark.parametrize("mode,rounds,can_finalize", [
    ("exact", 3, True), ("exact", 1, False), ("up_to", 1, True), ("up_to", 0, False),
])
def test_reserve_status_agrees_with_final_eligibility(task, tmp_path, capsys, monkeypatch,
                                                     mode, rounds, can_finalize):
    from inferrsi.apps.cli import _session_request
    from inferrsi.apps.cli.arguments import parser
    from inferrsi.knowledge.ranking_policy import managed_ranking_policy

    root = tmp_path / "session"
    args = parser().parse_args(start_args(task, root))
    args.round_mode = mode
    manager.run_session(
        _session_request(args), ranking_policy_for=managed_ranking_policy, task_source=task,
        assess_packaged=executor.assess_packaged_task,
    )
    diagnose(root, capsys)
    for index in range(rounds):
        submit(root, index + 2, capsys)
    deadline = json.loads((root / "state.json").read_bytes())["deadline"]
    monkeypatch.setattr(optimization, "time", SimpleNamespace(time=lambda: deadline - 1))
    status = optimization.status(root)
    assert status["remaining_search_seconds"] == 0
    assert status["can_finalize"] is can_finalize
    assert status["next_action"] == (
        "independently_retest_selected_candidate_with_final" if can_finalize
        else "search_budget_exhausted_incomplete_session"
    )


def test_executor_exception_without_receipt_blocks_without_claiming_cleanup(
    session, monkeypatch, capsys,
):
    def unavailable(*args):
        raise OSError("executor unavailable")

    monkeypatch.setattr(executor, "execute_ordinary", unavailable)
    code = main(["benchmarks", "session", "round", "--session", str(session),
                 "--candidate", str(session / "work/candidate.py"), "--hypothesis", "probe"])
    view = json.loads(capsys.readouterr().out)
    assert code == 2 and view["state"] == "blocked" and view["pending"] is None
    assert view["latest_observation"]["execution"]["cleanup_verified"] is None
    assert view["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert not (session / "calls.log").exists()


def test_executor_exception_after_receipt_collects_without_relaunch(session, monkeypatch, capsys):
    original = executor.execute_ordinary

    def failed_after_execution(*args):
        original(*args)
        raise OSError("coordinator failed after child completion")

    monkeypatch.setattr(executor, "execute_ordinary", failed_after_execution)
    view = submit(session, 2, capsys)
    assert view["pending"] is None and view["best"]["score"] == 2
    assert (session / "calls.log").read_text().splitlines() == ["2"]


def test_assessor_exception_preserves_type_and_settles_failed_attempt(session, monkeypatch, capsys):
    def broken_assessor(*args, **kwargs):
        raise TypeError("invalid task assessment")

    monkeypatch.setattr(evaluator, "assess_ordinary", broken_assessor)
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


def start_args(task, root):
    return ["benchmarks", "session", "start", task.name, "--session", str(root),
            "--rounds", "3", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
            "--condition", "synthetic-current-agent", "--evaluation-args", ""]


def test_child_assessor_exception_keeps_its_reason_through_a_real_round(task, tmp_path, capsys):
    # #412 R3: the frozen protocol's assess runs in the protocol child. Its exception must
    # settle the attempt with the same "<Type>: <message>" as the in-process call did.
    path = task / "optimization.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "def assess(directory, settings, execution):\n",
        "def assess(directory, settings, execution):\n"
        "    raise TypeError('invalid task assessment')\n"), encoding="utf-8")
    root = tmp_path / "session"
    assert main(start_args(task, root)) == 0
    capsys.readouterr()
    diagnose(root, capsys)
    candidate = root / "work/candidate.py"
    candidate.write_text("FACTOR = 2\n", encoding="utf-8")
    assert main(["benchmarks", "session", "round", "--session", str(root),
                 "--candidate", str(candidate), "--hypothesis", "Child assessor error"]) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["pending"] is None
    assessment = view["latest_observation"]["assessment"]
    assert assessment["reason"] == "TypeError: invalid task assessment"
    assert assessment["verdict"] == "INCONCLUSIVE" and assessment["score"] is None
    retained = json.loads((root / view["latest_observation"]["path"] / "observation.json")
                          .read_text())
    assert retained["assessment"] == assessment
    assert (root / "calls.log").read_text().splitlines() == ["2"]


def test_child_arguments_exception_keeps_the_coordinator_record_through_a_real_round(
    task, tmp_path, capsys,
):
    # #412 R3: a frozen protocol's `arguments` failure leaves the same coordinator record
    # as the in-process call did: the protocol's own type and message, and the attempt
    # settles through the existing coordinator path. The benchmark never starts.
    path = task / "optimization.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "def arguments(candidate, output, settings):\n",
        "def arguments(candidate, output, settings):\n"
        "    raise TypeError('bad arguments')\n"), encoding="utf-8")
    root = tmp_path / "session"
    assert main(start_args(task, root)) == 0
    capsys.readouterr()
    diagnose(root, capsys)
    candidate = root / "work/candidate.py"
    candidate.write_text("FACTOR = 2\n", encoding="utf-8")
    assert main(["benchmarks", "session", "round", "--session", str(root),
                 "--candidate", str(candidate), "--hypothesis", "Child arguments error"]) == 2
    view = json.loads(capsys.readouterr().out)
    directory = root / view["latest_observation"]["path"]
    assert json.loads((directory / "coordinator-error.json").read_text()) == {
        "type": "TypeError", "error": "bad arguments"}
    assessment = view["latest_observation"]["assessment"]
    assert assessment["reason"] == "ValueError: bad arguments"
    assert assessment["verdict"] == "INCONCLUSIVE" and assessment["score"] is None
    assert not (root / "calls.log").exists()


def test_child_argument_error_keeps_its_cli_message_at_start(task, tmp_path, capsys):
    path = task / "optimization.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "def validate_arguments(args):\n",
        "def validate_arguments(args):\n    raise ValueError('pairs must be positive')\n"),
        encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        main(start_args(task, tmp_path / "session"))
    assert stop.value.code == 2
    error = capsys.readouterr().err
    assert "error: pairs must be positive" in error and "protocol_exception" not in error
    assert not (tmp_path / "session").exists()


def test_task_runner_does_not_expose_harness_as_top_level_modules(task, tmp_path):
    from inferrsi.apps.workflows.benchmark_operations import run_task

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


def test_scoped_read_records_bytes_independently_of_the_experiment_limit(task, request, capsys):
    from inferrsi.apps.views.dashboard import dashboard_snapshot

    query = "Qwen-Image-2.1 denoise NPU eager"
    scenario = "diffusion.image_generation"
    ref = "package:vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
    (task / "task.json").write_text(json.dumps({
        "knowledge_delivery": {"query": query, "scenario": scenario,
                               "ref": ref, "context_bytes": 1},
    }))
    root = request.getfixturevalue("session")
    for scope in ([], ["--scenario", "diffusion.t2i"]):
        assert main(["find", query, "--session", str(root), *scope]) == 0
        found = json.loads(capsys.readouterr().out)
        hits = {item["material_ref"]: item for item in found["items"]}
        assert main(hits["package:inferrsi.ascend.skills.ascend_graph_mode"]["read_args"]) == 0
        assert json.loads(capsys.readouterr().out)["content"]
        assert main(hits[ref]["read_args"]) == 0
        card = json.loads(capsys.readouterr().out)
        receipt = json.loads((root / card["reference"]["path"]).read_bytes())
        size = hits[ref]["next_read_content_bytes"]
        assert receipt["context_budget"] is None and not receipt["context_omissions"]
        assert len(card["content"].encode("utf-8")) == receipt["context_bytes_used"] == size > 0
        search = json.loads((root / found["reference"]["path"]).read_bytes())
        assert "context_bytes" not in receipt["request"]
        assert "context_bytes" not in search["request"]
        visible = dashboard_snapshot(root)["data"]["managed_retrievals"]
        observed = next(row for row in visible if row["path"] == found["reference"]["path"])
        card_hit = next(item for item in observed["items"] if item["ref"] == ref)
        assert card_hit["delivered"] and card_hit["reads"] == [
            {"path": card["reference"]["path"], "resource": "record.json"},
        ]


def test_knowledge_delivery_is_retained_and_bound_to_round(session, capsys):
    from inferrsi.apps.workflows.campaign import verify_capture
    from inferrsi.knowledge.knowledge_find import installed_skill_root
    from inferrsi.knowledge.knowledge_operations import KnowledgeReader

    assert main([
        "find", "cache per-step masks ran out of device memory", "--session", str(session),
        "--limit", "1",
    ]) == 0
    found = json.loads(capsys.readouterr().out)
    hit, = found["items"]
    assert "content" not in hit
    wrong_pin = list(hit["read_args"])
    wrong_pin[wrong_pin.index("--revision") + 1] = "sha256:" + "0" * 64
    with pytest.raises(SystemExit):
        main(wrong_pin)
    assert "hit and revision" in capsys.readouterr().err
    assert main(hit["read_args"]) == 0
    delivered = json.loads(capsys.readouterr().out)
    assert set(delivered["reference"]) == {"path", "sha256", "kind"}
    path = session / delivered["reference"]["path"]
    capture, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert capture["selection"]["method"] == "find-lexical-v1"
    assert capture["retrieval"]["calls"] == ["read"]
    assert capture["request"]["search_ref"] == found["reference"]["path"]
    item, = capture["items"]
    assert item["ref"] == "checkout:case.qwen-ascend-rejected-directions"
    context, = capture["contexts"]
    assert context["revision"] == item["revision"]
    assert context["content_bytes"] > 0 and capture["context_budget"] is None
    assert {resource["path"] for resource in context["resources"]} == {
        "qwen-ascend-rejected-directions.md",
    }
    reader = KnowledgeReader(skill_root=installed_skill_root())
    for resource in context["resources"]:
        assert resource["content"].encode("utf-8") == reader.resource(
            item["ref"], resource["path"], revision=item["revision"]
        )
    result = submit(session, 2, capsys)
    observation = result["latest_observation"]
    assert main(["benchmarks", "session", "status", "--session", str(session),
                 "--round-receipt", "1"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["completed_rounds"] == 1 and receipt["latest_observation"] == {
        key: observation[key] for key in ("path", "observation_sha256")
    }
    assert observation["contexts"] == [
        {**found["reference"], "round": 1, "diagnosis_id": observation["diagnosis_id"]},
        {**delivered["reference"], "round": 1, "diagnosis_id": observation["diagnosis_id"],
         "search_ref": found["reference"]["path"]},
    ]

    from inferrsi.apps.views.dashboard import dashboard_snapshot

    data = dashboard_snapshot(session)["data"]
    retrieval, = data["managed_retrievals"]
    assert retrieval["round"] == 1 and "external" not in retrieval
    assert data["candidates"][0]["knowledge_uses"] == []
    with pytest.raises(SystemExit):
        main(hit["read_args"])
    assert "current round and diagnosis" in capsys.readouterr().err


def test_round_cites_the_cuda_skill_read_and_rejects_the_search(session, capsys):
    from tests.apps.test_campaign_task_selection import BASELINE_CUE

    assert main(["find", BASELINE_CUE, "--session", str(session),
                 "--backend", "cuda", "--limit", "2"]) == 0
    found = json.loads(capsys.readouterr().out)
    hit = found["items"][0]
    assert hit["material_ref"] == "package:inferrsi.common.skills.inference_benchmark_design"
    search = found["reference"]
    assert search["kind"] == "knowledge_search"
    assert (found["hits"], found["context_bytes_used"]) == (2, 0)

    args = round_arguments(session, 2)
    with pytest.raises(SystemExit) as error:
        main([*args, "--knowledge-ref", search["path"]])
    assert error.value.code == 2
    assert "Cite a delivered context" in capsys.readouterr().err
    _, state, _ = optimization.read_session_records(session)
    assert not state["rounds"] and state["pending"] is None

    paths, body = [], bytearray()
    read_args = hit["read_args"]
    while read_args is not None:
        assert main(read_args) == 0
        opened = json.loads(capsys.readouterr().out)
        assert opened["content_resource"] == hit["body_resource"]
        assert opened["revision"] == hit["revision"]
        assert opened["reference"]["kind"] == "delivered_context"
        paths.append(opened["reference"]["path"])
        body.extend(opened["content"].encode("utf-8"))
        read_args = opened.get("next_read_args")
    assert len(body) == 13_166

    citation = f"{paths[0]}#{hit['material_ref']}"
    assert main([*args, "--knowledge-ref", citation]) == 0
    assert json.loads(capsys.readouterr().out)["completed_rounds"] == 1
    _, state, _ = optimization.read_session_records(session)
    completed, = state["rounds"]
    assert completed["knowledge_refs"] == [citation]


def test_legacy_retrieval_is_linked_only_by_matching_submission_snapshots(session, capsys):
    from inferrsi.apps.views.dashboard import dashboard_snapshot
    from tests.fixtures.knowledge_retrieval import install_legacy_capture

    plan, state = optimization._load(session)
    binding = optimization._knowledge_request(plan, state, action="read").binding
    path, digest = install_legacy_capture(session, "managed-omitted", "legacy", diagnosis=binding)
    raw = path.read_bytes()
    capture = json.loads(raw)
    assert capture["context_bytes_used"] == 0 and not capture["contexts"]
    state_path = session / "state.json"
    reference = {"path": path.relative_to(session).as_posix(), "sha256": digest,
                 "kind": "delivered_context", "diagnosis_id": binding["diagnosis_id"]}
    state["contexts"].append(reference)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert dashboard_snapshot(session)["data"]["managed_retrievals"] == []

    refs = [reference["path"], reference["path"] + "#" + capture["items"][0]["ref"]]
    args = round_arguments(session, 2)
    for ref in refs:
        with pytest.raises(SystemExit) as error:
            main([*args, "--knowledge-ref", ref])
        assert error.value.code == 2
        assert "delivered resources" in capsys.readouterr().err
    _, state, summary = optimization.read_session_records(session)
    assert state["contexts"] == [reference] and not state["rounds"]
    assert summary["knowledge_deliveries"] == [{**reference, "kind": "empty_context"}]

    submit(session, 2, capsys)
    state = json.loads(state_path.read_bytes())
    submitted, = state["rounds"]
    state["pending"] = {**submitted, "candidate_id": "candidate-002", "knowledge_refs": refs}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    data = dashboard_snapshot(session)["data"]
    query, = data["managed_retrievals"]
    assert query["round"] is None and query["submitted_rounds"] == [1, 2]
    item, = query["items"]
    assert item["ref"] == capture["items"][0]["ref"] and not item["delivered"]
    assert data["candidates"][0]["knowledge_uses"] == []
    assert data["pending_candidate"]["knowledge_uses"] == []

    state["pending"]["contexts"] = [{**reference, "sha256": "0" * 64}]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert dashboard_snapshot(session)["data"]["managed_retrievals"][0]["submitted_rounds"] == [1]
    assert path.read_bytes() == raw


def test_nonempty_legacy_capture_is_audit_only_in_both_reference_forms(session, capsys):
    from inferrsi.apps.workflows.campaign import verify_capture
    from tests.fixtures.knowledge_retrieval import install_legacy_capture

    plan, state = optimization.read_session_records(session)[:2]
    binding = optimization._knowledge_request(plan, state, action="read").binding
    path, digest = install_legacy_capture(
        session, "managed-query", "legacy-delivered", diagnosis=binding,
        ranking_policy=plan["ranking_policy"],
    )
    state_file = session / "state.json"
    relative = path.relative_to(session).as_posix()
    raw = path.read_bytes()
    capture, status = verify_capture(raw)
    assert status == "verified"
    context, = capture["contexts"]
    state["contexts"].append({"path": relative, "sha256": digest, "kind": "delivered_context",
                              "diagnosis_id": binding["diagnosis_id"]})
    state_file.write_text(json.dumps(state), encoding="utf-8")
    before = state_file.read_bytes()
    args = round_arguments(session, 2)
    for ref in (relative, f"{relative}#{context['ref']}"):
        with pytest.raises(SystemExit) as error:
            main([*args, "--knowledge-ref", ref])
        assert error.value.code == 2
        assert "legacy captures are audit-only" in capsys.readouterr().err
    assert path.read_bytes() == raw and state_file.read_bytes() == before


def test_round_declarations_follow_the_candidate_through_assessment(session, capsys, monkeypatch):
    from inferrsi.apps.views.dashboard import dashboard_snapshot

    execute = executor.execute_ordinary
    expected = {"hypothesis": "Reuse the table", "strategy": "Share across layers",
                "alternatives": ["Cache across requests", "Precompute at [redacted-path]"],
                "selection_reason": "Layers use the same positions"}

    def observe_pending(root, directory, plan, deadline):
        pending = dashboard_snapshot(root)["data"]["pending_candidate"]
        assert pending["managed_submission"] == expected
        return execute(root, directory, plan, deadline)

    monkeypatch.setattr(executor, "execute_ordinary", observe_pending)
    candidate = session / "work/candidate.py"
    candidate.write_text("FACTOR = 2\n", encoding="utf-8")
    args = ["benchmarks", "session", "round", "--session", str(session),
            "--candidate", str(candidate), "--hypothesis", expected["hypothesis"],
            "--strategy", expected["strategy"]]
    for flag in ("--alternative", "--selection-reason"):
        with pytest.raises(SystemExit):
            main([*args, flag, " "])
    assert main([*args, "--alternative", "Cache across requests",
                 "--alternative", "Precompute at /private/path",
                 "--selection-reason", expected["selection_reason"]]) == 0
    capsys.readouterr()
    data = dashboard_snapshot(session)["data"]
    assert data["pending_candidate"] is None
    assert data["candidates"][0]["managed_submission"] == expected
    state_path = session / "state.json"
    state = json.loads(state_path.read_bytes())
    state["rounds"][0]["alternatives"] = ["Unsubmitted option"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="Round submission"):
        dashboard_snapshot(session)


@pytest.mark.parametrize("mutation", [
    "absolute", "outside", "symlink", "ancestor_symlink", "oversized", "hash_mismatch",
])
def test_managed_knowledge_rejects_unverified_capture(
    session, capsys, monkeypatch, mutation,
):
    from inferrsi.apps.views.dashboard import dashboard_snapshot
    from inferrsi.apps.views.retrieval_projection import managed_knowledge
    from inferrsi.harness.records import evidence
    from inferrsi.harness.records.knowledge_capture import MAX_CONTEXT_CAPTURE_BYTES

    assert main([
        "find", "cache per-step masks ran out of device memory", "--session", str(session),
        "--limit", "1",
    ]) == 0
    capsys.readouterr()
    state_path = session / "state.json"
    state = json.loads(state_path.read_bytes())
    reference, = state["contexts"]
    path = session / reference["path"]
    raw = path.read_bytes()
    expected = "unsafe_path"
    if mutation in ("absolute", "outside", "symlink"):
        outside = session.parent / "other-capture.json"
        outside.write_bytes(raw)
        if mutation == "absolute":
            reference["path"] = outside.as_posix()
        elif mutation == "outside":
            reference["path"] = "../other-capture.json"
        else:
            path.unlink()
            try:
                path.symlink_to(outside)
            except OSError:
                pytest.skip("test requires permission to create symlinks")
    elif mutation == "ancestor_symlink":
        alias = session / "alias"
        try:
            alias.symlink_to(path.parent, target_is_directory=True)
        except OSError:
            pytest.skip("test requires permission to create symlinks")
        reference["path"] = f"alias/{path.name}"
    elif mutation == "oversized":
        raw += b" " * MAX_CONTEXT_CAPTURE_BYTES
        path.write_bytes(raw)
        reference["sha256"] = hashlib.sha256(raw).hexdigest()
        expected = "too_large"
    else:
        path.write_bytes(raw + b" ")
        expected = "Delivered knowledge context changed"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    reads = []
    read_regular = evidence.read_regular

    def track_read(path, limit):
        data = read_regular(path, limit)
        reads.append(len(data))
        return data

    monkeypatch.setattr(evidence, "read_regular", track_read)
    assert managed_knowledge(session, [reference]) == ([], {})
    with pytest.raises(ValueError, match=expected):
        dashboard_snapshot(session)
    if expected == "unsafe_path":
        assert not reads
    elif expected == "too_large":
        assert reads == [MAX_CONTEXT_CAPTURE_BYTES + 1] * 2


def test_cannbot_query_and_read_trace_to_candidate(tmp_path, task, capsys, monkeypatch):
    from inferrsi.apps.integrations.cannbot import project
    from inferrsi.apps.integrations.project_binding import checkout_identity
    from inferrsi.apps.views.codex_knowledge import decode
    from inferrsi.apps.views.dashboard import dashboard_snapshot

    revision, digest = "a" * 40, "b" * 64
    locator = "ops/ascendc/apis/synthetic"
    uncited = "ops/ascendc/apis/uncited"
    card_text = "synthetic external body"
    raw_query = "cache per-step masks ran out of device memory in /tmp/profile.json"
    search_query = "cache per-step masks ran out of device memory in [redacted-path]"
    phase = {"state": "ok", "items": [locator, uncited]}
    approved = tmp_path / "approved"
    (approved / ".git").mkdir(parents=True)
    unrelated = tmp_path / "unrelated"
    (unrelated / ".git").mkdir(parents=True)
    monkeypatch.chdir(approved)

    def describe(root, **kwargs):
        assert root == approved.resolve()
        return {"state": "ok", "revision": revision}

    def search(query, *, platform, limit, root, **kwargs):
        assert (query, platform, limit) == (search_query, "a3", 2)
        assert root == approved.resolve()
        if phase["state"] != "ok":
            raise project.ChannelFailure("private worker diagnostics", state=phase["state"])
        return {
            "revision": revision,
            "items": [
                {"locator": ref, "card_sha256": digest, "score": 7, "summary": card_text}
                for ref in phase["items"]
            ],
        }

    def read(ref, *, expected_revision, expected_sha256, page, timeout, root, expected_checkout):
        assert ref in (locator, uncited)
        assert root == approved.resolve()
        assert expected_checkout == checkout_identity(approved.resolve())
        assert (expected_revision, expected_sha256, page) == (
            revision, digest, 2 if ref == locator else 1,
        )
        return {"state": "ok", "locator": ref, "revision": revision, "card_sha256": digest,
                "page": page, "pages": 2, "text": card_text}

    monkeypatch.setattr(project, "describe", describe)
    monkeypatch.setattr(project, "search", search)
    monkeypatch.setattr(project, "read", read)
    root = tmp_path / "with-cannbot"
    operation = ["benchmarks", "session"]
    session_args = ["--session", str(root)]
    start_args = [*operation, "start", task.name, *session_args, "--rounds", "3",
                  "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
                  "--condition", "synthetic-combined", "--evaluation-args", "",
                  "--cannbot-platform", "a3"]
    with pytest.raises(SystemExit):
        main([*start_args, "--knowledge", "off"])
    assert "requires --knowledge on" in capsys.readouterr().err
    assert not root.exists()
    assert main(start_args) == 0
    started = json.loads(capsys.readouterr().out)
    assert started["external_knowledge"] == {
        "channel": "cannbot-knowledge", "backend": "ascend", "platform": "a3",
    }
    assert "external_knowledge_project" not in started
    monkeypatch.chdir(unrelated)

    query_args = ["find", raw_query, *session_args, "--limit", "2"]
    with pytest.raises(SystemExit):
        main(query_args)
    assert "Record measured bottleneck evidence" in capsys.readouterr().err
    diagnose(root, capsys)
    diagnosis, = dashboard_snapshot(root)["data"]["managed_diagnoses"]
    assert diagnosis == {
        "rounds": [], "bottleneck": "Reference operation",
        "measurement_summary": "Synthetic workload: reference operation took 4 ms.",
    }
    assert main(query_args) == 0
    returned = capsys.readouterr().out
    answer = json.loads(returned)
    event, complete, recorded = decode(("find", query_args), 0, returned)
    assert complete and recorded["capture"][0] == answer["reference"]["path"]
    assert event["query"] == answer["query"] == search_query
    assert any(item["ref"] == "cannbot-knowledge:" + locator for item in event["materials"])
    assert not decode(("find", [*query_args, "--no-external"]), 0, returned)[1]
    assert not decode(("find", query_args), 0, json.dumps({**answer, "query": "other"}))[1]
    search_path = answer["external"]["reference"]["path"]
    assert main(answer["items"][0]["read_args"]) == 0
    local_read = json.loads(capsys.readouterr().out)
    local_path, local_item = local_read["reference"]["path"], local_read["ref"]
    before = dashboard_snapshot(root)["data"]
    assert before["managed_diagnoses"] == [{**diagnosis, "rounds": [1]}]
    query, = before["managed_retrievals"]
    assert query["query"] == search_query and query["round"] == 1
    assert any(x["ref"] == local_item and x["delivered"] for x in query["items"])
    assert query["external"]["state"] == "ok"
    assert query["external"]["count"] == 2
    assert query["external"]["reads"] == []
    assert not before["candidates"]

    ext_hit = next(hit for hit in answer["external"]["items"] if hit["locator"] == locator)
    assert ext_hit["read_args"] == [
        "read", *session_args, "--search-ref", search_path,
        "--locator", locator,
    ]
    read_args = ext_hit["read_args"][:-1]
    with pytest.raises(SystemExit):
        main([*read_args, "ops/ascendc/not-from-search"])
    assert "from the recorded search" in capsys.readouterr().err
    capsys.readouterr()
    assert main([*read_args, uncited]) == 0
    capsys.readouterr()
    marker = approved / ".git"
    saved_marker = approved / "saved-git"
    marker.rename(saved_marker)
    marker.mkdir()
    with pytest.raises(SystemExit):
        main([*read_args, locator, "--page", "2"])
    assert "not_enabled" in capsys.readouterr().err
    marker.rmdir()
    saved_marker.rename(marker)

    assert main([*read_args, locator, "--page", "2"]) == 0
    delivery = json.loads(capsys.readouterr().out)
    assert delivery["context"]["text"] == card_text
    assert delivery["receipt"]["page"] == 2
    receipt_path = delivery["reference"]["path"]

    candidate = root / "work/candidate.py"
    candidate.write_text("FACTOR = 2\n")
    round_args = [*operation, "round", *session_args, "--candidate", str(candidate),
                  "--hypothesis", "Apply selected knowledge"]
    with pytest.raises(SystemExit):
        main([*round_args, "--knowledge-ref", search_path])
    assert "read receipt from this session" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main([*round_args, "--knowledge-ref", local_path + "#unknown"])
    assert "delivered resources" in capsys.readouterr().err
    execute = executor.execute_ordinary

    def observe_pending(root, directory, plan, deadline):
        pending_view = dashboard_snapshot(root)["data"]
        assert pending_view["managed_diagnoses"] == [{**diagnosis, "rounds": [1]}]
        current = pending_view["pending_candidate"]
        assert current["candidate_id"] == "candidate-001" and current["round"] == 1
        assert [use["ref"] for use in current["knowledge_uses"]] == [locator, local_item]
        return execute(root, directory, plan, deadline)

    monkeypatch.setattr(executor, "execute_ordinary", observe_pending)
    assert main([*round_args, "--knowledge-ref", receipt_path,
                 "--knowledge-ref", local_path + "#" + local_item]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main([*read_args, locator])
    assert "from the current round" in capsys.readouterr().err
    capsys.readouterr()

    monkeypatch.setattr(executor, "execute_ordinary", execute)
    phase["items"] = [uncited]
    assert main(query_args) == 0
    later_search = json.loads(capsys.readouterr().out)["external"]["reference"]["path"]
    assert main(["read", *session_args, "--search-ref", later_search,
                 "--locator", uncited]) == 0
    later_reference = json.loads(capsys.readouterr().out)["reference"]
    later_path = later_reference["path"]

    phase["items"] = []
    assert main(query_args) == 0
    capsys.readouterr()
    assert submit(root, -1, capsys)["latest_observation"]["assessment"]["score"] is None
    phase["state"] = "unreachable"
    assert main(query_args) == 0
    capsys.readouterr()
    data = dashboard_snapshot(root)["data"]
    first, later, empty, unavailable = data["managed_retrievals"]
    assert data["managed_diagnoses"] == [{**diagnosis, "rounds": [1, 2, 3]}]
    assert [first["round"], later["round"], empty["round"], unavailable["round"]] == [1, 2, 2, 3]
    assert {entry["locator"] for entry in first["external"]["reads"]} == {locator, uncited}
    assert later["external"]["reads"] == [{"locator": uncited, "page": 1}]
    assert empty["external"]["state"] == "ok" and empty["external"]["count"] == 0
    assert unavailable["external"]["state"] == "unreachable"
    row, failed = data["candidates"]
    assert (row["candidate_id"], row["round"], row["measured_score"], row["verdict"]) == (
        "candidate-001", 1, 2, "PASS",
    )
    assert [(use["source"], use["ref"]) for use in row["knowledge_uses"]] == [
        ("cannbot-knowledge", locator), ("local", local_item),
    ]
    assert row["knowledge_uses"][0]["card_sha256"] == digest
    assert failed["knowledge_uses"] == [] and failed["measured_score"] is None
    assert card_text not in json.dumps(data)
    assert "private worker diagnostics" not in json.dumps(data)
    for path in root.rglob("*.json"):
        retained = path.read_text(encoding="utf-8")
        assert card_text not in retained
        assert "private worker diagnostics" not in retained

    state_path = root / "state.json"
    original_state = state_path.read_bytes()
    state = json.loads(original_state)
    first_round = state["rounds"][0]
    original_refs = first_round["knowledge_refs"]
    original_contexts = first_round["contexts"]
    first_round["knowledge_refs"] = [later_path]
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="Round knowledge attribution"):
        dashboard_snapshot(root)
    first_round["knowledge_refs"] = original_refs
    first_round["contexts"] = [*original_contexts, later_reference]
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="Round knowledge attribution"):
        dashboard_snapshot(root)
    first_round["contexts"] = original_contexts

    # Even an imported record with a matching digest must not widen the view.
    for reference in state["contexts"]:
        if reference["path"] not in (search_path, later_path):
            continue
        path = root / reference["path"]
        record = json.loads(path.read_text())
        record["text"] = card_text
        if "items" in record:
            record["items"][0]["summary"] = card_text
        raw = json.dumps(record).encode()
        path.write_bytes(raw)
        reference["sha256"] = hashlib.sha256(raw).hexdigest()
    state_path.write_text(json.dumps(state))
    assert card_text not in json.dumps(dashboard_snapshot(root))

    # Allowlisted keys can still carry card material or private worker details.
    for reference in state["contexts"]:
        if reference["path"] not in (search_path, later_path):
            continue
        path = root / reference["path"]
        record = json.loads(path.read_text())
        nested = {"nested": [card_text, "private worker diagnostics"]}
        if reference["path"] == search_path:
            record.update(revision=nested, score_scale=nested, count=True, elapsed_ms="1")
            record["items"][0]["locator"] = "/private/worker/details"
            record["items"][1]["score"] = nested
            record["items"].append({"locator": nested, "card_sha256": digest})
        else:
            record["page"] = [nested]
        raw = json.dumps(record).encode()
        path.write_bytes(raw)
        reference["sha256"] = hashlib.sha256(raw).hexdigest()
    state_path.write_text(json.dumps(state))
    projection = dashboard_snapshot(root)["data"]
    first_query, later_query, *_ = projection["managed_retrievals"]
    external = first_query["external"]
    assert set(external) == {"channel", "backend", "platform", "state", "revision",
                             "score_scale", "count", "elapsed_ms", "items", "path", "reads"}
    assert all(external[key] is None for key in ("revision", "score_scale", "count", "elapsed_ms"))
    assert external["items"] == [{"locator": uncited, "card_sha256": digest, "score": None}]
    assert external["reads"] == later_query["external"]["reads"] == []
    assert [use["ref"] for use in projection["candidates"][0]["knowledge_uses"]] == [local_item]
    for secret in (card_text, "private worker diagnostics", "/private/worker/details"):
        assert secret not in json.dumps(projection)

    # Updating the session-wide receipt and its hash cannot rebind the citation.
    path = root / receipt_path
    receipt = json.loads(path.read_text())
    receipt["locator"] = uncited
    raw = json.dumps(receipt).encode()
    path.write_bytes(raw)
    cited = next(entry for entry in state["contexts"] if entry["path"] == receipt_path)
    cited["sha256"] = hashlib.sha256(raw).hexdigest()
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="Cited knowledge context differs"):
        dashboard_snapshot(root)


@pytest.mark.parametrize("legacy", [False, True])
def test_unbound_benchmark_cannot_borrow_another_checkout(
    tmp_path, task, capsys, monkeypatch, legacy,
):
    from inferrsi.apps.integrations import external_channels
    from inferrsi.apps.views.dashboard import dashboard_snapshot
    from inferrsi.harness.manager import _state as optimization

    origin = tmp_path / "outside-git"
    origin.mkdir()
    if any((path / ".git").exists() for path in origin.resolve().parents):
        pytest.skip("temporary directory is inside a Git project")
    unrelated = tmp_path / "other-checkout"
    (unrelated / ".git").mkdir(parents=True)
    monkeypatch.chdir(origin)

    def unexpected(**kwargs):
        pytest.fail("an unbound session attempted to assemble a project grant")

    monkeypatch.setattr(external_channels, "_SOURCES", (unexpected,))
    if legacy:
        initialize = optimization.initialize

        def legacy_plan(root, plan):
            plan.pop("external_knowledge_project")
            return initialize(root, plan)

        monkeypatch.setattr(optimization, "initialize", legacy_plan)

    root = tmp_path / "unbound"
    args = ["benchmarks", "session"]
    session_args = ["--session", str(root)]
    assert main([*args, "start", task.name, *session_args, "--rounds", "1", "--max-minutes", "5",
                 "--evaluation-timeout-seconds", "15", "--condition", "unbound-synthetic",
                 "--evaluation-args", "", "--cannbot-platform", "a3"]) == 0
    capsys.readouterr()
    monkeypatch.chdir(unrelated)
    diagnose(root, capsys)
    assert main(["find", "cache per-step masks ran out of device memory", *session_args]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["items"] and not any("content" in row for row in result["items"])
    assert result["external"]["state"] == "not_enabled" and result["external"]["items"] == []

    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    assert main([*args, "status", *session_args]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["external_knowledge"]["channel"] == "cannbot-knowledge"
    assert "external_knowledge_project" not in status
    records = dashboard_snapshot(root)["data"]["managed_retrievals"]
    assert records[0]["external"]["state"] == "not_enabled"
    assert before == {path: path.read_bytes() for path in root.rglob("*.json")}
    # A pinned Ascend grant cannot answer an explicitly CUDA-scoped Find.
    assert main(["find", "implementation option", *session_args, "--backend", "cuda"]) == 0
    scoped = json.loads(capsys.readouterr().out)
    assert "external" not in scoped
    saved = json.loads((root / scoped["reference"]["path"]).read_bytes())
    assert saved["request"]["backend"] == "cuda"


def test_runtime_identity_covers_migrated_process_domain_and_not_removed_executor() -> None:
    from importlib.resources import files

    identity = session_runtime_identity()
    root = Path(str(files("inferrsi")))
    assert "harness/executor/local_process.py" in identity
    # #412 R2: the Harness-owned primitives replace infra.artifacts in six modules.
    assert "harness/records/artifact_primitives.py" in identity
    # #412 R3: the protocol child entry runs every task protocol operation.
    assert "harness/executor/_task_protocol.py" in identity
    assert "harness/task_protocol.py" not in identity
    assert "harness/executor/protocol_child.py" in identity
    assert "harness/protocol_child.py" not in identity
    assert {
        "harness/executor/_ordinary.py", "harness/executor/_project.py",
        "harness/executor/_benchmark_child.py", "harness/evaluator/__init__.py",
        "harness/evaluator/_project.py", "harness/evaluator/_measurement.py",
    } <= identity.keys()
    assert {"harness/project.py", "harness/measurement.py"}.isdisjoint(identity)
    assert "apps/workflows/campaign.py" in identity
    assert "apps/workflows/session_knowledge.py" in identity
    assert "apps/workflows/knowledge.py" in identity
    assert "knowledge/knowledge_find.py" in identity
    assert "knowledge/ranking_policy.py" in identity
    assert "apps/campaign.py" not in identity
    assert "infra/executors/local.py" not in identity
    for name in identity:
        assert (root / name).is_file(), name
    assert "infra/processes.py" not in identity
    assert "harness/serving/server.py" not in identity
    for module in ("_server", "_http", "_image"):
        assert f"harness/executor/serving/{module}.py" in identity
    # The explicit prepare_generation import reaches execution validation even before use.
    assert "harness/executor/_generation.py" in identity
    assert "harness/executor/_execution.py" in identity
    assert "harness/execution_service.py" not in identity
    assert "benchmark/assessment.py" not in identity
    evidence = (root / "harness/records/evidence.py").read_bytes()
    assert identity["harness/records/evidence.py"] == hashlib.sha256(evidence).hexdigest()

    from inferrsi.harness.records.artifact_primitives import sha256

    assert identity["apps/workflows/campaign.py"] == sha256(root / "apps/workflows/campaign.py")


def test_runtime_identity_rejects_computed_dynamic_imports(tmp_path, monkeypatch):
    identity = session_runtime_identity()
    installed = Path(str(_runtime.files("inferrsi")))
    for name in identity:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(installed / name, target)
    path = tmp_path / "harness/records/evidence.py"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            "\ndef read_dynamic(name):\n"
            "    from importlib import import_module as load\n"
            "    return load('inferrsi.' + name)\n"
        )
    monkeypatch.setattr(_runtime, "files", lambda _: tmp_path)
    with pytest.raises(ValueError, match="Session runtime import must name a literal module"):
        session_runtime_identity()


PRE_SERVING = (Path(__file__).resolve().parents[1] / "fixtures" / "optimization-session"
               / "pre-serving-runtime-identity.json")


def _refused(session, capsys, action):
    # The CLI reports the refusal as a usage error: argparse exits with status 2.
    with pytest.raises(SystemExit) as stopped:
        main(["benchmarks", "session", action, "--session", str(session)])
    assert stopped.value.code == 2
    return capsys.readouterr()


def test_a_plan_from_before_the_serving_move_is_refused_and_left_unchanged(session, capsys):
    # #498 slice 2. The fixture holds the runtime identity that main at its source commit
    # records, computed from that commit's own file bytes, so it names infra/processes.py.
    # The new runtime refuses such a plan before status or recover dispatches, and keeps the
    # plan bytes; resume it with the runtime that planned it (CHANGELOG).
    pinned = json.loads(PRE_SERVING.read_text(encoding="utf-8"))["runtime_identity"]
    assert "infra/processes.py" in pinned and "harness/serving/server.py" not in pinned
    path = session / "plan.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["runtime_identity"] = pinned
    path.write_text(json.dumps(plan), encoding="utf-8")
    before = path.read_bytes()
    capsys.readouterr()
    for action in ("status", "recover"):
        output = _refused(session, capsys, action)
        assert "Optimization runtime changed" in output.out + output.err, action
    assert path.read_bytes() == before


PRE_CHANGE_SESSIONS = Path(__file__).resolve().parents[1] / "fixtures" / "optimization-session"


def _session_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.parametrize("fixture, removed_file", [
    # #498 slice 5 removed infra/artifacts.py from the runtime identity.
    ("pre-infra-removal-session", "infra/artifacts.py"),
    # The pre-#558 session records the original scenarios path.
    ("pre-trials-rename-session", "harness/scenarios/external.py"),
    ("pre-recovery-closure-session", "harness/serving/server.py"),
])
def test_a_session_planned_before_a_runtime_change_is_refused_and_left_unchanged(
    tmp_path, capsys, fixture, removed_file,
):
    # Each fixture is a session that main, before that change, started with its own installed
    # runtime, unedited (see optimization-session/README.md). Its coordinator was interrupted
    # after the candidate's child finished, so it holds a completed execution receipt for a
    # round that is not settled, and its plan.json still names the removed file. The current
    # runtime refuses it before status or recover dispatches, and no file changes.
    session = tmp_path / "session"
    shutil.copytree(PRE_CHANGE_SESSIONS / fixture, session)
    before = _session_bytes(session)
    state = json.loads(before["state.json"])
    assert state["rounds"] == [] and state["pending"]["kind"] == "round"
    receipt = json.loads(before[state["pending"]["path"] + "/execution/execution.json"])
    assert receipt["status"] == "completed" and receipt["returncode"] == 0
    assert before["calls.log"].splitlines() == [b"2"]
    assert removed_file in json.loads(before["plan.json"])["runtime_identity"]
    assert removed_file not in session_runtime_identity()
    from inferrsi.harness.manager import inspect_session_status

    historical = inspect_session_status(session)
    assert historical["read_only"] is True
    assert historical["next_action"] == "restore_frozen_runtime"
    assert historical["pending"] == state["pending"]
    for action in ("status", "recover"):
        output = _refused(session, capsys, action)
        assert "Optimization runtime changed" in output.out + output.err, action
    assert _session_bytes(session) == before


def test_changed_transitive_runtime_bytes_refuse_an_untouched_plan(
    session, capsys, monkeypatch, tmp_path,
):
    # A disposable copy of the installed identity files stands in for a newer wheel.
    from importlib.resources import files

    installed = Path(str(files("inferrsi")))
    copy = tmp_path / "install" / "inferrsi"
    for name in session_runtime_identity():
        (copy / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(installed / name, copy / name)
    monkeypatch.setattr(_runtime, "files", lambda package: copy)
    path = session / "plan.json"
    before = path.read_bytes()
    capsys.readouterr()
    assert main(["benchmarks", "session", "status", "--session", str(session)]) == 0
    evidence = copy / "harness/records/evidence.py"
    if not evidence.exists():
        # On the baseline the transitive module is installed but was omitted from the map.
        evidence.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(installed / "harness/records/evidence.py", evidence)
    evidence.write_bytes(evidence.read_bytes() + b"\n# changed transitive bytes\n")
    capsys.readouterr()
    output = _refused(session, capsys, "status")
    assert "Optimization runtime changed" in output.out + output.err
    assert path.read_bytes() == before


@pytest.mark.parametrize("action", ["status", "recover"])
def test_pre_move_runtime_identity_is_rejected_without_rewriting_plan(session, action):
    path = session / "plan.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["runtime_identity"]["apps/campaign.py"] = plan["runtime_identity"].pop(
        "apps/workflows/campaign.py"
    )
    # A prior release used the old key. Even equal bytes cannot admit that runtime map.
    frozen = json.dumps(plan, indent=2).encode("utf-8")
    path.write_bytes(frozen)
    with pytest.raises(SystemExit):
        main(["benchmarks", "session", action, "--session", str(session)])
    assert path.read_bytes() == frozen
    assert not (session / "calls.log").exists()


@pytest.fixture
def pre_move_python():
    executable = os.environ.get("INFERRSI_PRE_MOVE_PYTHON")
    if not executable:
        pytest.skip("Set INFERRSI_PRE_MOVE_PYTHON to an isolated, pinned pre-move wheel runtime")
    assert Path(executable).is_file()
    return executable


def test_pinned_pre_move_wheel_recovers_its_original_plan(
    tmp_path, task, pre_move_python,
):
    """Two independent runtimes; no patched identity map or rewritten frozen plan."""
    driver = """
import json, sys
from pathlib import Path
if sys.argv[1]:
    sys.path.insert(0, sys.argv[1])
from inferrsi.apps.cli import main
from inferrsi.benchmark import registry
registry._library_root = lambda: Path(sys.argv[2])
arguments = sys.argv[3:]
if arguments[0] == 'interrupt':
    from inferrsi.harness import optimization_session  # pinned pre-move wheel
    arguments.pop(0)
    execute = optimization_session._session_execute
    def interrupt(*args):
        execute(*args)
        raise KeyboardInterrupt('synthetic interruption after the retained execution')
    optimization_session._session_execute = interrupt
    try:
        main(arguments)
    except KeyboardInterrupt:
        print(json.dumps({'interrupted': True}))
    else:
        raise AssertionError('execution was not interrupted')
else:
    raise SystemExit(main(arguments))
"""
    post_move_python = os.environ.get("INFERRSI_POST_MOVE_PYTHON", sys.executable)
    current_source = "" if "INFERRSI_POST_MOVE_PYTHON" in os.environ else str(
        Path(__file__).resolve().parents[2] / "src"
    )

    def run(python, source, arguments, expected=0):
        result = subprocess.run(
            [python, "-I", "-c", driver, source, str(task.parent), *arguments],
            cwd=tmp_path, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == expected, result.stderr
        return result

    def start(root):
        return ["benchmarks", "session", "start", task.name, "--session", str(root),
                "--rounds", "3", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
                "--condition", "synthetic-release-boundary", "--evaluation-args", ""]

    old = tmp_path / "old-session"
    run(pre_move_python, "", start(old))
    frozen = (old / "plan.json").read_bytes()
    old_identity = json.loads(frozen)["runtime_identity"]
    assert "apps/campaign.py" in old_identity
    assert "apps/workflows/campaign.py" not in old_identity
    candidate = old / "work/candidate.py"
    candidate.write_text("FACTOR = 2\n", encoding="utf-8")
    interrupted = run(pre_move_python, "", [
        "interrupt", "benchmarks", "session", "round", "--session", str(old),
        "--candidate", str(candidate), "--hypothesis", "Synthetic release recovery control",
    ])
    assert json.loads(interrupted.stdout)["interrupted"]
    retained = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    for action in ("status", "recover"):
        rejected = run(post_move_python, current_source,
                       ["benchmarks", "session", action, "--session", str(old)], expected=2)
        assert "Optimization runtime changed" in rejected.stderr
        after = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
        assert after == retained
    recovered = json.loads(run(pre_move_python, "", [
        "benchmarks", "session", "recover", "--session", str(old),
    ]).stdout)
    assert recovered["completed_rounds"] == 1 and recovered["best"]["score"] == 2
    run(pre_move_python, "", ["benchmarks", "session", "status", "--session", str(old)])
    assert (old / "plan.json").read_bytes() == frozen
    assert (old / "calls.log").read_text().splitlines() == ["2"]

    new = tmp_path / "new-session"
    run(post_move_python, current_source, start(new))
    new_identity = json.loads((new / "plan.json").read_bytes())["runtime_identity"]
    assert "apps/workflows/campaign.py" in new_identity and "apps/campaign.py" not in new_identity
    from inferrsi.harness.records.artifact_primitives import sha256

    canonical = Path(__file__).resolve().parents[2] / "src/inferrsi/apps/workflows/campaign.py"
    assert new_identity["apps/workflows/campaign.py"] == sha256(canonical)


def test_mechanism_checks_are_rejected_for_packaged_task_sessions(session, tmp_path):
    mechanism = tmp_path / "mechanism.json"
    mechanism.write_text(json.dumps({"mechanism": "m", "expect": [
        {"region": "a", "direction": "decrease"}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["benchmarks", "session", "round", "--session", str(session),
              "--candidate", str(session / "work/candidate.py"), "--hypothesis", "h",
              "--mechanism-file", str(mechanism)])
    assert not (session / "rounds").exists() or not any((session / "rounds").iterdir())


def test_packaged_task_assessment_without_a_score_still_blocks(session, monkeypatch, capsys):
    """Only a project's paired decision may settle a scoreless round; tasks must score."""
    def scoreless(*args, **kwargs):
        return {"status": "completed", "verdict": "INCONCLUSIVE",
                "reason": "synthetic_missing_score", "eligible": False}

    monkeypatch.setattr(evaluator, "assess_ordinary", scoreless)
    candidate = session / "work/candidate.py"
    candidate.write_text("FACTOR = 2\n", encoding="utf-8")
    assert main(["benchmarks", "session", "round", "--session", str(session),
                 "--candidate", str(candidate), "--hypothesis", "Missing score control"]) == 2
    view = json.loads(capsys.readouterr().out)
    assert view["state"] == "blocked" and view["pending"] is None
    assessment = view["latest_observation"]["assessment"]
    assert assessment["status"] == "infrastructure_failure" and assessment["score"] is None
    assert "finite positive score" in assessment["reason"]
    assert view["best"]["kind"] == "baseline"
