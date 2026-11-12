"""Task-owned integration checks for both standalone plugin distributions."""

import json

from tests.test_codex_plugin import distribution as distribution
from tests.test_codex_plugin import invoke
from tests.test_project_optimization import project as project


def test_isolated_benchmark_child_uses_its_bundled_runtime(distribution, tmp_path, monkeypatch):
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "inferrsi.py").write_text("raise RuntimeError('wrong child runtime')\n")
    (tmp_path / "inferrsi.py").write_text("raise RuntimeError('wrong cwd runtime')\n")
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    result = invoke(distribution, tmp_path, "benchmarks", "run", "moe-forward-npu", "--help")
    assert result.returncode == 0, result.stderr
    assert "--pairs" in result.stdout and "--candidate" in result.stdout


def test_isolated_tts_entry_prepares_its_bundled_workload(distribution, tmp_path):
    prepared = tmp_path / "prepared"
    result = invoke(
        distribution, tmp_path, "benchmarks", "run", "qwen3-tts-npu", "prepare",
        "--output-dir", str(prepared), "--concurrency", "1", "--warmups", "1",
        "--quality-scorer-id", "synthetic-software-control",
        "--min-improvement-pct", "0", "--max-error-rate-increase", "0",
        "--max-speaker-drop", "0", "--max-duration-change-pct", "0",
        "--max-ttfa-regression-pct", "0",
    )
    assert result.returncode == 0, result.stderr
    assert len((prepared / "workload.jsonl").read_text(encoding="utf-8").splitlines()) == 12
    assert (prepared / "benchmark.py").is_file() and (prepared / "evaluation.py").is_file()
    assert json.loads((prepared / "policy.json").read_text())["quality_scorer_id"] == (
        "synthetic-software-control"
    )


def test_current_agent_session_uses_bundled_task_and_enforces_rounds(distribution, tmp_path):
    session = tmp_path / "optimization-session"
    started = invoke(
        distribution, tmp_path, "benchmarks", "session", "start", "qwen21-denoise-npu",
        "--session", str(session), "--rounds", "2", "--max-minutes", "5",
        "--evaluation-timeout-seconds", "30", "--condition", "software-control",
        "--evaluation-args", "--pairs 2 --samples 1 --warmups 1",
    )
    assert started.returncode == 0, started.stderr
    assert json.loads(started.stdout)["next_action"] == "edit_candidate_and_submit_round"
    assert (session / "frozen/optimization.py").is_file()
    assert (session / "work/candidate.py").is_file()
    captured = invoke(
        distribution, tmp_path, "benchmarks", "session", "knowledge", "--session", str(session),
        "--query", "cgroupv2", "--context-bytes", "2048",
    )
    assert captured.returncode == 0, captured.stderr
    assert json.loads(captured.stdout)["reference"]["kind"] == "delivered_context"
    final = invoke(
        distribution, tmp_path, "benchmarks", "session", "final", "--session", str(session)
    )
    assert final.returncode == 2 and "planned round" in final.stderr


def test_isolated_plugin_runs_project_round_and_retained_final(distribution, tmp_path, project):
    repo, protocol, instructions, root = project
    started = invoke(
        distribution, tmp_path, "campaign", "start", "--directory", str(root),
        "--repo", str(repo), "--include", "engine.py", "--include", "config.json",
        "--protocol", str(protocol), "--instructions", str(instructions),
        "--measure-command", '"{python}" "{protocol}/measure.py" "{candidate}" "{result}"',
        "--quality-command", '"{python}" "{protocol}/quality.py" "{candidate}" "{result}"',
        "--metric-key", "metric", "--metric-unit", "synthetic-units", "--direction", "maximize",
        "--quality-key", "correct", "--scope", "synthetic-software-control",
        "--min-improvement-pct", "1", "--warmups", "0", "--repetitions", "1",
        "--rounds", "1", "--max-minutes", "5", "--evaluation-timeout-seconds", "30",
    )
    assert started.returncode == 0, started.stderr
    (repo / "config.json").write_text('{"metric":20}', encoding="utf-8")
    submitted = invoke(distribution, tmp_path, "campaign", "round", "--directory", str(root),
                       "--candidate", str(repo), "--hypothesis", "Synthetic fixture change")
    assert submitted.returncode == 0, submitted.stderr
    assert json.loads(submitted.stdout)["best"]["score"] == 20
    (repo / "engine.py").write_text("raise RuntimeError('unsubmitted')", encoding="utf-8")
    final = invoke(distribution, tmp_path, "campaign", "final", "--directory", str(root),
                   "--reason", "Synthetic software control finished")
    assert final.returncode == 0, final.stderr
    assert json.loads(final.stdout)["state"] == "completed"
    rendered = invoke(distribution, tmp_path, "dashboard", "--input", str(root),
                      "--output", str(tmp_path / "report.html"))
    assert rendered.returncode == 0, rendered.stderr
    assert "Independent final: PASS" in (tmp_path / "report.html").read_text(encoding="utf-8")
