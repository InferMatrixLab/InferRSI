"""Φ-Bench adapter: package reading, control judgment and executor assembly (CPU only)."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.workflows import external_benchmark as ext
from inferrsi.benchmark.external import phibench

TASK = "kfc/fake-planner"

DOCKERFILE = """# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm
ARG ARCH_LIST=8.9
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC \\
    PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y git
ENV VENV=/opt/kernelbench-venv
RUN python3 -m venv "$VENV"
ENV PATH=$VENV/bin:$PATH
RUN mkdir -p /app/repo /logs/verifier
COPY environment/repo/ /app/repo/
COPY instruction.md /app/instruction.md
RUN cd /app/repo && git init -q && git add -A && git commit -qm baseline
RUN mkdir -p /opt/verifier-baseline \\
 && cp "/app/repo/planner.py" "/opt/verifier-baseline/planner.py"
RUN python - <<'PY'
COPY should-not-be-read /nowhere
PY
ENV PYTHONPATH=/app/repo ARCH=${ARCH_LIST}
WORKDIR /app/repo
"""

# A grader that scores the planner's VALUE: 1 -> baseline, 4 -> reference, 0 -> broken.
TEST_SH = """#!/bin/bash
mkdir -p /logs/verifier
v=$(python3 -c 'import planner; print(planner.VALUE)')
base=$(python3 -c 'import runpy
print(runpy.run_path("/opt/verifier-baseline/planner.py")["VALUE"])')
python3 - "$v" "$base" <<'PY'
import json, sys
v, base = int(sys.argv[1]), int(sys.argv[2])
hard = []
if v == 0:
    hard.append("hidden_correctness_failed")
speed = (v / base) if v else 1.0
if speed <= 1 and not hard:
    hard.append("speedup_not_above_baseline")
json.dump({"reward": 0.0, "speedup": speed, "ref_speedup": 4.0,
           "hard_fail_reasons": hard}, open("/logs/verifier/reward.json", "w"))
PY
"""

SOLVE_SH = """#!/bin/bash
case "${1:-}" in
  --noop) exit 0 ;;
  --negative) sed -i 's/VALUE = 1/VALUE = 0/' /app/repo/planner.py ;;
  *) sed -i 's/VALUE = 1/VALUE = 4/' /app/repo/planner.py ;;
esac
"""

PRE_ARTIFACTS = """#!/bin/bash
mkdir -p /logs/artifacts
git -C /app/repo diff > /logs/artifacts/model.patch
echo /app/repo/planner.py > /logs/artifacts/model_files.txt
"""


@pytest.fixture
def suite(tmp_path):
    root = tmp_path / "phibench"
    package = root / "tasks" / "kfc" / "fake-planner" / "task"
    (package / "environment" / "repo").mkdir(parents=True)
    (package / "environment" / "Dockerfile").write_text(DOCKERFILE)
    (package / "environment" / "repo" / "planner.py").write_text("VALUE = 1\n")
    (package / "instruction.md").write_text("Make VALUE larger.\n")
    (package / "task.toml").write_text('[verifier]\ntimeout_sec = 60\n')
    (package / "tests").mkdir()
    (package / "tests" / "test.sh").write_text(TEST_SH)
    (package / "solution").mkdir()
    (package / "solution" / "solve.sh").write_text(SOLVE_SH)
    (package / "pre_artifacts.sh").write_text(PRE_ARTIFACTS)
    index = {"tasks": [{
        "bench": "kfc", "task": "fake-planner",
        "package_root": "tasks/kfc/fake-planner/task", "gpus": 0,
        "primary_edit_paths": ["/app/repo/planner.py"], "reward_class": "performance",
        "ref_speedup": 4.0, "has_oracle": True, "max_submissions": 1,
    }]}
    (root / "tasks_index.json").write_text(json.dumps(index))
    return root


def score(reward, speedup=None, hard=(), ref=None):
    return {"reward": reward, "speedup": speedup, "ref_speedup": ref,
            "hard_fail_reasons": list(hard)}


def test_reads_task_from_index(suite):
    task = phibench.get_task(suite, TASK)
    assert task.task_id == TASK
    assert task.package_root == (suite / "tasks/kfc/fake-planner/task").resolve()
    assert task.reward_class == "performance" and task.ref_speedup == 4.0
    assert [t.task_id for t in phibench.list_tasks(suite)] == [TASK]


@pytest.mark.parametrize("task_id", ["fake-planner", "kfc/../x", "other/fake-planner"])
def test_rejects_malformed_task_ids(suite, task_id):
    with pytest.raises(ValueError):
        phibench.get_task(suite, task_id)


def test_unknown_task_and_missing_index(suite, tmp_path):
    with pytest.raises(ValueError, match="Unknown"):
        phibench.get_task(suite, "kfc/absent")
    with pytest.raises(ValueError, match="Not a Φ-Bench clone"):
        phibench.list_tasks(tmp_path / "empty")


def test_package_root_cannot_escape_suite(suite):
    index = json.loads((suite / "tasks_index.json").read_text())
    index["tasks"][0]["package_root"] = "../elsewhere"
    (suite / "tasks_index.json").write_text(json.dumps(index))
    with pytest.raises(ValueError, match="escapes"):
        phibench.get_task(suite, TASK)


def test_read_reward_merges_state_and_falls_back_to_text(tmp_path):
    (tmp_path / "reward.json").write_text(json.dumps(
        {"reward": 0.25, "speedup": 5.0, "ref_speedup": 4.0, "hard_fail_reasons": ["a"],
         "schema_version": "v3"}))
    (tmp_path / "verifier_state.json").write_text(json.dumps({"hard_fail_reasons": ["a", "b"]}))
    result = phibench.read_reward(tmp_path)
    assert result["reward"] == 0.25 and result["speedup"] == 5.0
    assert result["hard_fail_reasons"] == ["a", "b"] and result["source"] == "reward.json"
    (tmp_path / "reward.json").write_text("{broken")
    (tmp_path / "reward.txt").write_text("1.0\n")
    assert phibench.read_reward(tmp_path)["reward"] == 1.0
    assert phibench.read_reward(tmp_path / "missing")["reward"] is None


def test_read_reward_also_reads_metrics_json_like_the_runner(tmp_path):
    (tmp_path / "metrics.json").write_text(json.dumps(
        {"reward": 0.0, "speedup": 2.0, "hard_fail_reasons": ["build_check_failed"]}))
    (tmp_path / "reward.txt").write_text("0.0\n")
    result = phibench.read_reward(tmp_path)
    assert result["reward"] == 0.0 and result["source"] == "metrics.json"
    assert result["speedup"] == 2.0 and result["hard_fail_reasons"] == ["build_check_failed"]


@pytest.mark.parametrize(("control", "value", "verdict"), [
    ("noop", score(0.0, 1.0, ["speedup_not_above_baseline"]), "PASS"),
    ("noop", score(0.2, 5.0), "FAIL"),
    ("negative", score(0.0, 1.0, ["hidden_correctness_failed"]), "PASS"),
    ("negative", score(0.5), "FAIL"),
    ("negative", None, "INCONCLUSIVE"),
    ("oracle", score(0.0, 4.0001), "PASS"),
    ("oracle", score(0.0, 3.0), "FAIL"),
    ("oracle", score(0.0, 4.0, ["hidden_correctness_failed"]), "FAIL"),
    ("oracle", score(0.0), "INCONCLUSIVE"),
    ("noop", score(0.0, hard=["verifier_timed_out"]), "INCONCLUSIVE"),
    ("negative", score(0.0, hard=["verifier_timed_out"]), "INCONCLUSIVE"),
    ("oracle", score(0.0, 4.0, ["verifier_timed_out"]), "INCONCLUSIVE"),
])
def test_judges_controls_against_suite_expectations(suite, control, value, verdict):
    task = phibench.get_task(suite, TASK)
    check = phibench.judge_control(task, control, value, oracle_tolerance=0.001)
    assert check["verdict"] == verdict


def test_performance_oracle_without_frozen_tolerance_is_inconclusive(suite):
    task = phibench.get_task(suite, TASK)
    check = phibench.judge_control(task, "oracle", score(0.0, 4.0))
    assert check["verdict"] == "INCONCLUSIVE"


def test_implementation_oracle_must_score_one(suite):
    task = phibench.get_task(suite, TASK)
    task = phibench.PhiTask(**{**task.__dict__, "reward_class": "implementation"})
    assert phibench.judge_control(task, "oracle", score(1.0))["verdict"] == "PASS"
    assert phibench.judge_control(task, "oracle", score(0.0))["verdict"] == "FAIL"


def test_assessment_takes_the_worst_verdict(suite):
    task = phibench.get_task(suite, TASK)
    good = {"noop": score(0.0), "negative": score(0.0), "oracle": score(0.0, 4.0)}
    assert phibench.assess_controls(task, good, oracle_tolerance=0.0)["verdict"] == "PASS"
    assert phibench.assess_controls(task, {**good, "noop": None},
                                    oracle_tolerance=0.0)["verdict"] == "INCONCLUSIVE"
    assert phibench.assess_controls(task, {**good, "negative": score(1.0)},
                                    oracle_tolerance=0.0)["verdict"] == "FAIL"


def test_parse_dockerfile_keeps_replayable_steps_and_lists_the_rest(suite):
    plan = ext.parse_dockerfile(suite / "tasks/kfc/fake-planner/task/environment/Dockerfile")
    assert plan["copies"] == [("environment/repo/", "/app/repo/"),
                              ("instruction.md", "/app/instruction.md")]
    assert plan["baseline_copies"] == [
        ("/app/repo/planner.py", "/opt/verifier-baseline/planner.py")]
    assert plan["env"]["PATH"].startswith("/opt/kernelbench-venv/bin:/usr/local/sbin")
    assert plan["env"]["PYTHONPATH"] == "/app/repo" and plan["env"]["TZ"] == "UTC"
    assert "DEBIAN_FRONTEND" not in plan["env"] and plan["env"]["ARCH"] == "8.9"
    assert "ARCH_LIST" not in plan["env"]
    assert plan["workdir"] == "/app/repo"
    assert any(step.startswith("RUN apt-get") for step in plan["unreplayed"])
    assert any(step.startswith("RUN python - <<") for step in plan["unreplayed"])


def test_stage_rootless_rebuilds_the_image_layout(suite, tmp_path):
    task = phibench.get_task(suite, TASK)
    env_dir = tmp_path / "prepared-env"
    env_dir.mkdir()
    record = ext.stage_rootless(task, tmp_path / "root", python="python3", python_env=env_dir)
    root = tmp_path / "root"
    repo = root / "app" / "repo"
    count = subprocess.run(["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                            capture_output=True, text=True, check=True).stdout
    assert count == "1" and status == ""
    assert (root / "opt/verifier-baseline/planner.py").read_text() == "VALUE = 1\n"
    assert (root / "app/instruction.md").is_file() and (root / "tests/test.sh").is_file()
    assert (root / "opt/kernelbench-venv").resolve() == env_dir.resolve()
    assert record["fidelity"] == "approximate" and record["unreplayed_dockerfile_steps"]
    with pytest.raises(ValueError, match="already exists"):
        ext.stage_rootless(task, root, python="python3", python_env=env_dir)


def test_proot_argv_maps_container_paths(tmp_path):
    argv = ext.proot_argv("proot", tmp_path, "bash /tests/test.sh", env={"A": "1"},
                          cwd="/app/repo", extra_binds=[(tmp_path / "s", "/solution")])
    pairs = [argv[i + 1] for i, item in enumerate(argv) if item == "-b"]
    assert f"{tmp_path.resolve() / 'app'}:/app" in pairs
    assert f"{tmp_path.resolve() / 'tests'}:/tests" in pairs
    assert f"{tmp_path.resolve() / 's'}:/solution" in pairs
    assert argv[argv.index("-w") + 1] == "/app/repo"
    assert argv[-4:] == ["HOME=/root", "bash", "-c", "bash /tests/test.sh"]
    assert "A=1" in argv


def test_docker_executor_delegates_controls_to_the_suite_runner(suite, tmp_path):
    task = phibench.get_task(suite, TASK)
    argv = ext.docker_argv(task, "negative", tmp_path, python="python3",
                           runner_args=["--build-network", "host"])
    assert argv[1] == str(suite.resolve() / "scripts" / "run_task.py")
    assert argv[argv.index("--oracle-variant") + 1] == "negative"
    assert argv[argv.index("--agent") + 1] == "oracle"
    assert argv[-2:] == ["--build-network", "host"]
    with pytest.raises(ValueError, match="reference controls only"):
        ext.docker_argv(task, "candidate", tmp_path, python="python3")


def test_docker_run_keeps_the_runners_hard_fails(suite, tmp_path):
    # The runner writes verifier_timed_out into run.json, not into the verifier directory.
    runner = suite / "scripts" / "run_task.py"
    runner.parent.mkdir()
    runner.write_text(
        "import json, os, sys\n"
        "a = sys.argv\n"
        "run = os.path.join(a[a.index('--runs-dir') + 1], a[a.index('--run-name') + 1])\n"
        "os.makedirs(os.path.join(run, 'verifier'))\n"
        "json.dump({'reward': 0.0}, open(os.path.join(run, 'verifier', 'reward.json'), 'w'))\n"
        "json.dump({'status': 'ok', 'hard_fail_reasons': ['verifier_timed_out']},\n"
        "          open(os.path.join(run, 'run.json'), 'w'))\n")
    task = phibench.get_task(suite, TASK)
    result = ext.run_mode(task, "noop", tmp_path / "out", executor="docker",
                          python=sys.executable)
    assert result["status"] == "graded"
    assert result["score"]["hard_fail_reasons"] == ["verifier_timed_out"]
    assert phibench.judge_control(task, "noop", result["score"])["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize(("mode", "options", "message"), [
    ("candidate", {}, "candidate-patch"),
    ("oracle", {"candidate_patch": Path("x.patch")}, "candidate-patch"),
    ("agent", {}, "agent-command"),
    ("oracle", {"agent_env": {"A": "1"}}, "agent-env"),
    ("bogus", {}, "Unknown mode"),
])
def test_run_mode_validates_inputs(suite, tmp_path, mode, options, message):
    task = phibench.get_task(suite, TASK)
    with pytest.raises(ValueError, match=message):
        ext.run_mode(task, mode, tmp_path / "out", executor="rootless", proot="proot", **options)


def test_agent_timeout_comes_from_the_task(suite):
    task = phibench.get_task(suite, TASK)
    assert ext._agent_timeout(task) == 5400.0
    (task.package_root / "task.toml").write_text(
        "[agent]\ntimeout_sec = 21600\n\n[verifier]\ntimeout_sec = 60\n")
    assert ext._agent_timeout(task) == 21600.0


def test_timeouts_fall_back_like_the_suite_runner(suite):
    # Most packages set no [verifier] timeout_sec; the runner then uses top-level
    # timeout_sec or 3600 s, never "no limit".
    task = phibench.get_task(suite, TASK)
    (task.package_root / "task.toml").write_text("[verifier]\nentrypoint = \"tests/test.sh\"\n")
    assert ext._verifier_timeout(task) == 3600.0
    (task.package_root / "task.toml").write_text(
        "timeout_sec = 900\nagent_timeout_sec = 1200\n\n[verifier]\nmode = \"shared\"\n")
    assert ext._verifier_timeout(task) == 900.0 and ext._agent_timeout(task) == 1200.0


def test_cli_lists_suite_tasks(suite, capsys):
    assert main(["benchmarks", "external", "list", "--root", str(suite)]) == 0
    assert [t["task"] for t in json.loads(capsys.readouterr().out)] == [TASK]


PROOT = os.environ.get("INFERRSI_TEST_PROOT") or shutil.which("proot")


@pytest.mark.skipif(not PROOT, reason="needs proot (set INFERRSI_TEST_PROOT)")
def test_rootless_selfcheck_and_candidate_end_to_end(suite, tmp_path):
    task = phibench.get_task(suite, TASK)
    options = {"executor": "rootless", "proot": PROOT, "python": "python3"}
    result = ext.selfcheck(task, tmp_path / "out", oracle_tolerance=0.0, **options)
    assert result["verdict"] == "PASS", result
    assert result["runs"]["negative"]["score"]["hard_fail_reasons"] == ["hidden_correctness_failed"]
    patch = tmp_path / "cand.patch"
    patch.write_text((tmp_path / "out/oracle/root/logs/artifacts/model.patch").read_text())
    scored = ext.run_mode(task, "candidate", tmp_path / "out", candidate_patch=patch, **options)
    assert scored["score"]["speedup"] == 4.0 and scored["model_patch_bytes"] > 0
    agent = ext.run_mode(task, "agent", tmp_path / "agent", **options,
                         agent_env={"PHI_TEST_TOKEN": "forwarded"},
                         agent_command="test ! -e /tests && test ! -e /solution && "
                                       "test \"$PHI_TEST_TOKEN\" = forwarded && "
                                       "test -f $PHI_INSTRUCTION && "
                                       "sed -i 's/VALUE = 1/VALUE = 2/' planner.py")
    assert agent["score"]["speedup"] == 2.0 and agent["score"]["hard_fail_reasons"] == []
    assert agent["grading_assets_exposed_to_agent"] is False
    assert (tmp_path / "agent/agent/root/tests/test.sh").is_file()



@pytest.fixture(scope="module")
def plugin(tmp_path_factory):
    """A real built InferRSI Codex plugin, as a user would install it."""
    out = tmp_path_factory.mktemp("plugin") / "inferrsi"
    repo = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, str(repo / "tools" / "build_codex_plugin.py"),
                    "--output", str(out)], check=True, capture_output=True, text=True)
    return out


def test_inferrsi_plugin_is_only_for_rootless_agent_mode(suite, tmp_path):
    task = phibench.get_task(suite, TASK)
    with pytest.raises(ValueError, match="inferrsi-plugin"):
        ext.run_mode(task, "oracle", tmp_path / "a", executor="rootless", proot="proot",
                     inferrsi_plugin=Path("p"))
    with pytest.raises(ValueError, match="inferrsi-plugin"):
        ext.run_mode(task, "agent", tmp_path / "b", executor="docker", agent_command="true",
                     inferrsi_plugin=Path("p"))


def test_stage_inferrsi_plugin_rejects_an_unbuilt_template(suite, tmp_path):
    task = phibench.get_task(suite, TASK)
    root = tmp_path / "root"
    ext.stage_rootless(task, root, python="python3", include_tests=False,
                       include_solution=False)
    template = Path(__file__).resolve().parents[2] / "plugins" / "inferrsi"
    with pytest.raises(ValueError, match="build_codex_plugin"):
        ext.stage_inferrsi_plugin(root, template)


def test_stage_inferrsi_plugin_places_the_plugin_and_names_it(suite, tmp_path, plugin):
    task = phibench.get_task(suite, TASK)
    root = tmp_path / "root"
    ext.stage_rootless(task, root, python="python3", include_tests=False,
                       include_solution=False)
    original = (root / "app/instruction.md").read_text()
    record = ext.stage_inferrsi_plugin(root, plugin)
    assert record.pop("original_instruction") == original
    staged = root / "opt/inferrsi-plugin"
    launcher = staged / "skills/inferrsi/scripts/inferrsi.py"
    assert (staged / "plugin.json").is_file() and launcher.is_file()
    noted = (root / "app/instruction.md").read_text()
    assert noted.startswith(original) and "Use InferRSI" in noted
    assert "/opt/inferrsi-plugin/skills/inferrsi/SKILL.md" in noted
    assert record["content_sha256"] and record["usage"] == "plugin directory + prompt"
    info = subprocess.run([sys.executable, "-X", "utf8", str(launcher), "--plugin-info"],
                          check=True, capture_output=True, text=True)
    assert json.loads(info.stdout)["content_sha256"] == record["content_sha256"]


@pytest.mark.skipif(not PROOT, reason="needs proot (set INFERRSI_TEST_PROOT)")
def test_rootless_agent_with_and_without_inferrsi(suite, tmp_path, plugin):
    task = phibench.get_task(suite, TASK)
    options = {"executor": "rootless", "proot": PROOT, "python": "python3"}
    edit = "sed -i 's/VALUE = 1/VALUE = 2/' planner.py"
    control = ext.run_mode(task, "agent", tmp_path / "control", **options,
                           agent_command="test ! -e /opt/inferrsi-plugin && "
                                         "! grep -q InferRSI /app/instruction.md && " + edit)
    launcher = "/opt/inferrsi-plugin/skills/inferrsi/scripts/inferrsi.py"
    arm = ext.run_mode(task, "agent", tmp_path / "arm", **options, inferrsi_plugin=plugin,
                       agent_command="test ! -e /tests && test ! -e /solution && "
                                     f"grep -q {launcher} /app/instruction.md && "
                                     f"python3 -X utf8 {launcher} skills enter task-performance "
                                     "> /tmp/enter.json && " + edit)
    for result in (control, arm):
        assert result["status"] == "graded", result
        assert result["score"]["speedup"] == 2.0
        assert result["grading_assets_exposed_to_agent"] is False
    assert "inferrsi" not in control and arm["inferrsi"]["mount"] == "/opt/inferrsi-plugin"
    entered = json.loads((tmp_path / "arm/agent/root/tmp/enter.json").read_text())
    assert entered["name"] == "task-performance"
    restored = (tmp_path / "arm/agent/root/app/instruction.md").read_text()
    assert restored == (task.package_root / "instruction.md").read_text()
    assert "inferrsi" not in (tmp_path / "arm/agent/root/logs/artifacts/model.patch").read_text()


def test_rootless_steps_keep_the_host_gpu_selection(suite, tmp_path, monkeypatch):
    # `env -i` inside proot drops the caller's CUDA_VISIBLE_DEVICES: a run reserved on
    # GPU 5 then sees all cards and lands on GPU 0, next to other people's jobs.
    task = phibench.get_task(suite, TASK)
    calls = []

    def fake_run(argv, log, timeout):
        calls.append(argv)
        return {"exit_code": 0, "timed_out": False, "seconds": 0.0, "log": str(log)}

    monkeypatch.setattr(ext, "_run", fake_run)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "5")
    ext.run_rootless(task, "agent", tmp_path / "out", proot="proot", python="python3",
                     agent_command="true")
    assert len(calls) == 3
    for argv in calls:
        assert "CUDA_VISIBLE_DEVICES=5" in argv
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES")
    calls.clear()
    ext.run_rootless(task, "agent", tmp_path / "out2", proot="proot", python="python3",
                     agent_command="true")
    assert not any(arg.startswith("CUDA_VISIBLE_DEVICES=") for argv in calls for arg in argv)


def test_parse_dockerfile_unquotes_build_args(tmp_path):
    # Docker strips the quotes of `ARG X="9.0"`; keeping them hands torch an arch
    # list of `"9.0"`, which it rejects, so every CUDA-extension task fails to build.
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text('FROM x\nARG ARCH="9.0"\nARG EMPTY=\nARG BARE=1.2\n'
                          "ENV TORCH_CUDA_ARCH_LIST=${ARCH} A=${EMPTY}x B=$BARE\n")
    env = ext.parse_dockerfile(dockerfile)["env"]
    assert env["TORCH_CUDA_ARCH_LIST"] == "9.0"
    assert env["A"] == "x" and env["B"] == "1.2"


def test_controls_see_the_package_at_task_and_the_agent_does_not(suite, tmp_path, monkeypatch):
    # lh packages ship oracle.patch next to task.toml, and their solve.sh looks for it
    # under /task (the suite mounts the package there for reference runs).
    task = phibench.get_task(suite, TASK)
    calls = []

    def fake_run(argv, log, timeout):
        calls.append(argv)
        return {"exit_code": 0, "timed_out": False, "seconds": 0.0, "log": str(log)}

    monkeypatch.setattr(ext, "_run", fake_run)
    mount = f"{task.package_root.resolve()}:/task"
    ext.run_rootless(task, "oracle", tmp_path / "oracle", proot="proot", python="python3")
    assert mount in calls[0]
    calls.clear()
    ext.run_rootless(task, "agent", tmp_path / "agent", proot="proot", python="python3",
                     agent_command="true")
    assert not any(mount in argv for argv in calls)
    # proot shows the agent the whole host filesystem, so the suite clone (tests/ and
    # solution/ at their host path) is covered with an empty directory in its step only.
    cover = f"{(tmp_path / 'agent/suite-hidden').resolve()}:{task.suite_root}"
    assert cover in calls[0] and not any(cover in argv for argv in calls[1:])


@pytest.mark.skipif(not PROOT, reason="needs proot (set INFERRSI_TEST_PROOT)")
def test_agent_step_cannot_plant_a_score(suite, tmp_path):
    # /logs/verifier is shared with the grading step: nothing the agent writes there may
    # reach the score.
    task = phibench.get_task(suite, TASK)
    agent = ext.run_mode(task, "agent", tmp_path / "out", executor="rootless", proot=PROOT,
                         python="python3",
                         agent_command="echo '{\"hard_fail_reasons\": [\"planted\"]}' "
                                       "> /logs/verifier/verifier_state.json && "
                                       "sed -i 's/VALUE = 1/VALUE = 2/' planner.py")
    assert agent["landing"]["exit_code"] == 0, agent
    assert agent["score"]["speedup"] == 2.0 and agent["score"]["hard_fail_reasons"] == []


@pytest.mark.skipif(not PROOT, reason="needs proot (set INFERRSI_TEST_PROOT)")
def test_an_agent_that_fails_or_times_out_is_still_graded(suite, tmp_path):
    # The suite runner grades the tree an agent leaves, whatever its exit; dropping those
    # runs would score only the agents that finished cleanly.
    task = phibench.get_task(suite, TASK)
    agent = ext.run_mode(task, "agent", tmp_path / "out", executor="rootless", proot=PROOT,
                         python="python3",
                         agent_command="sed -i 's/VALUE = 1/VALUE = 2/' planner.py; exit 3")
    assert agent["status"] == "graded" and agent["warnings"] == ["agent_exited_nonzero"]
    assert agent["landing"]["exit_code"] == 3 and agent["score"]["speedup"] == 2.0
    (task.package_root / "task.toml").write_text(
        "[agent]\ntimeout_sec = 1\n[verifier]\ntimeout_sec = 60\n")
    late = ext.run_mode(task, "agent", tmp_path / "late", executor="rootless", proot=PROOT,
                        python="python3",
                        agent_command="sed -i 's/VALUE = 1/VALUE = 2/' planner.py; sleep 30")
    assert late["status"] == "graded" and late["warnings"] == ["agent_timed_out"]
    assert late["score"]["speedup"] == 2.0


def test_a_grader_cut_off_at_its_timeout_is_a_hard_fail(suite, tmp_path, monkeypatch):
    task = phibench.get_task(suite, TASK)

    def fake_run(argv, log, timeout):
        timed_out = log.name == "verify.log"
        return {"exit_code": None if timed_out else 0, "timed_out": timed_out,
                "seconds": 0.0, "log": str(log)}

    monkeypatch.setattr(ext, "_run", fake_run)
    result = ext.run_mode(task, "noop", tmp_path / "out", executor="rootless",
                          proot=sys.executable, python="python3")
    assert result["score"]["hard_fail_reasons"] == ["verifier_timed_out", "no_reward_file"]
    assert result["status"] == "no_reward"


def test_a_grader_that_writes_no_reward_is_not_a_score(suite, tmp_path, monkeypatch, capsys):
    task = phibench.get_task(suite, TASK)

    def fake_run(argv, log, timeout):
        return {"exit_code": 0, "timed_out": False, "seconds": 0.0, "log": str(log)}

    monkeypatch.setattr(ext, "_run", fake_run)
    monkeypatch.setattr(ext.shutil, "which", lambda name: name)
    status = main(["benchmarks", "external", "run", "--root", str(suite), "--task", TASK,
                   "--executor", "rootless", "--proot", "proot", "--python", "python3",
                   "--mode", "noop", "--output", str(tmp_path / "out")])
    result = json.loads((tmp_path / "out" / "noop" / "result.json").read_text())
    assert result["status"] == "no_reward" and status == 1
    assert result["score"]["hard_fail_reasons"] == ["no_reward_file"]

    selfcheck = phibench.assess_controls(task, {c: result["score"] for c in phibench.CONTROLS})
    assert selfcheck["verdict"] == "INCONCLUSIVE"
