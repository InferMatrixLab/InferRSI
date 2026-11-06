import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from inferrsi import cli, inspection
from inferrsi.task_input import normalize_task

FIXTURE = Path(__file__).parent / "fixtures" / "task-v1.yaml"


@pytest.fixture
def task_file(tmp_path):
    path = tmp_path / "inputs" / "task.yaml"
    path.parent.mkdir()
    path.write_bytes(FIXTURE.read_bytes())
    return path


def test_preview_and_validation_are_read_only(task_file, tmp_path, monkeypatch, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail("read-only task command attempted to probe or execute")

    monkeypatch.setattr(cli, "inspect_environment", unexpected)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.rglob("*"))
    assert cli.main(["task", "validate", str(task_file), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True}
    assert cli.main(["task", "preview", str(task_file), "--json"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["task"] == normalize_task(task_file).task
    assert preview["complete"] and not preview["missing"]
    assert preview["task"]["optimization"]["repository"] == str(task_file.parent / "checkout")
    assert preview["task"]["environment"]["backend"] == "cuda"
    assert preview["task"]["environment"]["repetitions"] == 2
    assert preview["task"]["environment"]["max_minutes"] == 1.5
    assert preview["task"]["acceptance"]["min_improvement_pct"] == 7.5
    assert preview["task"]["acceptance"]["reference"] == str(task_file.parent / "frozen-plan.md")
    assert sorted(tmp_path.rglob("*")) == before


def test_preview_uses_explicit_flags_and_respects_frozen_fields(task_file, tmp_path, monkeypatch,
                                                             capsys):
    monkeypatch.chdir(tmp_path)
    command = ["task", "preview", str(task_file), "--json"]
    assert cli.main([
        *command, "--backend=cpu", "--device-ids=", "--repo", "cli-checkout",
        "--repetitions", "5", "--min-improvement-pct", "7.5",
    ]) == 0
    task = json.loads(capsys.readouterr().out)["task"]
    assert task["environment"]["backend"] == "cpu"
    assert task["environment"]["device_ids"] == []
    assert task["environment"]["repetitions"] == 5
    assert task["optimization"]["repository"] == str(tmp_path / "cli-checkout")
    assert task["acceptance"]["min_improvement_pct"] == 7.5
    with pytest.raises(SystemExit) as exc:
        cli.main([*command, "--min-improvement-pct", "0"])
    assert exc.value.code == 2
    assert "acceptance.min_improvement_pct" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["plan", "run"])
def test_incomplete_task_stops_before_probes(task_file, monkeypatch, capsys, command):
    task_file.write_text("schema_version: 1\noptimization:\n  model: null\n", encoding="utf-8")
    assert cli.main(["task", "preview", str(task_file), "--json"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert not preview["complete"]
    assert {"optimization.model", "environment.backend", "acceptance.reference"} <= set(
        preview["missing"]
    )

    def unexpected(*args, **kwargs):
        pytest.fail("incomplete input reached an operation")

    monkeypatch.setattr(cli, "inspect_environment", unexpected)
    monkeypatch.setattr(cli, "run_experiment", unexpected)
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "--task", str(task_file)])
    assert exc.value.code == 2
    assert "optimization.model" in capsys.readouterr().err
    assert list(task_file.parent.iterdir()) == [task_file]


@pytest.mark.parametrize(("source", "message"), [
    ("schema_version: true\n", "schema_version"),
    ("schema_version: 2\n", "schema_version"),
    ("schema_version: 1\nschema_version: 1\n", "schema_version: duplicate"),
    ("schema_version: 1\nenvironment: null\n", "environment: expected a mapping"),
    ("schema_version: 1\nenvironment: {backend: gpu}\n", "environment.backend"),
    ("schema_version: 1\nenvironment: {backend: cpu, backend: cuda}\n",
     "environment.backend: duplicate"),
    ("schema_version: 1\nenvironment: {maxRounds: 2}\n", "environment.maxRounds"),
    ("schema_version: 1\nenvironment: {repetitions: 2.0}\n", "environment.repetitions"),
    ("schema_version: 1\nenvironment: {max_minutes: 1e999}\n", "environment.max_minutes"),
    ("schema_version: 1\nenvironment: {device_ids: ['0', '0']}\n", "environment.device_ids"),
    ("schema_version: 1\nenvironment: {baseline_command: [null]}\n",
     "environment.baseline_command"),
    ("schema_version: 1\nacceptance: {baseline: HEAD}\n", "acceptance.baseline"),
    ("schema_version: 1\nacceptance: {reference: 'https://user:secret@example.invalid/issues/1'}\n",
     "acceptance.reference"),
    ("schema_version: 1\noptimization: {model: &alias model}\n", "anchors, aliases and tags"),
    ("schema_version: 1\noptimization: {model: !!str model}\n", "anchors, aliases and tags"),
    ('schema_version: 1\noptimization: {objective: "\\uD800"}\n', "optimization.objective"),
    ('schema_version: 1\nacceptance: {reference: "https://@example.invalid/1"}\n',
     "acceptance.reference"),
    ('schema_version: 1\nacceptance: {reference: "https://example.invalid:abc/1"}\n',
     "acceptance.reference"),
    ("schema_version: 1\n# \0\n", "invalid YAML"),
    ("schema_version: 1\n---\nschema_version: 1\n", "invalid YAML"),
])
def test_invalid_yaml_has_a_field_or_location(task_file, source, message):
    task_file.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match=message) as exc:
        normalize_task(task_file, {"backend": "cpu"})
    assert "user:secret" not in str(exc.value)


def test_plan_and_explicit_run_share_task_and_keep_source_pin(task_file, capsys, monkeypatch):
    repo = task_file.parent / "checkout"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    git("init", "-q")
    git("-c", "commit.gpgsign=false", "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-qm", "synthetic")
    head = git("rev-parse", "HEAD")
    task = yaml.safe_load(task_file.read_text(encoding="utf-8"))
    task["acceptance"]["baseline"] = head
    (task_file.parent / "frozen-plan.md").write_text("Synthetic plan fixture", encoding="utf-8")
    script = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text('{\"metrics\":{\"latency_ms\":' + sys.argv[2] + '}}')"
    )
    task["environment"].update(
        baseline_command=[sys.executable, "-c", script, "{result}", "100"],
        candidate_command=[sys.executable, "-c", script, "{result}", "90"],
        quality_command=[sys.executable, "-c", "pass"],
        device_ids=[],
    )
    task_file.write_text(yaml.safe_dump(task), encoding="utf-8")
    options = ["--task", str(task_file), "--backend", "cpu"]
    assert cli.main(["plan", *options]) == 0
    plan = json.loads(capsys.readouterr().out)
    spec = plan["run_spec"]
    assert spec["revision"] == head
    assert spec["backend"] == "cpu"
    assert spec["repetitions"] == 2 and spec["max_minutes"] == 1.5
    assert spec["min_improvement_pct"] == 7.5 and spec["model"] == "test-model"
    output = task_file.parent / "results"
    assert not output.exists()
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", *options])
    assert exc.value.code == 2
    assert "--confirm-acceptance" in capsys.readouterr().err
    assert not output.exists()
    assert cli.main(["run", *options, "--confirm-acceptance"]) == 0
    result = json.loads(capsys.readouterr().out)
    run = Path(result["run_dir"])
    assert run.parent == output
    assert json.loads((run / "run.lock.json").read_text()) == spec
    assert json.loads((run / "environment.json").read_text())["task"] == plan["environment"]["task"]

    task["acceptance"]["baseline"] = "0" * 40
    task_file.write_text(yaml.safe_dump(task), encoding="utf-8")

    def unexpected(*args, **kwargs):
        pytest.fail("revision mismatch reached a runtime probe")

    monkeypatch.setattr(inspection, "_command", unexpected)
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", *options, "--confirm-acceptance"])
    assert exc.value.code == 2
    assert "acceptance.baseline" in capsys.readouterr().err
    assert list(output.iterdir()) == [run]
