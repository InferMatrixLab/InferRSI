"""``plan --task`` and ``run --task``: the shared YAML task contract on the plan/run path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.apps import cli
from inferrsi.apps.cli import arguments, task_input
from inferrsi.apps.legacy import run as legacy_run
from inferrsi.contracts import RunSpec

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "task-input"
COMPLETE = FIXTURES / "complete.yaml"
PARTIAL = FIXTURES / "partial.yaml"
HEAD = "abc1234" + "0" * 33
REQUIRED = "the following arguments are required: --baseline-command, --candidate-command"


def _task(tmp_path: Path, source: Path = COMPLETE, *, replace=(), plan_file=True) -> Path:
    """Copy a fixture into tmp_path/task with its repo/ and candidate/ checkouts."""
    directory = tmp_path / "task"
    for name in ("repo", "candidate"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    if plan_file:
        (directory / "plan").mkdir(exist_ok=True)
        (directory / "plan" / "acceptance.md").write_text("frozen gates\n", encoding="utf-8")
    target = directory / source.name
    shutil.copyfile(source, target)
    text = target.read_text(encoding="utf-8")
    for old, new in replace:
        assert old in text, old
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    return target


@pytest.fixture
def caller(tmp_path, monkeypatch) -> Path:
    directory = tmp_path / "caller"
    directory.mkdir()
    monkeypatch.chdir(directory)
    return directory


def _environment(head: str = HEAD) -> dict:
    return {
        "repository": {"available": True, "head": head},
        "device": {"status": "available", "selection_verified": True},
        "target_python": {"environment": {"python": "stub"}},
    }


@pytest.fixture
def inspected(monkeypatch) -> list:
    calls = []

    def fake(repo, repo_type, backend, **kwargs):
        calls.append({"repo": repo, "repo_type": repo_type, "backend": backend, **kwargs})
        return _environment()

    monkeypatch.setattr(cli, "inspect_environment", fake)
    return calls


def _forbid(monkeypatch, *names: str) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid task input must not probe, launch or write")

    for name in names:
        target, _, attribute = name.rpartition(".")
        module = {"cli": cli, "subprocess": subprocess, "os": os, "legacy": legacy_run}[target]
        if hasattr(module, attribute):
            monkeypatch.setattr(module, attribute, forbidden)


def _plan(capsys, *argv: str) -> dict:
    assert cli.main(["plan", *argv]) == 0
    return json.loads(capsys.readouterr().out)


def _exit(capsys, *argv: str) -> str:
    with pytest.raises(SystemExit) as raised:
        cli.main(list(argv))
    assert raised.value.code == 2
    return capsys.readouterr().err


def _expected_spec(directory: Path, caller: Path, **changes) -> dict:
    values = dict(
        repo=str((directory / "repo").resolve()),
        candidate_repo=str((directory / "candidate").resolve()),
        repo_type="vllm",
        backend="cuda",
        scenario="llm.decode",
        mode="code",
        baseline_command=("python", "bench.py", "--variant", "baseline", "--output",
                          "{result}"),
        candidate_command=("python", "bench.py", "--variant", "candidate", "--output",
                           "{result}"),
        validation_command=("python", "quality.py", "--output", "{result}"),
        metric_key="metrics.latency_ms",
        required_trial_checks=("checks.warm",),
        metric_unit="ms",
        comparison_scope="external_command",
        direction="minimize",
        repetitions=5,
        min_improvement_pct=2.5,
        max_minutes=90.0,
        workload_id="fixed-prompts-v1",
        model="<MODEL>",
        model_revision="<MODEL_REVISION>",
        agent="manual",
        device_ids=("0", "1"),
        output_dir=str((caller / "runs").resolve()),
    )
    values.update(changes)
    return json.loads(json.dumps(RunSpec(**values).to_dict()))


def test_plan_with_the_complete_fixture_gives_the_expected_run_spec(
    tmp_path, caller, inspected, capsys,
):
    task_file = _task(tmp_path)
    directory = task_file.parent
    result = _plan(capsys, "--task", str(task_file))
    assert result["run_spec"] == _expected_spec(directory, caller)
    assert inspected == [{
        "repo": str(directory / "repo"), "repo_type": "vllm", "backend": "cuda",
        "device_ids": ("0", "1"), "device_model": "<DEVICE_MODEL>",
        "python": str(directory / ".venv" / "bin" / "python"),
    }]
    assert result["execution"] == "not started"
    assert result["task"]["complete"] and result["task"]["execution"] == "not started"
    for name in ("objective", "plane"):
        assert result["task"]["task"]["optimization"][name]
    assert result["task"]["task"]["environment"]["rounds"] == 4
    assert result["task"]["task"]["acceptance"]["baseline_revision"] == "<baseline_sha>"


def test_plan_task_block_equals_the_agent_preview_and_the_cli_preview(
    tmp_path, caller, inspected, capsys,
):
    task_file = _task(tmp_path)
    for flags, overrides in (([], None),
                             (["--repetitions", "7", "--backend", "rocm"],
                              {"repetitions": 7, "backend": "rocm"})):
        block = _plan(capsys, "--task", str(task_file), *flags)["task"]
        assert block == task_input.preview(task_file, overrides, cwd=str(caller))
        completed = subprocess.run(
            [sys.executable, "-m", "inferrsi", "task", "preview", str(task_file), "--json",
             *flags],
            capture_output=True, text=True, encoding="utf-8", cwd=caller, check=False,
            env=dict(os.environ, PYTHONPATH=str(REPO / "src")),
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout) == block


def test_omitted_flags_keep_yaml_and_explicit_default_valued_flags_override(
    tmp_path, caller, inspected, capsys,
):
    task_file = _task(tmp_path)
    directory = task_file.parent
    plain = _plan(capsys, "--task", str(task_file))
    assert plain["run_spec"]["backend"] == "cuda"
    assert plain["run_spec"]["repetitions"] == 5
    assert plain["run_spec"]["min_improvement_pct"] == 2.5
    assert plain["task"]["sources"]["environment.backend"] == "yaml"

    # The values equal the plan parser defaults, yet they were supplied, so they win.
    result = _plan(capsys, "--task", str(task_file), "--backend", "cpu", "--repetitions", "3",
                   "--baseline-command", "python other.py --output {result}",
                   "--python", "venv/bin/python", "--min-improvement-pct", "2.5")
    assert result["run_spec"] == _expected_spec(
        directory, caller, backend="cpu", repetitions=3,
        baseline_command=("python", "other.py", "--output", "{result}"),
    )
    task = result["task"]
    assert task["task"]["environment"]["backend"] == "cpu"
    assert task["task"]["environment"]["repetitions"] == 3
    for path in ("environment.backend", "environment.repetitions",
                 "environment.baseline_command", "environment.python"):
        assert task["sources"][path] == "cli", path
    assert task["sources"]["acceptance.min_improvement_pct"] == "yaml"
    assert task["sources"]["environment.max_minutes"] == "yaml"
    assert inspected[-1]["backend"] == "cpu"
    assert inspected[-1]["python"] == str(caller / "venv" / "bin" / "python")


def test_missing_optional_python_and_candidate_use_the_caller_and_the_baseline(
    tmp_path, caller, inspected, capsys,
):
    task_file = _task(tmp_path, replace=(
        ("  candidate_repository: candidate\n", ""), ("  python: .venv/bin/python\n", ""),
    ))
    result = _plan(capsys, "--task", str(task_file))
    assert result["run_spec"]["candidate_repo"] is None
    assert inspected[-1]["python"] == sys.executable
    assert result["task"]["task"]["environment"]["python"] is None


@pytest.mark.parametrize("flags, field", [
    (("--min-improvement-pct", "5"), "acceptance.min_improvement_pct"),
    (("--min-improvement-pct", "0"), "acceptance.min_improvement_pct"),
    (("--metric-key", "metrics.throughput"), "acceptance.metric_key"),
    (("--direction", "maximize"), "acceptance.direction"),
    (("--require-trial-check", "checks.other"), "acceptance.required_trial_checks"),
])
@pytest.mark.parametrize("command", [("plan",), ("run",), ("run", "--dry-run")])
def test_conflicting_acceptance_flag_exits_before_inspection(
    tmp_path, caller, monkeypatch, capsys, flags, field, command,
):
    task_file = _task(tmp_path)
    _forbid(monkeypatch, "cli.inspect_environment", "legacy.run_experiment")
    err = _exit(capsys, *command, "--task", str(task_file), *flags)
    assert f"{command[0]}: error: task file {task_file} is not ready" in err
    assert f"error {field} (cli): {flags[0]} conflicts with the task file" in err


def _tree(root: Path) -> dict[str, bytes | None]:
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
            for path in sorted(root.rglob("*"))}


@pytest.mark.parametrize("command", [("plan",), ("run",), ("run", "--dry-run")])
def test_incomplete_or_invalid_task_reports_fields_and_starts_or_writes_nothing(
    tmp_path, caller, monkeypatch, capsys, command,
):
    partial = _task(tmp_path, PARTIAL)
    invalid = _task(tmp_path, replace=(("repetitions: 5", "repetitions: 0"),
                                       ("  rounds: 4\n", "  rounds: 4\n  budget: 1\n")))
    before = _tree(tmp_path)
    _forbid(monkeypatch, "subprocess.Popen", "subprocess.run", "os.system", "os.posix_spawn",
            "os.posix_spawnp", "os.execv", "os.execve", "os.fork", "os.mkdir", "os.makedirs",
            "cli.inspect_environment", "cli.write_report", "legacy.run_experiment")

    err = _exit(capsys, *command, "--task", str(partial))
    assert f"is not ready for {command[0]}" in err
    for field in ("optimization.framework", "environment.baseline_command",
                  "acceptance.baseline_revision", "acceptance.metric_key"):
        assert f"blocker {field}: missing; required for plan/run" in err

    err = _exit(capsys, *command, "--task", str(invalid), "--repetitions", "7")
    assert "error environment.repetitions (yaml): must be a positive integer" in err
    assert "error environment.budget (yaml): is not a v1 task field" in err

    err = _exit(capsys, *command, "--task", str(tmp_path / "missing.yaml"))
    assert "error $ (yaml): cannot read the task file" in err
    assert _tree(tmp_path) == before
    assert list(caller.iterdir()) == []


def _fake_run(monkeypatch, caller: Path) -> list:
    specs = []

    def run_experiment(spec, environment):
        specs.append(spec)
        directory = caller / "runs" / "run-1"
        directory.mkdir(parents=True)
        (directory / "status.json").write_text('{"verdict": "FAIL"}', encoding="utf-8")
        return directory

    monkeypatch.setattr(legacy_run, "run_experiment", run_experiment)
    monkeypatch.setattr(cli, "write_report", lambda directory: None)
    return specs


def test_run_rejects_a_baseline_revision_that_is_not_the_checkout_head(
    tmp_path, caller, inspected, monkeypatch, capsys,
):
    task_file = _task(tmp_path, replace=(('"<baseline_sha>"', '"def5678"'),))
    specs = _fake_run(monkeypatch, caller)
    err = _exit(capsys, "run", "--task", str(task_file))
    assert "acceptance.baseline_revision 'def5678' does not match" in err
    assert len(inspected) == 1 and specs == []
    assert list(caller.iterdir()) == []


def test_run_rejects_a_missing_local_reference_before_inspection(
    tmp_path, caller, monkeypatch, capsys,
):
    task_file = _task(tmp_path, replace=(('"<baseline_sha>"', f'"{HEAD[:7]}"'),),
                      plan_file=False)
    _forbid(monkeypatch, "cli.inspect_environment", "legacy.run_experiment")
    err = _exit(capsys, "run", "--task", str(task_file))
    assert "acceptance.reference must be an existing local plan file" in err
    assert str(task_file.parent / "plan" / "acceptance.md") in err
    assert list(caller.iterdir()) == []


@pytest.mark.parametrize("revision, reference", [
    (HEAD[:7], None), (HEAD, None), (HEAD[:12].upper(), "https://example.com/issues/1"),
])
def test_run_with_an_agreeing_task_reaches_the_experiment_and_records_the_task(
    tmp_path, caller, inspected, monkeypatch, capsys, revision, reference,
):
    replace = [('"<baseline_sha>"', f'"{revision}"')]
    if reference:
        replace.append(("reference: plan/acceptance.md", f"reference: {reference}"))
    task_file = _task(tmp_path, replace=replace, plan_file=reference is None)
    specs = _fake_run(monkeypatch, caller)
    assert cli.main(["run", "--task", str(task_file), "--repetitions", "7"]) == 1
    out = json.loads(capsys.readouterr().out)
    directory = Path(out["run_dir"])
    assert [json.loads(json.dumps(spec.to_dict())) for spec in specs] == [
        _expected_spec(task_file.parent, caller, repetitions=7)
    ]
    recorded = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    assert recorded == task_input.preview(task_file, {"repetitions": 7}, cwd=str(caller))
    assert recorded["task"]["acceptance"]["baseline_revision"] == revision
    args = json.loads((directory / "args.json").read_text(encoding="utf-8"))
    assert args["task_file"] == str(task_file)
    assert args["backend"] == "cuda" and args["repetitions"] == 7
    assert args["baseline_command"] == list(_expected_spec(
        task_file.parent, caller)["baseline_command"])
    assert args["device_ids"] == "0,1"
    assert arguments.SUPPLIED not in args


def test_flag_only_plan_and_run_keep_their_contract(tmp_path, caller, inspected, monkeypatch,
                                                    capsys):
    for argv, missing in ((["plan"], REQUIRED),
                          (["run", "--baseline-command", "b"],
                           "the following arguments are required: --candidate-command")):
        err = _exit(capsys, *argv)
        assert f"{argv[0]}: error: {missing}\n" in err
    assert inspected == []

    repo = tmp_path / "repo"
    repo.mkdir()
    flags = ["--repo", str(repo), "--baseline-command", "python b.py",
             "--candidate-command", "python c.py"]
    result = _plan(capsys, *flags)
    assert set(result) == {"run_spec", "environment", "execution", "validation"}
    assert result["run_spec"]["backend"] == "cpu"
    assert result["run_spec"]["baseline_command"] == ["python", "b.py"]
    assert inspected[-1]["python"] == sys.executable

    _fake_run(monkeypatch, caller)
    assert cli.main(["run", *flags]) == 1
    directory = Path(json.loads(capsys.readouterr().out)["run_dir"])
    assert not (directory / "task.json").exists()
    args = json.loads((directory / "args.json").read_text(encoding="utf-8"))
    assert "task_file" not in args and arguments.SUPPLIED not in args
    assert args["baseline_command"] == "python b.py"


def test_only_supplied_flags_become_overrides():
    for command in ("plan", "run"):
        args = arguments.parser().parse_args([command, "--task", "t.yaml"])
        supplied = vars(args).pop(arguments.SUPPLIED, ())
        assert supplied == ("task_file",)
        assert task_input.supplied_overrides(args, supplied) == {}
        args = arguments.parser().parse_args(
            [command, "--task", "t.yaml", "--backend", "cpu", "--require-trial-check", "a",
             "--require-trial-check", "b", "--dry-run", "--agent", "codex"])
        supplied = vars(args).pop(arguments.SUPPLIED)
        assert task_input.supplied_overrides(args, supplied) == {
            "backend": "cpu", "require_trial_check": ["a", "b"]}


def test_arguments_from_a_preview_feed_make_spec_like_the_equivalent_flags(tmp_path, caller):
    task_file = _task(tmp_path)
    values = task_input.arguments_from(task_input.preview(task_file)["task"])
    assert values["device_ids"] == "0,1"
    assert values["require_trial_check"] == ["checks.warm"]
    assert values["python"] == str(task_file.parent / ".venv" / "bin" / "python")
    args = arguments.parser().parse_args(["plan", "--task", str(task_file)])
    vars(args).update(values)
    flags = arguments.parser().parse_args([
        "plan", "--repo", values["repo"], "--candidate-repo", values["candidate_repo"],
        "--repo-type", "vllm", "--backend", "cuda", "--device-ids", "0,1",
        "--scenario", "llm.decode", "--mode", "code",
        "--baseline-command", "python bench.py --variant baseline --output {result}",
        "--candidate-command", "python bench.py --variant candidate --output {result}",
        "--validation-command", "python quality.py --output {result}",
        "--require-trial-check", "checks.warm", "--repetitions", "5",
        "--min-improvement-pct", "2.5", "--max-minutes", "90", "--workload-id",
        "fixed-prompts-v1", "--model", "<MODEL>", "--model-revision", "<MODEL_REVISION>",
    ])
    assert arguments.make_spec(args) == arguments.make_spec(flags)
