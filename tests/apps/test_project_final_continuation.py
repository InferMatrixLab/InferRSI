"""CPU checks for explicit continuation of an ordinary project campaign."""

import errno
import hashlib
import json
import subprocess
import sys
import time
from html import unescape
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.apps import delivery
from inferrsi.apps.cli import main
from inferrsi.apps.views.dashboard import dashboard_snapshot
from inferrsi.harness import executor
from inferrsi.harness.manager import _state, read_session_records
from tests.apps.test_project_optimization import project as project
from tests.apps.test_project_optimization import start, start_arguments, submit


def _args(project, action, *extra):
    return ["campaign", action, "--directory", str(project[3]), *extra]


def _call(project, capsys, action, *args, expected=0):
    assert main(_args(project, action, *args)) == expected
    return json.loads(capsys.readouterr().out)


def _failed_final(project, capsys, *, opt_in=True, rounds=3, inconclusive=False):
    protocol = project[1]
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "source, result = map(Path, sys.argv[1:])\n"
        "metric = json.loads((source / 'config.json').read_text())['metric']\n"
        "if 'final' in result.parts and metric == 20:\n    metric = 10\n"
        + ("if 'final' in result.parts and metric == 30:\n    metric = None\n"
           if inconclusive else "")
        + "result.write_text(json.dumps({'metric': metric}))\n",
        encoding="utf-8",
    )
    extra = ("--rounds", str(rounds)) + (("--allow-final-continuation",) if opt_in else ())
    start(project, capsys, extra=extra)
    code, first_round = submit(project, capsys, 20)
    assert code == 0 and first_round["latest_observation"]["assessment"]["verdict"] == "PASS"
    status = _call(project, capsys, "final", "--reason", "Independently check first selection")
    first = read_session_records(project[3])[1]["final"]
    assert status["state"] == "completed" and first["assessment"]["verdict"] == "FAIL"
    assert first["assessment"]["reason"] == "performance_gate_not_met"
    return status, first


def _continuation_args(project, first, *, attempt_id=None, reason="Try another candidate"):
    return _args(project, "round", "--candidate", str(project[0]), "--hypothesis", "Try new input",
                 "--continue-after-final", attempt_id or Path(first["path"]).name,
                 "--continuation-reason", reason)


def _next_candidate(project):
    (project[0] / "config.json").write_text('{"metric":30}', encoding="utf-8")


@pytest.mark.parametrize("second_verdict", ["PASS", "INCONCLUSIVE"])
def test_continuation_retains_current_final_and_evidence(project, capsys, second_verdict):
    root = project[3]
    status, first = _failed_final(project, capsys, inconclusive=second_verdict == "INCONCLUSIVE")
    assert status["can_continue"] and status["next_action"] == "continue_search_after_failed_final"
    assert status["continuation_block_reason"] is None
    first_id = status["current_final_attempt_id"]
    plan_bytes = (root / "plan.json").read_bytes()
    deadline = read_session_records(root)[1]["deadline"]
    first_receipt = root / first["path"] / "observation.json"
    first_bytes = first_receipt.read_bytes()
    first_bundle = Path(status["delivery"]["output"])

    _next_candidate(project)
    proc = subprocess.run([sys.executable, "-m", "inferrsi", *_continuation_args(project, first)],
                          check=True, capture_output=True, text=True, timeout=30)
    resumed = json.loads(proc.stdout)
    assert resumed["state"] == "active" and resumed["completed_rounds"] == 2
    assert resumed["current_final_attempt_id"] == first_id
    assert resumed["latest_observation"]["continuation"] == {
        "after_final": first_id, "reason": "Try another candidate",
    }
    assert resumed["best"]["candidate_id"] != first["candidate_id"]
    _, progress, _ = delivery.project(root, export_id="continued-progress")
    assert progress["final"]["attempt_id"] == first_id
    assert progress["selected_candidate"]["candidate_id"] == first["candidate_id"]
    assert progress["final"]["binding"]["verified"] is True

    result = _call(project, capsys, "final", "--reason", "Independently check second selection",
                   expected=0 if second_verdict == "PASS" else 2)
    _, state, summary = read_session_records(root)
    history = result["final_attempts"]
    assert [item["verdict"] for item in history] == ["FAIL", second_verdict]
    assert [item["candidate_id"] for item in history] == [
        first["candidate_id"], resumed["best"]["candidate_id"],
    ]
    current = history[1 if second_verdict == "PASS" else 0]
    assert result["current_final_attempt_id"] == current["attempt_id"]
    assert result["continuation_block_reason"] == "continuation_already_used"
    assert summary["final_attempts"] == history and summary["final_assessment"] == state["final"][
        "assessment"
    ]
    assert json.loads((root / "summary.json").read_bytes())["final_attempts"] == history
    assert state["deadline"] == deadline and (root / "plan.json").read_bytes() == plan_bytes
    assert first_receipt.read_bytes() == first_bytes

    dashboard = dashboard_snapshot(root)
    view = dashboard["data"]["optimization_session"]
    assert view["current_final_attempt_id"] == current["attempt_id"]
    assert [item["attempt_id"] for item in view["final_attempts"]] == [
        item["attempt_id"] for item in history
    ]
    for item in history:
        assert item["observation"] in dashboard["chart"]
    assert delivery.read_bundle(first_bundle)["acceptance"]["verdict"] == "FAIL"

    bundle = Path(result["delivery"]["output"])
    published = delivery.read_bundle(bundle)
    assert published["acceptance"]["verdict"] == current["verdict"]
    assert published["final"]["attempt_id"] == current["attempt_id"]
    assert published["final"]["binding"]["verified"] is True
    rows = published["final_attempts"]
    assert [item["verdict"] for item in rows] == ["FAIL", second_verdict]
    assert [item["attempt_id"] for item in rows if item["current"]] == [current["attempt_id"]]
    index = {item["id"]: item for item in json.loads((bundle / "artifacts.json").read_bytes())[
        "artifacts"
    ]}
    original = index[rows[0]["assessment_ref"]]
    assert original["location"] == history[0]["observation"]
    assert original["sha256"] == hashlib.sha256(first_bytes).hexdigest()
    for row in rows:
        assert row["assessment_provenance"]["verification"] == "verified"
        assert all(ref in index for ref in row["evidence_refs"])
        for report in ("report.md", "report.html"):
            assert row["attempt_id"] in unescape((bundle / report).read_text(encoding="utf-8"))


@pytest.mark.parametrize(("barrier", "message"), [
    ("disabled", "continuation_not_enabled"),
    ("rounds", "round_budget_exhausted"),
    ("time", "search_time_exhausted"),
    ("cleanup", "failed_final_cleanup_unverified"),
    ("cleanup_other_attempt", "failed_final_cleanup_unverified"),
    ("identity", "Continuation must name the current failed final"),
    ("reason", "Continuation requires a failed final ID and a separate reason"),
])
def test_continuation_refusal_spends_no_round(project, capsys, monkeypatch, barrier, message):
    root = project[3]
    _, first = _failed_final(project, capsys, opt_in=barrier != "disabled",
                             rounds=1 if barrier == "rounds" else 3)
    plan, state, _ = read_session_records(root)
    path = root / first["path"] / "execution/launch-quality-candidate.json"
    if barrier == "cleanup":
        path.unlink()
    elif barrier == "cleanup_other_attempt":
        other = root / state["rounds"][0]["path"] / "execution" / path.name
        path.write_bytes(other.read_bytes())
    elif barrier == "time":
        now = state["deadline"] - plan["final_reserve_seconds"]
        monkeypatch.setattr(_state, "time", SimpleNamespace(time=lambda: now))
    args = _continuation_args(project, first,
                              attempt_id="absent" if barrier == "identity" else None,
                              reason="  " if barrier == "reason" else "Try another candidate")
    _next_candidate(project)
    state_path = root / "state.json"
    original = state_path.read_bytes()
    round_paths = sorted(root.glob("rounds/*/attempt-*"))
    with pytest.raises(SystemExit) as refusal:
        main(args)
    assert refusal.value.code == 2 and message in capsys.readouterr().err
    assert state_path.read_bytes() == original
    assert sorted(root.glob("rounds/*/attempt-*")) == round_paths
    status = _call(project, capsys, "status")
    assert status["continuation_block_reason"] == (
        None if barrier in ("identity", "reason") else message
    )


def test_continuation_start_requires_up_to_project(project, capsys):
    with pytest.raises(SystemExit) as refusal:
        main(start_arguments(project, mode="exact", extra=("--allow-final-continuation",)))
    assert refusal.value.code == 2
    assert "up-to-budget project" in capsys.readouterr().err
    assert not project[3].exists()


def test_continuation_rechecks_budget_after_retention(project, capsys, monkeypatch):
    root = project[3]
    _, first = _failed_final(project, capsys)
    _next_candidate(project)
    plan, state, _ = read_session_records(root)
    cutoff = state["deadline"] - plan["final_reserve_seconds"]
    clock = cutoff - 1
    retain = _state.candidates.retain

    def retain_until_cutoff(*args, **kwargs):
        nonlocal clock
        fingerprint = retain(*args, **kwargs)
        clock = cutoff
        return fingerprint

    def reject_execution(*args):
        pytest.fail("Candidate reached the executor after the search cutoff")

    monkeypatch.setattr(_state, "time", SimpleNamespace(time=lambda: clock))
    monkeypatch.setattr(_state.candidates, "retain", retain_until_cutoff)
    monkeypatch.setattr(executor, "execute_ordinary", reject_execution)
    control = (root / "state.json").read_bytes()
    attempts = sorted(root.glob("rounds/*/attempt-*"))
    with pytest.raises(SystemExit) as refusal:
        main(_continuation_args(project, first))
    assert refusal.value.code == 2 and "search_time_exhausted" in capsys.readouterr().err
    assert (root / "state.json").read_bytes() == control
    assert sorted(root.glob("rounds/*/attempt-*")) == attempts
    status = _call(project, capsys, "status")
    assert status["continuation_block_reason"] == "search_time_exhausted"
    assert status["current_final_attempt_id"] == Path(first["path"]).name


@pytest.mark.skipif(sys.platform != "linux", reason="requires a Linux controller process")
def test_interrupted_admission_excludes_second_process_and_replay(project, capsys, tmp_path):
    root = project[3]
    first_status, first = _failed_final(project, capsys)
    _next_candidate(project)
    args = _continuation_args(project, first)
    marker = tmp_path / "admitted"
    driver = """
import sys, time
from pathlib import Path
from inferrsi.apps.cli import main
from inferrsi.harness import executor
def hold_before_launch(*args):
    Path(sys.argv[1]).touch()
    time.sleep(60)
    raise AssertionError('test must stop the controller before launch')
executor.execute_ordinary = hold_before_launch
sys.exit(main(sys.argv[2:]))
"""
    state_path = root / "state.json"
    with subprocess.Popen([sys.executable, "-c", driver, str(marker), *args]) as controller:
        try:
            stop_at = time.monotonic() + 15
            while not marker.is_file() and controller.poll() is None and time.monotonic() < stop_at:
                time.sleep(0.02)
            assert marker.is_file() and controller.poll() is None
            before = state_path.read_bytes()
            contender = subprocess.run([sys.executable, "-m", "inferrsi", *args],
                                       capture_output=True, text=True, timeout=15)
            assert contender.returncode == 2
            assert f"[Errno {errno.EAGAIN}]" in contender.stderr
            assert state_path.read_bytes() == before
        finally:
            controller.kill()
            controller.wait(timeout=10)

    admitted = json.loads(before)
    pending = admitted["pending"]
    assert pending["continuation"]["after_final"] == first_status["current_final_attempt_id"]
    assert len(admitted["rounds"]) == 1
    assert not (root / pending["path"] / "execution").exists()
    with pytest.raises(SystemExit) as replay:
        main(args)
    assert replay.value.code == 2 and "unresolved_attempt_or_pause" in capsys.readouterr().err
    assert state_path.read_bytes() == before
    assert delivery.read_bundle(Path(first_status["delivery"]["output"]))["acceptance"][
        "verdict"
    ] == "FAIL"

    _call(project, capsys, "recover", expected=2)
    recovered = _call(project, capsys, "recover", "--confirm-domain-empty")
    assert recovered["completed_rounds"] == 2 and recovered["pending"] is None
    assert recovered["latest_observation"]["path"] == pending["path"]
    assert recovered["current_final_attempt_id"] == first_status["current_final_attempt_id"]
    assert recovered["continuation_block_reason"] == "continuation_already_used"
    assert json.loads(state_path.read_bytes())["deadline"] == admitted["deadline"]
    settled = state_path.read_bytes()
    with pytest.raises(SystemExit) as replay:
        main(args)
    assert replay.value.code == 2 and "continuation_already_used" in capsys.readouterr().err
    assert state_path.read_bytes() == settled
    assert not (root / pending["path"] / "execution").exists()


def test_interrupted_second_final_keeps_previous_binding(project, capsys, monkeypatch):
    root = project[3]
    _, first = _failed_final(project, capsys)
    _next_candidate(project)
    assert main(_continuation_args(project, first)) == 0
    capsys.readouterr()

    def interrupt(*_):
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(executor, "execute_ordinary", interrupt)
        with pytest.raises(KeyboardInterrupt):
            main(_args(project, "final", "--reason", "Independently recheck the new selection"))
    _call(project, capsys, "recover", expected=2)
    _call(project, capsys, "recover", "--confirm-domain-empty")
    _, result, _ = delivery.project(root, export_id="interrupted-final")
    assert result["final"]["attempt_id"] == Path(first["path"]).name
    assert result["final"]["binding"]["verified"] is True
    assert [row["verdict"] for row in result["final_attempts"]] == ["FAIL", "INCONCLUSIVE"]
