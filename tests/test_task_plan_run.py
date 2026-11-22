"""``plan --task`` and ``run --task``: the shared YAML task contract on the plan/run path."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

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


def _task(tmp_path: Path, source: Path = COMPLETE, *, replace=(), plan_file=True,
          gate=None) -> Path:
    """Copy a fixture into tmp_path/task with its repo/ and candidate/ checkouts.

    ``plan_file`` writes the fixture's Markdown plan/acceptance.md. A ``gate`` document is
    written to plan/gate.yaml, and the task's acceptance.reference then names it.
    """
    directory = tmp_path / "task"
    for name in ("repo", "candidate"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    if plan_file:
        (directory / "plan").mkdir(exist_ok=True)
        (directory / "plan" / "acceptance.md").write_text("frozen gates\n", encoding="utf-8")
    if gate is not None:
        (directory / "plan").mkdir(exist_ok=True)
        (directory / "plan" / "gate.yaml").write_text(
            yaml.safe_dump(gate, sort_keys=False), encoding="utf-8")
        replace = (*replace, ("reference: plan/acceptance.md", "reference: plan/gate.yaml"))
    target = directory / source.name
    shutil.copyfile(source, target)
    text = target.read_text(encoding="utf-8")
    for old, new in replace:
        assert old in text, old
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    return target


def _gate(**changes) -> dict:
    """A frozen gate record: the complete fixture's acceptance section, baseline HEAD[:7]."""
    acceptance = yaml.safe_load(COMPLETE.read_text(encoding="utf-8"))["acceptance"]
    acceptance.update(reference="https://example.com/issues/1", baseline_revision=HEAD[:7])
    acceptance.update(changes)
    return {"schema_version": 1, "acceptance": acceptance}


def _agreeing(tmp_path: Path, revision: str = HEAD[:7], *, replace=(), **gate) -> Path:
    """The complete fixture at ``revision``, referencing a frozen gate record that agrees.

    ``replace`` edits only the task and ``gate`` changes only the record.
    """
    return _task(tmp_path, replace=(('"<baseline_sha>"', f'"{revision}"'), *replace),
                 gate=_gate(**{"baseline_revision": revision, **gate}))


@pytest.fixture
def caller(tmp_path, monkeypatch) -> Path:
    directory = tmp_path / "caller"
    directory.mkdir()
    monkeypatch.chdir(directory)
    return directory


def _environment(head: str = HEAD) -> dict:
    return {
        "repository": {"available": True, "head": head, "snapshot_hash": "f" * 64},
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
        revision="<baseline_sha>",
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
    # The fixture's Markdown plan states no machine-readable gate: plan says so, still 0.
    gate = result["frozen_gate"]
    assert gate["status"] == "unverified" and gate["sha256"] is None
    assert gate["reference"] == str(directory / "plan" / "acceptance.md")
    assert [item["field"] for item in gate["problems"]] == ["acceptance.reference"]


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
    task_file = _agreeing(tmp_path, "def5678")
    specs = _fake_run(monkeypatch, caller)
    err = _exit(capsys, "run", "--task", str(task_file))
    assert "acceptance.baseline_revision 'def5678' does not match" in err
    assert len(inspected) == 1 and specs == []
    assert list(caller.iterdir()) == []


_FORBIDDEN = ("subprocess.Popen", "subprocess.run", "os.system", "os.posix_spawn",
              "os.posix_spawnp", "os.execv", "os.execve", "os.fork", "os.mkdir", "os.makedirs",
              "cli.inspect_environment", "cli.write_report", "legacy.run_experiment")


@pytest.mark.parametrize("old, new, gate, field, shown", [
    # The review case: reference and HEAD agree; only the agreed threshold changed.
    ("min_improvement_pct: 2.5", "min_improvement_pct: 1.0", {},
     "acceptance.min_improvement_pct", "is 1.0 in the task but 2.5"),
    ("metric_key: metrics.latency_ms", "metric_key: metrics.ttft_ms", {},
     "acceptance.metric_key", '"metrics.ttft_ms" in the task but "metrics.latency_ms"'),
    ("direction: minimize", "direction: maximize", {},
     "acceptance.direction", '"maximize" in the task but "minimize"'),
    ("metric_unit: ms", "metric_unit: s", {}, "acceptance.metric_unit", '"s" in the task'),
    ("comparison_scope: external_command", "comparison_scope: in_process", {},
     "acceptance.comparison_scope", '"in_process" in the task but "external_command"'),
    ("required_trial_checks: [checks.warm]", "required_trial_checks: []", {},
     "acceptance.required_trial_checks", 'is [] in the task but ["checks.warm"]'),
    ('  constraints: "Quality must not regress against the baseline"\n', "", {},
     "acceptance.constraints", "is null in the task but"),
    # HEAD matches the task's revision, but the frozen record pins another baseline.
    (None, None, {"baseline_revision": "def5678"},
     "acceptance.baseline_revision", f'is "{HEAD[:7]}" in the task but "def5678"'),
])
def test_run_rejects_a_task_whose_gate_differs_from_its_frozen_record(
    tmp_path, caller, monkeypatch, capsys, old, new, gate, field, shown,
):
    task_file = _agreeing(tmp_path, replace=((old, new),) if old else (), **gate)
    record = task_file.parent / "plan" / "gate.yaml"
    before = _tree(tmp_path)
    _forbid(monkeypatch, *_FORBIDDEN)
    err = _exit(capsys, "run", "--task", str(task_file))
    assert "frozen gate mismatch: run --task needs" in err
    assert f"\n{field}: " in err and shown in err
    assert f"in the frozen gate record {record}" in err
    assert err.count(" in the frozen gate record ") == 1
    assert _tree(tmp_path) == before
    assert list(caller.iterdir()) == []


@pytest.mark.parametrize("case, message", [
    ("missing", "is not an existing local frozen gate record file: "),
    ("url", "is an HTTP(S) URL, which InferRSI does not fetch, so the frozen gate cannot"),
    ("markdown", "frozen gate record {plan}: $ the task file must be a mapping, not string"),
    ("itself", "names the task file itself, not a separate frozen gate record"),
    ("unstated", "frozen gate record {gate} does not state acceptance.min_improvement_pct"),
    ("unknown", "frozen gate record {gate}: acceptance.threshold is not a v1 task field"),
    ("no-section", "frozen gate record {gate} has no acceptance section"),
])
def test_run_rejects_a_frozen_gate_it_cannot_verify_before_inspection(
    tmp_path, caller, monkeypatch, capsys, case, message,
):
    revision = ('"<baseline_sha>"', f'"{HEAD[:7]}"')
    reference = "reference: plan/acceptance.md"
    task_file = {
        "missing": lambda: _task(tmp_path, replace=(revision,), plan_file=False),
        "url": lambda: _task(tmp_path, replace=(
            revision, (reference, "reference: https://example.com/issues/1"))),
        "markdown": lambda: _task(tmp_path, replace=(revision,)),
        "itself": lambda: _task(tmp_path, replace=(
            revision, (reference, "reference: complete.yaml"))),
        "unstated": lambda: _agreeing(tmp_path, min_improvement_pct=None),
        "unknown": lambda: _agreeing(tmp_path, threshold=2.5),
        "no-section": lambda: _task(tmp_path, replace=(revision,),
                                    gate={"schema_version": 1}),
    }[case]()
    plan = task_file.parent / "plan"
    before = _tree(tmp_path)
    _forbid(monkeypatch, *_FORBIDDEN)
    err = _exit(capsys, "run", "--task", str(task_file))
    assert "frozen gate unverified: run --task needs" in err
    assert "\nacceptance.reference: " in err
    assert message.format(plan=plan / "acceptance.md", gate=plan / "gate.yaml") in err
    assert _tree(tmp_path) == before
    assert list(caller.iterdir()) == []


@pytest.mark.parametrize("command", [("plan",), ("run", "--dry-run")])
def test_plan_and_dry_run_report_a_mismatched_frozen_gate_without_running(
    tmp_path, caller, inspected, monkeypatch, capsys, command,
):
    task_file = _agreeing(tmp_path, replace=(("min_improvement_pct: 2.5",
                                               "min_improvement_pct: 1.0"),))
    _forbid(monkeypatch, "legacy.run_experiment", "cli.write_report")
    assert cli.main([*command, "--task", str(task_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["execution"] == "not started"
    assert result["run_spec"]["min_improvement_pct"] == 1.0
    gate = result["frozen_gate"]
    assert gate["status"] == "mismatch"
    assert [item["field"] for item in gate["problems"]] == ["acceptance.min_improvement_pct"]
    assert gate == task_input.frozen_gate(result["task"]["task"], task_file)
    assert list(caller.iterdir()) == []


@pytest.mark.parametrize("revision", [HEAD[:7], HEAD, HEAD[:12].upper()])
def test_run_with_an_agreeing_task_reaches_the_experiment_and_records_the_task(
    tmp_path, caller, inspected, monkeypatch, capsys, revision,
):
    task_file = _agreeing(tmp_path, revision)
    record = task_file.parent / "plan" / "gate.yaml"
    specs = _fake_run(monkeypatch, caller)
    assert cli.main(["run", "--task", str(task_file), "--repetitions", "7"]) == 1
    out = json.loads(capsys.readouterr().out)
    directory = Path(out["run_dir"])
    assert [json.loads(json.dumps(spec.to_dict())) for spec in specs] == [
        _expected_spec(task_file.parent, caller, repetitions=7, revision=revision,
                       snapshot_id="f" * 64)
    ]
    recorded = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    assert recorded == task_input.preview(task_file, {"repetitions": 7}, cwd=str(caller))
    assert recorded["task"]["acceptance"]["baseline_revision"] == revision
    gate = json.loads((directory / "frozen_gate.json").read_text(encoding="utf-8"))
    assert gate == {"reference": str(record), "status": "agrees", "problems": [],
                    "sha256": hashlib.sha256(record.read_bytes()).hexdigest()}
    # An Agent gets the same result from the shared contract.
    assert gate == task_input.frozen_gate(recorded["task"], recorded["task_file"])
    args = json.loads((directory / "args.json").read_text(encoding="utf-8"))
    assert args["task_file"] == str(task_file)
    assert args["backend"] == "cuda" and args["repetitions"] == 7
    assert args["baseline_command"] == list(_expected_spec(
        task_file.parent, caller)["baseline_command"])
    assert args["device_ids"] == "0,1"
    assert arguments.SUPPLIED not in args


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Synthetic Contributor",
         "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def test_real_git_run_keeps_the_frozen_threshold_when_reference_and_head_match(
    tmp_path, caller, capsys,
):
    """The review reproduction, unstubbed: a real Git checkout and real CPU commands.

    Baseline 100 ms and candidate 80 ms are a 20% gain. The frozen record and the task
    both state 21%, so the run is a FAIL. Keeping that reference and HEAD but lowering only
    the task's threshold to 0 exits 2 before any benchmark command or run directory. So
    does a baseline revision that is not HEAD, even when the record states it too.
    """
    directory = tmp_path / "task"
    repo = directory / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    _git(repo, "commit", "--allow-empty", "--quiet", "-m", "fixture")
    head = _git(repo, "rev-parse", "HEAD")
    launches = tmp_path / "launches"
    script = ("import json, sys; open(sys.argv[3], 'a').write('.'); open(sys.argv[1], 'w')"
              ".write(json.dumps({'metrics': {'latency_ms': float(sys.argv[2])}}))")
    gate = {"baseline_revision": head, "metric_key": "metrics.latency_ms",
            "direction": "minimize", "metric_unit": "ms", "min_improvement_pct": 21}
    (directory / "plan").mkdir()
    record = directory / "plan" / "gate.yaml"
    task_file = directory / "task.yaml"

    def write(frozen=(), **task):
        record.write_text(yaml.safe_dump({"schema_version": 1, "acceptance": {
            "reference": "https://example.com/issues/1", **gate, **dict(frozen)}}),
            encoding="utf-8")
        task_file.write_text(yaml.safe_dump({
            "schema_version": 1,
            "optimization": {"repository": "repo", "model": "synthetic", "framework": "vllm",
                             "workload": "synthetic-v1", "objective": "Keep the frozen gate",
                             "plane": "harness"},
            "environment": {
                "backend": "cpu", "repetitions": 1, "max_minutes": 5,
                "baseline_command": [sys.executable, "-c", script, "{result}", "100",
                                     str(launches)],
                "candidate_command": [sys.executable, "-c", script, "{result}", "80",
                                      str(launches)],
                "quality_command": [sys.executable, "-c", "pass"],
            },
            "acceptance": {"reference": "plan/gate.yaml", **gate, **task},
        }), encoding="utf-8")

    write(min_improvement_pct=0)
    err = _exit(capsys, "run", "--task", str(task_file))
    assert "frozen gate mismatch: run --task needs" in err
    assert (f"\nacceptance.min_improvement_pct: is 0.0 in the task but 21.0 in the frozen "
            f"gate record {record}") in err
    other = "0" * 40
    write({"baseline_revision": other}, baseline_revision=other)
    err = _exit(capsys, "run", "--task", str(task_file))
    assert f"acceptance.baseline_revision {other!r} does not match the baseline" in err
    assert f"checkout HEAD {head};" in err
    assert not launches.exists() and list(caller.iterdir()) == []

    write()
    assert cli.main(["run", "--task", str(task_file)]) == 1
    run = Path(json.loads(capsys.readouterr().out)["run_dir"])
    assert launches.exists()
    evaluation = json.loads((run / "evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["verdict"] == "FAIL" and evaluation["min_improvement_pct"] == 21.0
    assert evaluation["improvement_pct"] == pytest.approx(20.0)
    frozen = json.loads((run / "frozen_gate.json").read_text(encoding="utf-8"))
    assert frozen["status"] == "agrees" and frozen["reference"] == str(record)


@pytest.mark.parametrize("command", [("plan",), ("run",), ("run", "--dry-run")])
def test_missing_candidate_directory_refuses_before_any_probe(
    tmp_path, caller, monkeypatch, capsys, command,
):
    task_file = _agreeing(tmp_path, replace=(
        ("candidate_repository: candidate", "candidate_repository: missing-candidate"),
    ))
    before = _tree(tmp_path)
    _forbid(monkeypatch, *_FORBIDDEN)
    error = _exit(capsys, *command, "--task", str(task_file))
    assert "candidate_repo must be an existing directory" in error
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("switch_at", ["after_inspection", "before_trial"])
@pytest.mark.parametrize("short_revision", [False, True])
@pytest.mark.parametrize("source_change", ["checkout", "working-tree"])
def test_task_revision_is_bound_to_real_execution_snapshots(
    tmp_path, caller, monkeypatch, capsys, switch_at, short_revision, source_change,
):
    """Only the race is scheduled; Git, inspection, snapshots and runner are real."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    _git(repo, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (repo / "metric.txt").write_text("100\n", encoding="utf-8")
    _git(repo, "add", "metric.txt")
    _git(repo, "commit", "--quiet", "-m", "accepted baseline")
    accepted = _git(repo, "rev-parse", "HEAD")
    (repo / "metric.txt").write_text("200\n", encoding="utf-8")
    _git(repo, "commit", "--quiet", "-am", "different baseline")
    changed = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "--quiet", accepted)
    revision = accepted[:8].upper() if short_revision else accepted
    launches = tmp_path / "launches"
    script = (
        "import json,sys; from pathlib import Path; "
        "Path(sys.argv[2]).open('a').write('.'); "
        "value=float(Path('metric.txt').read_text()) if sys.argv[3]=='baseline' else 80; "
        "Path(sys.argv[1]).write_text(json.dumps({'metrics':{'latency_ms':value}}))"
    )
    record = tmp_path / "gate.yaml"
    gate = {"baseline_revision": revision, "metric_key": "metrics.latency_ms",
            "direction": "minimize", "metric_unit": "ms", "min_improvement_pct": 30}
    record.write_text(yaml.safe_dump({"schema_version": 1, "acceptance": gate}),
                      encoding="utf-8")
    task_file = tmp_path / "task.yaml"
    task_file.write_text(yaml.safe_dump({
        "schema_version": 1,
        "optimization": {"repository": "repo", "model": "synthetic", "framework": "vllm",
                         "workload": "snapshot-race", "objective": "Bind the accepted source",
                         "plane": "harness"},
        "environment": {"backend": "cpu", "python": sys.executable,
                        "baseline_command": [sys.executable, "-c", script, "{result}",
                                             str(launches), "baseline"],
                        "candidate_command": [sys.executable, "-c", script, "{result}",
                                              str(launches), "candidate"],
                        "quality_command": [sys.executable, "-c", "pass"],
                        "repetitions": 1, "max_minutes": 1},
        "acceptance": {"reference": "gate.yaml", **gate},
    }), encoding="utf-8")

    def change_source():
        if source_change == "checkout":
            _git(repo, "checkout", "--quiet", changed)
        else:
            (repo / "metric.txt").write_text("200\n", encoding="utf-8")

    if switch_at == "after_inspection":
        inspect = cli.inspect_environment

        def inspection(*args, **kwargs):
            environment = inspect(*args, **kwargs)
            assert environment["repository"]["head"] == accepted
            change_source()
            return environment

        monkeypatch.setattr(cli, "inspect_environment", inspection)
    else:
        snapshot = legacy_run.repository_identity
        calls = []

        def capture(path, exclude=None):
            identity = snapshot(path, exclude)
            calls.append(identity)
            if len(calls) == 2:  # Both initial identities were captured, before the first trial.
                change_source()
            return identity

        monkeypatch.setattr(legacy_run, "repository_identity", capture)

    assert cli.main(["run", "--task", str(task_file)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert not launches.exists()
    assert output["status"]["state"] == "failed"
    assert output["status"]["verdict"] == "INCONCLUSIVE"
    pin = "revision" if source_change == "checkout" else "snapshot_id"
    assert f"RunSpec.{pin}" in output["status"]["error"]
    directory = Path(output["run_dir"])
    locked = json.loads((directory / "run.lock.json").read_text(encoding="utf-8"))
    assert locked["revision"] == revision
    inspected = json.loads((directory / "environment.json").read_text(encoding="utf-8"))
    assert locked["snapshot_id"] == inspected["repository"]["snapshot_hash"]
    assert not list(directory.glob("*/trial-*/execution.json"))


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
    assert not (directory / "frozen_gate.json").exists()
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
    spec = arguments.make_spec(args)
    assert spec.revision == "<baseline_sha>"
    assert replace(spec, revision="") == arguments.make_spec(flags)
