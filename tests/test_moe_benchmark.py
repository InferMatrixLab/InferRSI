"""No-device contract tests; these do not claim NPU performance acceptance."""

import copy
import errno
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from inferrsi.harness.scenarios import _moe_processes, moe
from inferrsi.harness.scenarios.external import execute_trial


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def fixture_run(tmp_path):
    """A hand-authored two-case transcript with one timed sample per label.

    Rank 0 takes 10/5ms and rank 1 takes 12/6ms. The expected score is 2,
    and suite latency is 6, using rank MAX rather than rank-0 latency.
    """
    task = {"cases": [{"id": "timed", "measured": True},
                      {"id": "edge", "measured": False}],
            "measurement": {"warmups": 0, "samples_per_pair": 1}}
    _write(tmp_path / "task/task.json", task)
    cases = [{"id": "timed", "baseline_median_ms": 12.0, "candidate_median_ms": 6.0,
              "speedup": 2.0, "samples_ms": {"baseline": [12.0], "candidate": [6.0]}}]
    summary = {"completed": True, "correctness": "PASS", "cases": cases, "speedup": 2.0,
               "aggregation": "geometric_mean_case_speedups",
               "measurement_protocol":
                   "shape-matched-different-values-warmup-both-labels-before-paired-timing",
               "metrics": {"suite_latency_ms": 6.0}}
    ranks = []
    for rank in (0, 1):
        calls = []
        for case, seed in (("timed", 100000), ("timed", 100001),
                           ("edge", 110000), ("edge", 110001)):
            for label in ("baseline", "candidate"):
                calls.append({"case_id": case, "seed": seed, "label": label,
                              "phase": "correctness", "variant": "standard",
                              "pair": None, "sample": None, "included_in_score": False})
        for phase, variant, scored in (("shape_warmup", "shape_warmup", False),
                                       ("measurement", "standard", True)):
            for label in ("baseline", "candidate"):
                calls.append({"case_id": "timed", "seed": 100100, "label": label,
                              "phase": phase, "variant": variant, "pair": 0, "sample": 0,
                              "included_in_score": scored})
        samples = []
        for call in calls:
            latency = (10.0 + 2 * rank) / (2 if call["label"] == "candidate" else 1)
            call.update(all_ranks_correct=True, local_elapsed_ms=latency,
                        input_sha256=f"rank{rank}-{call['seed']}-{call['variant']}",
                        checks={k: True for k in ("shape_dtype_device", "finite", "values",
                                                  "nrmse_pass", "input_parameters_preserved")})
            if call["included_in_score"]:
                sample = {k: call[k] for k in ("case_id", "seed", "label", "pair", "sample",
                                               "local_elapsed_ms", "input_sha256")}
                sample["slowest_rank_elapsed_ms"] = 6.0 if call["label"] == "candidate" else 12.0
                samples.append(sample)
        record = {"rank": rank, "completed": True, "correctness": "PASS", "phase": "completed",
                  "calls": calls, "samples": samples, "cases": cases, "speedup": 2.0}
        ranks.append(record)
        _write(tmp_path / f"results/rank-{rank}.json", record)
    _write(tmp_path / "results/summary.json", summary)
    execution = {"status": "completed", "returncode": 0, "metric": 6.0, "metric_error": None}
    identity = moe._hashes(tmp_path, ["task/task.json"])
    return tmp_path, task, ranks, summary, execution, identity


def _adjudicate(fixture_run, **changes):
    root, _, _, _, execution, identity = fixture_run
    execution = {**execution, **changes}
    return moe._adjudicate(root, execution, {"verified": True}, identity, 1)


def test_complete_two_rank_result_is_recomputed(fixture_run):
    root = fixture_run[0]
    before = (root / "results/rank-0.json").read_bytes()
    result = _adjudicate(fixture_run)
    assert result["completed"] and result["correctness"] == "PASS"
    assert result["speedup"] == 2.0 and result["metrics"]["suite_latency_ms"] == 6.0
    assert (root / "results/rank-0.json").read_bytes() == before


@pytest.mark.parametrize("status,returncode", [("timeout", 0), ("failed", 2), ("cancelled", -9)])
def test_failed_execution_cannot_reuse_successful_summary(fixture_run, status, returncode):
    result = _adjudicate(fixture_run, status=status, returncode=returncode)
    assert not result["completed"] and result["correctness"] == "INCONCLUSIVE"
    assert result["speedup"] is None and result["metrics"] == {}


@pytest.mark.parametrize("change", ["missing_rank", "duplicate_rank", "missing_call", "bad_check",
                                    "duplicate_sample", "wrong_max", "wrong_summary"])
def test_incomplete_or_inconsistent_evidence_has_no_score(fixture_run, change):
    root, _, ranks, summary, _, _ = fixture_run
    if change == "missing_rank":
        (root / "results/rank-1.json").unlink()
    elif change == "wrong_summary":
        summary["speedup"] = 99
        _write(root / "results/summary.json", summary)
    else:
        record = copy.deepcopy(ranks[1])
        if change == "duplicate_rank":
            record["rank"] = 0
        elif change == "missing_call":
            record["calls"].pop(0)
        elif change == "bad_check":
            record["calls"][0]["checks"]["finite"] = False
        elif change == "duplicate_sample":
            record["samples"].append(record["samples"][0])
        elif change == "wrong_max":
            record["samples"][0]["slowest_rank_elapsed_ms"] = 10.0
        _write(root / "results/rank-1.json", record)
    result = _adjudicate(fixture_run)
    assert not result["completed"] and result["speedup"] is None


@pytest.mark.parametrize("phase,kind,expected", [
    ("candidate_import", "", "FAIL"), ("candidate_measurement", "", "FAIL"),
    ("trusted_output_validation", "candidate_invalid_output", "FAIL"),
    ("baseline_import", "", "INCONCLUSIVE"),
    ("trusted_output_validation", "baseline_invalid_output", "INCONCLUSIVE"),
])
def test_candidate_failure_is_not_an_infrastructure_retry(fixture_run, phase, kind, expected):
    root, _, ranks, _, _, _ = fixture_run
    ranks[0].update(completed=False, calls=[], phase="trusted_rank_alignment_failure")
    _write(root / "results/rank-0.json", ranks[0])
    ranks[1].update(completed=False, correctness="INCONCLUSIVE", phase=phase, failure_kind=kind,
                    calls=[])
    _write(root / "results/rank-1.json", ranks[1])
    result = _adjudicate(fixture_run, status="failed", returncode=2)
    assert result["correctness"] == expected and result["speedup"] is None
    assert result["round_consumed"] is (expected == "FAIL")


def test_cleanup_failure_does_not_erase_consumed_candidate(fixture_run):
    root, _, ranks, _, execution, identity = fixture_run
    ranks[1].update(completed=False, phase="candidate_import", error="candidate exception")
    _write(root / "results/rank-1.json", ranks[1])
    result = moe._adjudicate(root, execution, {"verified": False}, identity, 1)
    assert result["round_consumed"] and result["correctness"] == "FAIL"
    assert not result["completed"] and result["speedup"] is None
    assert "cleanup" in result["error"]


@pytest.mark.parametrize("rank", [0, 1])
def test_malformed_peer_does_not_erase_consumed_candidate(fixture_run, rank):
    root = fixture_run[0]
    (root / f"results/rank-{rank}.json").write_text("{")
    result = _adjudicate(fixture_run, status="timeout", returncode=None)
    assert result["round_consumed"] and result["status"] == "infrastructure_failure"
    assert not result["completed"] and result["speedup"] is None


@pytest.mark.parametrize("status,exit_code", [("infrastructure_failure", 1),
                                             ("candidate_failure", 2)])
def test_exit_status_is_separate_from_consumed_attempt(monkeypatch, status, exit_code):
    monkeypatch.setattr(moe, "evaluate", lambda *args, **kwargs: {
        "status": status, "completed": False, "round_consumed": True})
    assert moe.main(["--candidate", "candidate.py", "--output-dir", "new-run",
                     "--pairs", "2", "--timeout-seconds", "10"]) == exit_code


def test_source_drift_and_failed_cleanup_invalidate_score(fixture_run):
    root, _, _, _, execution, identity = fixture_run
    result = moe._adjudicate(root, execution, {"verified": False}, identity, 1)
    assert result["speedup"] is None and not result["completed"]
    (root / "task/task.json").write_text("{}")
    result = _adjudicate(fixture_run)
    assert result["speedup"] is None and "changed" in result["error"]


@pytest.mark.parametrize("pairs,timeout", [(0, 10), (-1, 10), (True, 10), (1.5, 10),
                                         (1, 0), (1, -1), (1, float("nan")),
                                         (1, float("inf"))])
def test_invalid_limits_fail_before_output_creation(tmp_path, pairs, timeout):
    candidate = tmp_path / "implementation.py"
    candidate.write_text("def compute(*a, **kw): pass\n")
    with pytest.raises(ValueError):
        moe.evaluate(candidate, tmp_path / "run", pairs=pairs, timeout_seconds=timeout)
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("visible", ["", "0", "0,0", "2,", "0,1,2", "bad,1"])
def test_bad_device_allocation_rejected_without_launch(tmp_path, monkeypatch, visible):
    candidate = tmp_path / "implementation.py"
    candidate.write_text("def compute(*a, **kw): pass\n")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: "")
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", visible)
    with pytest.raises(ValueError, match="NPUs|VISIBLE"):
        moe.evaluate(candidate, tmp_path / "run", pairs=1, timeout_seconds=10)
    assert not (tmp_path / "run").exists()


def test_existing_output_is_never_overwritten(tmp_path):
    candidate = tmp_path / "implementation.py"
    candidate.write_text("candidate evidence")
    with pytest.raises(FileExistsError):
        moe.evaluate(candidate, tmp_path, pairs=1, timeout_seconds=10)
    assert candidate.read_text() == "candidate evidence"


def test_evaluate_freezes_input_uses_executor_and_retains_failure(tmp_path, monkeypatch):
    candidate = tmp_path / "implementation.py"
    candidate.write_text("raise RuntimeError('candidate import failed')\n")
    output = tmp_path / "run"
    monkeypatch.setattr(moe, "_preflight", lambda *args: None)
    monkeypatch.setattr(moe, "cleanup", lambda token: {"verified": True})
    before = time.monotonic()

    def execute(command, cwd, trial, deadline, metric):
        assert cwd == output and trial == output / "execution"
        assert before < deadline <= time.monotonic() + 10
        assert metric == "metrics.suite_latency_ms"
        assert command[:2] == (sys.executable, "-B")
        identity = json.loads((output / "identity.json").read_text())
        assert moe._hashes(output, identity) == identity
        assert (output / "candidate/implementation.py").read_bytes() == candidate.read_bytes()
        _write(output / "results/rank-0.json", {
            "rank": 0, "phase": "candidate_import", "completed": False,
            "correctness": "INCONCLUSIVE", "error": "candidate import failed"})
        return {"status": "failed", "returncode": 2, "metric": None}

    monkeypatch.setattr(moe, "execute_trial", execute)
    result = moe.evaluate(candidate, output, pairs=2, timeout_seconds=10)
    assert result["status"] == "candidate_failure" and result["round_consumed"]
    assert result["speedup"] is None
    assert json.loads((output / "result.json").read_text()) == result


def test_resources_stage_without_importing_candidate_or_device(tmp_path):
    candidate = tmp_path / "implementation.py"
    candidate.write_text("raise RuntimeError('must not import while staging')\n")
    output = tmp_path / "run"
    identity = moe._prepare(candidate, output, 2)
    task = json.loads((output / "task/task.json").read_text())
    assert task["world_size"] == 2 and task["num_experts"] == 8
    assert len(task["cases"]) == 7 and sum(c["measured"] for c in task["cases"]) == 3
    assert task["tolerance"] == {"atol": 0.03, "rtol": 0.03, "nrmse": 0.01, "frozen": True}
    assert moe._hashes(output, identity) == identity
    assert (output / "candidate/implementation.py").read_bytes() == candidate.read_bytes()
    assert json.loads((output / "request.json").read_text()) == {"repetitions": 2}


def _fake_proc_entry(proc, pid, marker, *, state="S", start_ticks=123):
    entry = proc / str(pid)
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "environ").write_bytes((_moe_processes.MARKER + "=" + marker + "\0").encode())
    fields = [state] + ["0"] * 18 + [str(start_ticks)]
    (entry / "stat").write_text(f"{pid} (python) " + " ".join(fields))
    return entry


def test_exact_marker_and_zombie_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: (tmp_path.stat().st_uid), raising=False)
    _fake_proc_entry(tmp_path, "self", "", start_ticks=100)
    for pid, marker, state in ((111, "token", "S"), (222, "other", "S"), (333, "token", "Z")):
        _fake_proc_entry(tmp_path, pid, marker, state=state)
    assert _moe_processes._members("token", tmp_path) == [{"pid": 111, "start_ticks": 123}]


@pytest.mark.parametrize("start_ticks,verified", [(99, True), (100, False), (101, False)])
def test_unreadable_environment_only_excludes_strictly_older_process(
    tmp_path, monkeypatch, start_ticks, verified
):
    monkeypatch.setattr(os, "getuid", lambda: tmp_path.stat().st_uid, raising=False)
    _fake_proc_entry(tmp_path, "self", "", start_ticks=100)
    entry = _fake_proc_entry(tmp_path, 111, "other", start_ticks=start_ticks)
    read_bytes = Path.read_bytes

    def unreadable(path):
        if path == entry / "environ":
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return read_bytes(path)

    members = _moe_processes._members
    monkeypatch.setattr(Path, "read_bytes", unreadable)
    monkeypatch.setattr(_moe_processes, "_members", lambda token: members(token, tmp_path))
    guard = _moe_processes.cleanup("token", grace_seconds=0)
    assert guard["verified"] is verified, guard
    assert guard["signalled_pids"] == []
    if not verified:
        assert repr(str(entry / "environ")) in guard["error"]


def test_same_tick_owned_process_remains_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: tmp_path.stat().st_uid, raising=False)
    _fake_proc_entry(tmp_path, "self", "", start_ticks=100)
    _fake_proc_entry(tmp_path, 111, "token", start_ticks=100)
    assert _moe_processes._members("token", tmp_path) == [{"pid": 111, "start_ticks": 100}]


def test_reused_pid_is_not_signalled(monkeypatch):
    scans = iter([[{"pid": 111, "start_ticks": 123}], []])
    monkeypatch.setattr(_moe_processes, "_members", lambda token: next(scans))
    # The PID was reused after enumeration; its new start time must be checked
    # immediately before signalling even though the original marker matched.
    fields = ["S"] + ["0"] * 18 + ["124"]
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: "111 (python) " + " ".join(fields))
    signalled = []
    monkeypatch.setattr(os, "kill", lambda *args: signalled.append(args))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    guard = _moe_processes.cleanup("token")
    assert guard["verified"] and not signalled, guard


@pytest.mark.skipif(sys.platform != "linux", reason="real /proc and detached process sessions")
def test_deadline_cleans_detached_workers_but_preserves_unrelated_process(tmp_path):
    token = uuid.uuid4().hex
    script = tmp_path / "fake_torchrun.py"
    script.write_text(
        "import json, os, pathlib, subprocess, sys, time\n"
        f"os.environ[{_moe_processes.MARKER!r}] = sys.argv[1]\n"
        "children = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "start_new_session=True) for _ in range(2)]\n"
        "pathlib.Path('workers.json').write_text(json.dumps([p.pid for p in children]))\n"
        "time.sleep(60)\n", encoding="utf-8")
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 start_new_session=True)
    try:
        execution = execute_trial((sys.executable, str(script), token), tmp_path,
                                  tmp_path / "execution", time.monotonic() + 2, None)
        assert execution["status"] == "timeout"
        pids = json.loads((tmp_path / "workers.json").read_text())
        guard = _moe_processes.cleanup(token)
        assert guard["verified"], guard
        assert set(pids) <= set(guard["signalled_pids"]), guard
        assert not _moe_processes._members(token)
        assert unrelated.poll() is None
    finally:
        _moe_processes.cleanup(token)
        unrelated.kill()
        unrelated.wait(timeout=5)
