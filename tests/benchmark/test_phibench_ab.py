"""One-command Φ-Bench A/B: draw, run identity, partial exit and score quality."""

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AB = load("phibench_ab")
TASK = load("phibench_task")


def entry(task, gpus=0):
    return {"bench": task.split("/")[0], "task": task.split("/")[1],
            "task_id": task, "gpus": gpus, "ref_speedup": 1.0,
            "reward_class": "performance", "package_root": "tasks/x/task"}


def plan():
    rows = []
    for index in range(4):
        rows.append(entry(f"kfc/g{index}", 1))
    for index in range(2):
        rows.append(entry(f"kfc/c{index}", 0))
    for index in range(2):
        rows.append(entry(f"lh/g{index}", 1))
    rows.append(entry("lh/c0", 0))
    for index in range(2):
        rows.append(entry(f"e2e/g{index}", 1))
    for row in rows:
        row["task"] = f"{row['bench']}/{row['task']}"
    return rows


def test_allocate_largest_remainder():
    assert AB.allocate({"a": 5, "b": 3, "c": 2}, 5) == {"a": 3, "b": 1, "c": 1}
    assert AB.allocate({"a": 1, "b": 1}, 1) == {"a": 1, "b": 0}


def test_select_keeps_the_suite_mix():
    suite = plan()
    for n in range(1, len(suite) + 1):
        chosen = AB.select(suite, n, 0)
        assert len(chosen) == n
        for bench in ("kfc", "lh", "e2e"):
            size = sum(row["task"].startswith(bench + "/") for row in suite)
            got = sum(row["task"].startswith(bench + "/") for row in chosen)
            assert abs(got - n * size / len(suite)) < 1


def test_select_is_reproducible_and_seed_changes_the_draw():
    suite = plan()
    first = [row["task"] for row in AB.select(suite, 5, 0)]
    assert first == [row["task"] for row in AB.select(suite, 5, 0)]
    assert first != [row["task"] for row in AB.select(suite, 5, 1)]


@pytest.mark.parametrize("n", [0, -1, 12])
def test_n_out_of_range(n):
    with pytest.raises(ValueError):
        AB.select(plan(), n, 0)


def arm(reward, patch=10, timed_out=False):
    return {"status": "graded", "reward": reward, "speedup": 1.0, "hard": [],
            "patch_bytes": patch, "tokens": 100, "landing_timed_out": timed_out}


def write_summary(out, task, *, run_id="run", plan_sha="plan", plugin_sha="plugin",
                  control=0.0, inferrsi=0.0, selfcheck="PASS", ref=1.0,
                  patch=10, finished=True):
    summary = {
        "task": task, "run_id": run_id, "plan_sha256": plan_sha,
        "plugin_sha256": plugin_sha,
        "steps": {"selfcheck": {"verdict": selfcheck}, "calibration": {"median": ref}},
    }
    if control is not None:
        summary["steps"]["control"] = arm(control, patch)
    if inferrsi is not None:
        summary["steps"]["inferrsi"] = arm(inferrsi, patch)
    if finished:
        summary["finished"] = "2026-11-28T00:00:00"
    path = out / "runs" / task.replace("/", "__") / "summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary))


def test_score_reports_quality_and_sensitivity(tmp_path):
    suite = plan()[:5]
    write_summary(tmp_path, "kfc/g0", control=0.0, inferrsi=0.5, patch=10)
    write_summary(tmp_path, "kfc/g1", control=0.4, inferrsi=0.4, selfcheck="FAIL", patch=10)
    write_summary(tmp_path, "kfc/g2", control=0.2, inferrsi=0.1, ref=None, patch=0)
    write_summary(tmp_path, "kfc/g3", control=None, inferrsi=0.3)
    result = AB.score_tasks(suite, tmp_path)
    assert result["scored"] == 3
    assert result["score"] == pytest.approx((0.5 + 0.4 + 0.1) / 3 - (0.0 + 0.4 + 0.2) / 3)
    assert result["quality"] == {
        "selfcheck_pass": 2, "selfcheck_fail": 1, "selfcheck_inconclusive": 0,
        "selfcheck_missing": 0, "no_calibration": 1, "empty_patch": 1, "timed_out": 0,
        "probe_exposed": 0,
    }
    assert result["sensitivity"]["exclude_no_calibration"] == pytest.approx(0.45 - 0.2)
    assert result["sensitivity"]["exclude_selfcheck_not_pass"] == pytest.approx(0.3 - 0.1)
    assert result["sensitivity"]["exclude_empty_patch"] == pytest.approx(0.45 - 0.2)
    assert [item["task"] for item in result["unscored"]] == ["kfc/g3", "kfc/c0"]


def test_reward_none_is_unscored_not_zero(tmp_path):
    write_summary(tmp_path, "kfc/g0", control=0.0, inferrsi=None)
    result = AB.score_tasks(plan()[:1], tmp_path)
    assert result["scored"] == 0 and result["score"] is None
    assert result["unscored"][0]["task"] == "kfc/g0"


def test_finished_requires_the_same_run_plan_and_plugin(tmp_path):
    ident = {"run_id": "run", "plan_sha256": "plan", "plugin_sha256": "plugin"}
    write_summary(tmp_path, "kfc/g0")
    assert AB.finished(AB.task_summary(tmp_path, "kfc/g0"), ident)
    assert not AB.finished(AB.task_summary(tmp_path, "kfc/g0"),
                           {**ident, "run_id": "other"})
    assert not AB.finished(AB.task_summary(tmp_path, "kfc/g0"),
                           {**ident, "plan_sha256": "other"})
    assert not AB.finished(AB.task_summary(tmp_path, "kfc/g0"),
                           {**ident, "plugin_sha256": "other"})
    write_summary(tmp_path, "kfc/c0", finished=False)
    assert not AB.finished(AB.task_summary(tmp_path, "kfc/c0"), ident)


def make_suite(tmp_path):
    root = tmp_path / "phibench"
    package = root / "tasks" / "kfc" / "fake" / "task"
    package.mkdir(parents=True)
    (package / "task.toml").write_text("[verifier]\ntimeout_sec = 60\n")
    (package / "tests").mkdir()
    (package / "tests" / "ref_speedup.txt").write_text("1.0\n")
    (root / "tasks_index.json").write_text(json.dumps({"tasks": [{
        "bench": "kfc", "task": "fake", "package_root": "tasks/kfc/fake/task",
        "gpus": 0, "ref_speedup": 1.0, "reward_class": "performance",
    }]}))
    return root


def test_task_worker_runs_the_whole_sequence_with_a_fake_cli(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_HOME", "HTTPS_PROXY", "HTTP_PROXY"):
        monkeypatch.setenv(name, "test")
    root = make_suite(tmp_path)
    fake = tmp_path / "fake_cli.py"
    fake.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "def value(flag):\n"
        "    return args[args.index(flag) + 1]\n"
        "out = Path(value('--output'))\n"
        "if args[2] == 'selfcheck':\n"
        "    out.mkdir(parents=True, exist_ok=True)\n"
        "    (out / 'selfcheck.json').write_text(json.dumps({'verdict': 'PASS'}))\n"
        "else:\n"
        "    mode = value('--mode')\n"
        "    target = out / mode\n"
        "    target.mkdir(parents=True, exist_ok=True)\n"
        "    reward = 1.0 if mode == 'oracle' else 0.5\n"
        "    (target / 'result.json').write_text(json.dumps({\n"
        "        'status': 'graded',\n"
        "        'score': {'reward': reward, 'speedup': 2.0, 'hard_fail_reasons': []},\n"
        "        'model_patch_bytes': 10,\n"
        "        'landing': {'exit_code': 0, 'seconds': 1},\n"
        "    }))\n"
        "    if mode == 'agent':\n"
        "        (target / 'landing.log').write_text('tokens used\\n100\\n')\n",
        encoding="utf-8",
    )
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "SKILL.md").write_text("x")
    runs = tmp_path / "runs"
    code = TASK.main([
        "--root", str(root), "--runs", str(runs), "--task", "kfc/fake",
        "--plugin", str(plugin), "--executor", "docker",
        "--agent-command", "true",
        "--cli", f"{sys.executable} {fake}", "--run-id", "run", "--plan-sha", "plan",
        "--plugin-sha", "plugin",
    ])
    assert code == 0
    summary = json.loads((runs / "kfc__fake" / "summary.json").read_text())
    assert summary["finished"] and summary["run_id"] == "run"
    assert summary["steps"]["selfcheck"]["verdict"] == "PASS"
    assert summary["steps"]["calibration"]["median"] == 2.0
    assert (root / "tasks/kfc/fake/task/tests/ref_speedup.txt").read_text().strip() == "2"
    assert summary["steps"]["control"]["reward"] == 0.5
    assert summary["steps"]["inferrsi"]["reward"] == 0.5
    assert summary["steps"]["control"]["tokens"] == 100


def test_task_worker_rejects_another_run(tmp_path):
    root = make_suite(tmp_path)
    runs = tmp_path / "runs"
    summary = runs / "kfc__fake" / "summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({"run_id": "other", "plan_sha256": "plan"}))
    args = SimpleNamespace(
        root=root, runs=runs, task="kfc/fake", venv=None, taskenv=None, plugin=None,
        agent_env=[], executor="docker", proot="proot", cli="x", pythonpath=None,
        bind=[], oracle_tolerance=0.03, max_attempts=1, no_calibration=False,
        run_id="run", plan_sha="plan", plugin_sha="plugin", agent_command="x",
    )
    with pytest.raises(SystemExit):
        TASK.Worker(args)


def test_main_score_only_uses_the_saved_task_list(tmp_path):
    root = make_suite(tmp_path)
    out = tmp_path / "run"
    out.mkdir()
    (out / "run.json").write_text(json.dumps({
        "run_id": "run", "plan_sha256": "plan", "plugin_sha256": None,
        "tasks": ["kfc/fake"], "n": 1, "seed": 3,
    }))
    write_summary(out, "kfc/fake", plugin_sha=None)
    assert AB.main(["--root", str(root), "--out", str(out), "--score-only"]) == 0
    result = json.loads((out / "score.json").read_text())
    assert result["tasks"] == 1 and result["scored"] == 1
    assert (result["n"], result["seed"]) == (1, 3)


def test_main_requires_allow_partial_for_an_unfinished_run(tmp_path, capsys):
    root = make_suite(tmp_path)
    out = tmp_path / "run"
    out.mkdir()
    (out / "run.json").write_text(json.dumps({
        "run_id": "run", "plan_sha256": "plan", "plugin_sha256": None,
        "tasks": ["kfc/fake"],
    }))
    assert AB.main(["--root", str(root), "--out", str(out), "--score-only"]) == 2
    assert AB.main(["--root", str(root), "--out", str(out), "--score-only",
                    "--allow-partial"]) == 0
    assert "未跑完或未出分" in capsys.readouterr().err


def test_main_refuses_an_existing_run_without_resume(tmp_path):
    root = make_suite(tmp_path)
    out = tmp_path / "run"
    out.mkdir()
    (out / "run.json").write_text(json.dumps({
        "run_id": "run", "plan_sha256": "plan", "plugin_sha256": "plugin",
        "tasks": ["kfc/fake"],
    }))
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    with pytest.raises(SystemExit):
        AB.main(["--root", str(root), "--out", str(out), "--plugin", str(plugin),
                 "--agent-command", "true"])


def test_main_resume_reuses_finished_tasks(tmp_path, monkeypatch, capsys):
    root = make_suite(tmp_path)
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "SKILL.md").write_text("x")
    out = tmp_path / "run"
    calls = []

    def fake_run_pool(args, tasks, run_dir, ident, workers, prefix):
        calls.append(tasks)
        for item in tasks:
            write_summary(run_dir, item["task"], run_id=ident["run_id"],
                          plan_sha=ident["plan_sha256"],
                          plugin_sha=ident["plugin_sha256"])

    monkeypatch.setattr(AB, "run_pool", fake_run_pool)
    argv = ["--root", str(root), "--out", str(out), "--plugin", str(plugin),
            "--agent-command", "true", "--executor", "docker", "--n", "1",
            "--agent-env", "OPENAI_API_KEY", "--gpu-prefix", "gpu run --", "--no-calibration"]
    assert AB.main(argv) == 0
    assert any(calls)
    saved = json.loads((out / "run.json").read_text())
    assert saved["agent_env"] == ["OPENAI_API_KEY"]
    assert saved["gpu_prefix"] == "gpu run --" and saved["no_calibration"] is True
    first = capsys.readouterr().out
    assert "新跑 1 道" in first
    assert AB.main(["--resume", "--out", str(out)]) == 0
    second = capsys.readouterr().out
    assert "新跑 0 道、复用 1 道" in second


def test_a_new_seed_runs_a_new_sample(tmp_path, monkeypatch):
    root = tmp_path / "suite"
    root.mkdir()
    rows = [{"bench": "kfc", "task": f"t{index}", "gpus": index % 2,
             "package_root": f"tasks/kfc/t{index}", "ref_speedup": 1.0}
            for index in range(6)]
    (root / "tasks_index.json").write_text(json.dumps({"tasks": rows}))
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "SKILL.md").write_text("x")
    runs = []

    def fake_run_pool(args, tasks, run_dir, ident, workers, prefix):
        for item in tasks:
            write_summary(run_dir, item["task"], run_id=ident["run_id"],
                          plan_sha=ident["plan_sha256"],
                          plugin_sha=ident["plugin_sha256"])

    monkeypatch.setattr(AB, "run_pool", fake_run_pool)
    for seed in (1, 2):
        out = tmp_path / f"ab-{seed}"
        assert AB.main(["--root", str(root), "--out", str(out), "--n", "3",
                        "--seed", str(seed), "--plugin", str(plugin),
                        "--agent-command", "true", "--executor", "docker"]) == 0
        runs.append(json.loads((out / "run.json").read_text())["tasks"])
    assert runs[0] != runs[1]
    assert all(len(tasks) == 3 for tasks in runs)


def test_task_worker_retries_the_failed_arm_on_the_next_invocation(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_HOME", "HTTPS_PROXY", "HTTP_PROXY"):
        monkeypatch.setenv(name, "test")
    root = make_suite(tmp_path)
    counter = tmp_path / "counter"
    counter.write_text("0")
    fake = tmp_path / "fake_cli.py"
    fake.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "def value(flag):\n"
        "    return args[args.index(flag) + 1]\n"
        "out = Path(value('--output'))\n"
        "if args[2] == 'selfcheck':\n"
        "    out.mkdir(parents=True, exist_ok=True)\n"
        "    (out / 'selfcheck.json').write_text(json.dumps({'verdict': 'PASS'}))\n"
        "else:\n"
        "    mode = value('--mode')\n"
        "    target = out / mode\n"
        "    target.mkdir(parents=True, exist_ok=True)\n"
        "    arm = '--inferrsi-plugin' in args\n"
        "    count = Path('" + str(counter) + "').read_text()\n"
        "    status = 'graded'\n"
        "    if arm and count == '0':\n"
        "        status = 'error'\n"
        "        Path('" + str(counter) + "').write_text('1')\n"
        "    (target / 'result.json').write_text(json.dumps({\n"
        "        'status': status,\n"
        "        'score': {'reward': 0.5, 'speedup': 1.0, 'hard_fail_reasons': []},\n"
        "        'model_patch_bytes': 10,\n"
        "        'landing': {'exit_code': 0, 'seconds': 1},\n"
        "    }))\n",
        encoding="utf-8",
    )
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "SKILL.md").write_text("x")
    runs = tmp_path / "runs"
    argv = [
        "--root", str(root), "--runs", str(runs), "--task", "kfc/fake",
        "--plugin", str(plugin), "--executor", "docker", "--agent-command", "true",
        "--cli", f"{sys.executable} {fake}", "--run-id", "run", "--plan-sha", "plan",
        "--plugin-sha", "plugin", "--max-attempts", "2",
    ]
    assert TASK.main(argv) == 1
    first = json.loads((runs / "kfc__fake" / "summary.json").read_text())
    assert "finished" not in first
    assert first["attempts"]["inferrsi"] == 1
    assert TASK.main(argv) == 0
    second = json.loads((runs / "kfc__fake" / "summary.json").read_text())
    assert second["finished"] and second["attempts"]["inferrsi"] == 2


def test_main_refuses_a_non_empty_out_without_a_run(tmp_path):
    root = make_suite(tmp_path)
    out = tmp_path / "not-a-run"
    out.mkdir()
    (out / "keep.txt").write_text("do not clobber")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    with pytest.raises(SystemExit):
        AB.main(["--root", str(root), "--out", str(out), "--plugin", str(plugin),
                 "--agent-command", "true"])
    assert (out / "keep.txt").read_text() == "do not clobber"


def test_run_process_kills_the_whole_group_on_timeout(tmp_path):
    pid_file = tmp_path / "child.pid"
    script = tmp_path / "hang.py"
    script.write_text(
        f"""import subprocess, sys, time
subprocess.Popen([sys.executable, "-c",
                  "import os,time;open(r'{pid_file}','w').write(str(os.getpid()));time.sleep(30)"])
time.sleep(30)
""",
        encoding="utf-8",
    )
    code, timed_out = TASK.run_process([sys.executable, str(script)], tmp_path / "hang.log",
                                       1.0, tmp_path, dict(os.environ))
    assert code is None and timed_out
    pid = int(pid_file.read_text())
    time.sleep(0.5)
    state = Path(f"/proc/{pid}/stat")
    if state.exists():
        assert state.read_text().split()[2] == "Z"


def test_a_probe_that_exposes_grading_assets_is_not_scored(tmp_path):
    write_summary(tmp_path, "kfc/g0", control=0.0, inferrsi=0.5)
    path = tmp_path / "runs" / "kfc__g0" / "summary.json"
    summary = json.loads(path.read_text())
    summary["steps"]["probe"] = {"status": "graded", "grading_assets_exposed": True}
    path.write_text(json.dumps(summary))
    result = AB.score_tasks(plan()[:1], tmp_path)
    assert result["scored"] == 0 and result["score"] is None
    assert result["quality"]["probe_exposed"] == 1
    assert result["unscored"][0]["state"] == "probe_failed"


def test_resume_rejects_a_different_plan(tmp_path):
    root = make_suite(tmp_path)
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    out = tmp_path / "run"

    def fake_run_pool(args, tasks, run_dir, ident, workers, prefix):
        for item in tasks:
            write_summary(run_dir, item["task"], run_id=ident["run_id"],
                          plan_sha=ident["plan_sha256"],
                          plugin_sha=ident["plugin_sha256"])

    original = AB.run_pool
    AB.run_pool = fake_run_pool
    try:
        assert AB.main(["--root", str(root), "--out", str(out), "--n", "1",
                        "--plugin", str(plugin), "--agent-command", "true",
                        "--executor", "docker"]) == 0
    finally:
        AB.run_pool = original
    with pytest.raises(SystemExit):
        AB.main(["--resume", "--out", str(out), "--n", "2"])


def test_a_real_run_with_an_unfinished_task_exits_2(tmp_path, monkeypatch, capsys):
    root = tmp_path / "suite"
    root.mkdir()
    rows = [{"bench": "kfc", "task": f"t{index}", "gpus": 0,
             "package_root": f"tasks/kfc/t{index}", "ref_speedup": 1.0}
            for index in range(2)]
    (root / "tasks_index.json").write_text(json.dumps({"tasks": rows}))
    plugin = tmp_path / "plugin"
    plugin.mkdir()

    def fake_run_pool(args, tasks, run_dir, ident, workers, prefix):
        done = [item for item in tasks if item["task"] == "kfc/t0"]
        for item in done:
            write_summary(run_dir, item["task"], run_id=ident["run_id"],
                          plan_sha=ident["plan_sha256"],
                          plugin_sha=ident["plugin_sha256"])

    monkeypatch.setattr(AB, "run_pool", fake_run_pool)
    argv = ["--root", str(root), "--out", str(tmp_path / "run"), "--plugin", str(plugin),
            "--agent-command", "true", "--executor", "docker"]
    assert AB.main(argv) == 2
    assert "未跑完或未出分" in capsys.readouterr().err
    assert AB.main(argv + ["--resume", "--allow-partial"]) == 0
