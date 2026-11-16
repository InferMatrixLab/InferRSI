"""Real command integration of shared rounds; metric values are synthetic controls."""

import json
import os
import subprocess
import sys

import pytest

from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard
from inferrsi.cli import main
from inferrsi.harness.optimization import read_records


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "engine.py").write_text("def compute(x):\n    return x * 2\n", encoding="utf-8")
    (repo / "config.json").write_text('{"metric": 10}', encoding="utf-8")
    protocol = tmp_path / "protocol"
    protocol.mkdir()
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "config = json.loads((Path(sys.argv[1])/'config.json').read_text())\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric':config['metric']}))\n",
        encoding="utf-8",
    )
    (protocol / "quality.py").write_text(
        "import json, runpy, sys\nfrom pathlib import Path\n"
        "compute = runpy.run_path(str(Path(sys.argv[1])/'engine.py'))['compute']\n"
        "Path(sys.argv[2]).write_text(json.dumps({'correct':compute(16)==32}))\n",
        encoding="utf-8",
    )
    instructions = tmp_path / "task.md"
    instructions.write_text("Synthetic integration fixture; preserve compute outputs.",
                            encoding="utf-8")
    return repo, protocol, instructions, tmp_path / "campaign"


def start_arguments(project, *, direction="maximize", mode="up_to", extra=()):
    repo, protocol, instructions, root = project
    return [
        "campaign", "start", "--directory", str(root), "--repo", str(repo),
        "--include", "engine.py", "--include", "config.json", "--protocol", str(protocol),
        "--instructions", str(instructions), "--measure-command",
        '"{python}" "{protocol}/measure.py" "{candidate}" "{result}"',
        "--quality-command", '"{python}" "{protocol}/quality.py" "{candidate}" "{result}"',
        "--metric-key", "metric", "--metric-unit", "synthetic-units", "--direction", direction,
        "--quality-key", "correct", "--scope", "synthetic-software-control",
        "--repetitions", "2", "--warmups", "1", "--min-improvement-pct", "1",
        "--rounds", "3", "--round-mode", mode, "--max-minutes", "5",
        "--evaluation-timeout-seconds", "20", *extra,
    ]


def start(project, capsys, *, direction="maximize", mode="up_to", extra=()):
    assert main(start_arguments(project, direction=direction, mode=mode, extra=extra)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["working_candidate"] == str(project[0])
    return result


def submit(project, capsys, metric):
    repo, _, _, root = project
    (repo / "config.json").write_text(json.dumps({"metric": metric}), encoding="utf-8")
    code = main(["campaign", "round", "--directory", str(root), "--candidate", str(repo),
                 "--hypothesis", "Synthetic candidate with declared configuration change"])
    return code, json.loads(capsys.readouterr().out)


def test_project_lifecycle_never_imports_benchmark(project):
    """Reject any Benchmark import in a fresh process, including the CLI entry."""
    repo, _, _, root = project
    script = """
import importlib.abc, json, sys
from pathlib import Path
class NoBenchmark(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('inferrsi.benchmark', 'inferrsi.benchmark_operations') or (
            fullname.startswith('inferrsi.benchmark.')
        ):
            raise AssertionError('Ordinary optimization imported ' + fullname)
sys.meta_path.insert(0, NoBenchmark())
from inferrsi.cli import main
from inferrsi.harness.optimization import read_records
config = json.loads(sys.stdin.read())
assert main(config['start']) == 0
Path(config['repo'], 'config.json').write_text('{"metric":20}', encoding='utf-8')
for command in config['commands']:
    assert main(command) == 0
plan, state, summary = read_records(Path(config['root']))
assert not any(name.startswith('benchmark/') for name in plan['runtime_identity'])
assert state['final']['assessment']['verdict'] == 'PASS'
assert summary['optimization_speedup'] == 2
assert summary['completed_rounds'] == 1
"""
    commands = [
        ["campaign", "knowledge", "--directory", str(root), "--query", "cgroupv2",
         "--context-bytes", "2048"],
        ["campaign", "round", "--directory", str(root), "--candidate", str(repo),
         "--hypothesis", "Synthetic configuration improvement"],
        ["campaign", "recover", "--directory", str(root)],
        ["campaign", "final", "--directory", str(root), "--reason", "Synthetic search done"],
        ["campaign", "status", "--directory", str(root)],
        ["dashboard", "--input", str(root), "--output", str(root / "report.html")],
    ]
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        input=json.dumps({"start": start_arguments(project), "commands": commands,
                          "repo": str(repo), "root": str(root)}),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "Independent final: PASS" in (root / "report.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("direction,value", [("maximize", 20), ("minimize", 5)])
def test_project_runs_shared_rounds_and_final_from_retained_multifile_candidate(
    project, capsys, direction, value,
):
    start(project, capsys, direction=direction)
    code, result = submit(project, capsys, value)
    assert code == 0 and result["best"]["score"] == value
    repo, _, _, root = project
    selected = root / result["best"]["path"]
    assert (selected / "engine.py").is_file() and (selected / "config.json").is_file()
    (repo / "engine.py").write_text("raise RuntimeError('unsubmitted edit')", encoding="utf-8")
    assert main(["campaign", "final", "--directory", str(root),
                 "--reason", "Caller ended the up-to-budget search"]) == 0
    capsys.readouterr()
    plan, state, summary = read_records(root)
    assert plan["round_mode"] == "up_to" and summary["completed_rounds"] == 1
    assert state["final"]["assessment"]["verdict"] == "PASS"
    assert summary["optimization_speedup"] == 2
    assert summary["usage"]["total_tokens"] is None
    assert state["final"]["candidate_sha256"] == state["best"]["sha256"]
    # The existing dashboard reads the same state, even if the derived summary was removed.
    (root / "summary.json").unlink()
    snapshot = dashboard_snapshot(root)
    assert snapshot["data"]["candidates"][0]["verdict"] == "PASS"
    assert snapshot["data"]["optimization_session"]["completed_rounds"] == 1
    assert "Synthetic candidate" in render_dashboard(snapshot)
    assert not (root / "rounds.jsonl").exists()  # No second mutable control log.


def test_quality_failure_is_retained_and_cannot_win(project, capsys):
    start(project, capsys)
    (project[0] / "engine.py").write_text("def compute(x):\n    return 0\n", encoding="utf-8")
    code, result = submit(project, capsys, 100)
    assert code == 0 and result["best"]["kind"] == "baseline"
    assert result["latest_observation"]["assessment"]["verdict"] == "FAIL"
    assert result["completed_rounds"] == 1
    (project[0] / "engine.py").write_text("def compute(x):\n    return 2*x\n", encoding="utf-8")
    _, result = submit(project, capsys, 20)
    assert result["best"]["kind"] == "candidate"


@pytest.mark.parametrize("quality_failed", [False, True])
def test_dashboard_rejects_identical_bytes_when_earlier_round_remains_best(
    project, capsys, quality_failed,
):
    if quality_failed:
        # Freeze a synthetic gate up front; never rewrite the retained protocol.
        (project[1] / "quality.py").write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "result = Path(sys.argv[2])\n"
            "rejected = 'round-02' in result.parts and 'quality-candidate' in result.parts\n"
            "result.write_text(json.dumps({'correct':not rejected}))\n",
            encoding="utf-8",
        )
    start(project, capsys)
    assert submit(project, capsys, 20)[0] == 0
    assert submit(project, capsys, 20)[0] == 0
    root = project[3]
    _, state, _ = read_records(root)
    first, second = state["rounds"]
    assert first["candidate_sha256"] == second["candidate_sha256"]
    assert second["assessment"]["quality_passed"] is not quality_failed
    assert second["best_after"]["candidate_id"] == first["candidate_id"]
    data = dashboard_snapshot(root)["data"]
    assert [row["decision"] for row in data["candidates"]] == ["adopted", "rejected"]
    assert [row["decision"]["outcome"] for row in data["rounds"]] == ["adopted", "rejected"]


def test_missing_quality_evidence_is_inconclusive(project, capsys):
    (project[1] / "quality.py").write_text(
        "import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text('{}')\n",
        encoding="utf-8")
    start(project, capsys)
    code, result = submit(project, capsys, 20)
    assert code == 2 and result["state"] == "blocked"
    assert result["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"


def test_fixed_rounds_and_frozen_protocol_are_not_bypassed(project, capsys):
    start(project, capsys, mode="exact")
    submit(project, capsys, 20)
    with pytest.raises(SystemExit):
        main(["campaign", "final", "--directory", str(project[3]), "--reason", "early"])
    (project[3] / "frozen/protocol/quality.py").write_text("# modified", encoding="utf-8")
    with pytest.raises(SystemExit):
        submit(project, capsys, 30)


def test_project_knowledge_off_and_manual_record_writes_are_rejected(project, capsys):
    start(project, capsys, extra=("--knowledge", "off"))
    root = project[3]
    with pytest.raises(SystemExit):
        main(["campaign", "knowledge", "--directory", str(root),
              "--query", "fusion", "--context-bytes", "100"])
    with pytest.raises(SystemExit):
        main(["campaign", "record", "--directory", str(root), "--candidate", "untracked",
              "--run-id", "missing", "--round", "1", "--title", "Bypass managed writes"])
    with pytest.raises(SystemExit):
        main(["campaign", "capture-context", "--directory", str(root), "--id", "bypass",
              "--relevance", "fusion", "--context-bytes", "100"])


def test_declared_paths_cannot_escape_project(project, capsys):
    with pytest.raises(SystemExit):
        start(project, capsys, extra=("--include", "../protocol"))
    assert not project[3].exists()


def test_changed_retained_assessment_is_rejected(project, capsys):
    start(project, capsys)
    _, view = submit(project, capsys, 20)
    path = project[3] / view["latest_observation"]["path"] / "observation.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="assessment record changed"):
        read_records(project[3])


def test_candidate_directory_identity_includes_new_files(tmp_path):
    from inferrsi.harness.candidates import identity, retain

    source = tmp_path / "source"
    source.mkdir()
    (source / "code.py").write_text("value = 1", encoding="utf-8")
    before = identity(source)
    (source / "config.json").write_text("{}", encoding="utf-8")
    assert identity(source) != before
    assert retain(source, tmp_path / "snapshot") == identity(source)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable mode")
def test_snapshot_preserves_executable_helper_and_binds_its_mode(tmp_path):
    from inferrsi.harness.candidates import identity, retain

    source = tmp_path / "source"
    source.mkdir()
    helper = source / "helper.sh"
    helper.write_text("#!/bin/sh\nprintf 'synthetic-helper'\n", encoding="utf-8")
    helper.chmod(0o755)
    copied = tmp_path / "snapshot"
    fingerprint = retain(source, copied)
    assert subprocess.check_output([str(copied / "helper.sh")]) == b"synthetic-helper"
    (copied / "helper.sh").chmod(0o644)
    assert identity(copied) != fingerprint


@pytest.mark.parametrize("relative", ["protocol/new_check.py", "baseline/new_config.json"])
def test_frozen_input_additions_are_rejected_even_after_candidate_wins(project, capsys, relative):
    start(project, capsys)
    submit(project, capsys, 20)
    (project[3] / "frozen" / relative).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="file set"):
        read_records(project[3])


def test_bad_candidate_exception_is_classified_by_frozen_wrapper(project, capsys):
    quality = project[1] / "quality.py"
    quality.write_text(
        "import json, runpy, sys\nfrom pathlib import Path\n"
        "try:\n"
        "    compute = runpy.run_path(str(Path(sys.argv[1])/'engine.py'))['compute']\n"
        "    result = {'correct':compute(16)==32}\n"
        "except RuntimeError:\n"
        "    result = {'status':'candidate_failure', 'reason':'compute raised RuntimeError'}\n"
        "Path(sys.argv[2]).write_text(json.dumps(result))\n", encoding="utf-8")
    start(project, capsys)
    (project[0] / "engine.py").write_text(
        "def compute(x):\n    raise RuntimeError('bad candidate')\n", encoding="utf-8")
    code, view = submit(project, capsys, 20)
    assert code == 0 and view["state"] == "active" and view["completed_rounds"] == 1
    assert view["latest_observation"]["assessment"]["verdict"] == "FAIL"
    assert len(view["latest_observation"]["execution"]["steps"]) == 2  # No wasted measurement.
    (project[0] / "engine.py").write_text("def compute(x):\n    return x*2\n", encoding="utf-8")
    assert submit(project, capsys, 20)[1]["best"]["kind"] == "candidate"


def test_unclassified_process_crash_does_not_claim_candidate_failure(project, capsys):
    start(project, capsys)
    (project[0] / "engine.py").write_text("raise RuntimeError('unknown failure')", encoding="utf-8")
    code, view = submit(project, capsys, 20)
    assert code == 2 and view["state"] == "blocked" and not view["can_finalize"]
    assert view["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"


def test_project_cwd_logs_leave_frozen_inputs_usable(project, capsys):
    measure = project[1] / "measure.py"
    measure.write_text(measure.read_text() + "Path('scratch.log').write_text('log')\n")
    start(project, capsys)
    code, view = submit(project, capsys, 20)
    assert code == 0 and view["state"] == "active" and view["best"]["score"] == 20
    assert not (project[3] / "frozen/baseline/scratch.log").exists()
    execution = project[3] / view["latest_observation"]["path"] / "execution"
    assert (execution / "workspace/baseline/scratch.log").is_file()
    assert (execution / "workspace/candidate/scratch.log").is_file()
    assert main(["campaign", "recover", "--directory", str(project[3])]) == 0
    capsys.readouterr()
    assert main(["campaign", "final", "--directory", str(project[3]),
                 "--reason", "Scratch output control complete"]) == 0
    assert read_records(project[3])[2]["optimization_speedup"] == 2


def test_project_execution_copy_source_changes_are_rejected(project, capsys):
    measure = project[1] / "measure.py"
    measure.write_text(measure.read_text() + "Path('engine.py').write_text('modified')\n")
    start(project, capsys)
    code, view = submit(project, capsys, 20)
    assert code == 2 and view["state"] == "blocked" and view["pending"] is None
    assert view["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert (project[3] / "frozen/baseline/engine.py").read_text().startswith("def compute")


@pytest.mark.parametrize("assessment", [
    {"status": "completed", "score": 20},
    {"status": "completed", "score": float("nan"), "baseline_score": 10},
    {"status": "unexpected"}, None,
])
def test_malformed_assessment_settles_as_blocked(project, capsys, monkeypatch, assessment):
    from inferrsi.harness import optimization_session

    start(project, capsys)
    monkeypatch.setattr(optimization_session, "_session_assess", lambda *args: assessment)
    code, view = submit(project, capsys, 20)
    assert code == 2 and view["state"] == "blocked" and view["pending"] is None
    assert view["best"]["kind"] == "baseline"
    assert view["latest_observation"]["assessment"]["score"] is None


def test_post_execution_drift_retains_readable_rejection(project, capsys, monkeypatch):
    from inferrsi.harness import optimization_session

    start(project, capsys)
    original = optimization_session._session_execute

    def drift(root, *args):
        result = original(root, *args)
        (root / "frozen/protocol/unexpected.py").write_text("drift")
        return result

    monkeypatch.setattr(optimization_session, "_session_execute", drift)
    code, view = submit(project, capsys, 20)
    assert code == 2 and view["state"] == "blocked" and view["pending"] is None
    assert "file set" in view["integrity_error"] and view["summary"] is None
    for operation in ("status", "recover"):
        main(["campaign", operation, "--directory", str(project[3])])
        assert json.loads(capsys.readouterr().out)["state"] == "blocked"
    with pytest.raises(ValueError, match="file set"):
        read_records(project[3])  # Rejected data cannot become a valid report.


def test_final_freezes_elapsed_time_and_dashboard_redacts_private_text(
    project, capsys, monkeypatch,
):
    from inferrsi.harness import optimization

    start(project, capsys, extra=("--condition", "token=condition-secret"))
    repo, _, _, root = project
    (repo / "config.json").write_text('{"metric":20}', encoding="utf-8")
    assert main(["campaign", "round", "--directory", str(root), "--candidate", str(repo),
                 "--hypothesis", "token=hypothesis-secret C:/private/file"]) == 0
    capsys.readouterr()
    assert main(["campaign", "final", "--directory", str(root),
                 "--reason", "token=stop-secret"]) == 0
    assert not json.loads(capsys.readouterr().out)["can_finalize"]
    original = read_records(root)[2]["wall_elapsed_seconds"]
    monkeypatch.setattr(optimization.time, "time", lambda: 10**12)
    assert read_records(root)[2]["wall_elapsed_seconds"] == original
    html = render_dashboard(dashboard_snapshot(root))
    for private in ("condition-secret", "hypothesis-secret", "stop-secret", "C:/private/file"):
        assert private not in html
    assert "Cumulative observed tokens" in html and "Not recorded" in html


@pytest.mark.parametrize("side,verdict", [("baseline", "INCONCLUSIVE"), ("candidate", "FAIL")])
def test_dashboard_shows_failed_independent_final_separately_from_search(
    project, capsys, side, verdict,
):
    quality = project[1] / "quality.py"
    quality.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "# Synthetic final-only rejection exercises result presentation, not quality policy.\n"
        "passed = not ('final' in Path(sys.argv[2]).parts and "
        f"Path(sys.argv[1]).name == {side!r})\n"
        "Path(sys.argv[2]).write_text(json.dumps({'correct':passed}))\n", encoding="utf-8")
    start(project, capsys)
    submit(project, capsys, 20)
    assert main(["campaign", "final", "--directory", str(project[3]),
                 "--reason", "Search done"]) == 2
    capsys.readouterr()
    snapshot = dashboard_snapshot(project[3])
    assert snapshot["data"]["candidates"][0]["verdict"] == "PASS"
    assert f"Independent final: {verdict}" in snapshot["chart"]
    assert "Campaign state: blocked" in snapshot["chart"]
    assert "observation.json" in snapshot["chart"]


def test_final_reserve_blocks_search_but_allows_final(project, capsys, monkeypatch):
    from inferrsi.harness import optimization

    start(project, capsys)
    submit(project, capsys, 20)
    plan, state, _ = read_records(project[3])
    monkeypatch.setattr(optimization.time, "time", lambda: state["deadline"] - 10)
    with pytest.raises(SystemExit):
        submit(project, capsys, 30)
    assert optimization.status(project[3])["can_finalize"]
    assert plan["final_reserve_seconds"] == 20
    assert main(["campaign", "final", "--directory", str(project[3]),
                 "--reason", "Search time exhausted"]) == 0
    capsys.readouterr()
