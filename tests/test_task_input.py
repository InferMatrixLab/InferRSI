"""Shared YAML task contract v1: validation, normalization, overrides and read-only preview."""

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

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: pytest supplies tomli.
    import tomli as tomllib

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "task-input"
COMPLETE = FIXTURES / "complete.yaml"
PARTIAL = FIXTURES / "partial.yaml"
CASES = json.loads((FIXTURES / "invalid-cases.json").read_text(encoding="utf-8"))
RESOURCES = REPO / "src" / "inferrsi" / "apps" / "cli" / "task-input" / "v1"


def _copy(tmp_path: Path, source: Path = COMPLETE) -> Path:
    directory = tmp_path / "task"
    directory.mkdir(exist_ok=True)
    target = directory / source.name
    shutil.copyfile(source, target)
    return target


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "case.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _main(capsys, *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def _expected_complete(directory: Path) -> dict:
    base = str(directory)
    return {
        "optimization": {
            "repository": os.path.join(base, "repo"),
            "candidate_repository": os.path.join(base, "candidate"),
            "model": "<MODEL>",
            "model_revision": "<MODEL_REVISION>",
            "framework": "vllm",
            "workload": "fixed-prompts-v1",
            "scenario": "llm.decode",
            "mode": "code",
            "objective": "Reduce decode latency for the fixed workload",
            "plane": "harness",
        },
        "environment": {
            "backend": "cuda",
            "device_ids": ["0", "1"],
            "device_model": "<DEVICE_MODEL>",
            "python": os.path.join(base, ".venv", "bin", "python"),
            "baseline_command": ["python", "bench.py", "--variant", "baseline",
                                 "--output", "{result}"],
            "candidate_command": ["python", "bench.py", "--variant", "candidate",
                                  "--output", "{result}"],
            "quality_command": ["python", "quality.py", "--output", "{result}"],
            "repetitions": 5,
            "max_minutes": 90.0,
            "rounds": 4,
        },
        "acceptance": {
            "reference": os.path.join(base, "plan", "acceptance.md"),
            "baseline_revision": "<baseline_sha>",
            "metric_key": "metrics.latency_ms",
            "direction": "minimize",
            "metric_unit": "ms",
            "min_improvement_pct": 2.5,
            "comparison_scope": "external_command",
            "required_trial_checks": ["checks.warm"],
            "constraints": "Quality must not regress against the baseline",
        },
    }


def test_complete_fixture_is_valid_complete_and_resolves_paths_against_the_file(
    tmp_path, monkeypatch,
):
    task_file = _copy(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = task_input.preview(Path("..") / "task" / "complete.yaml")
    assert result["task_file"] == str(task_file)
    assert result["valid"] and result["complete"]
    assert result["errors"] == [] and result["blockers"] == []
    assert result["task"] == _expected_complete(task_file.parent)
    assert set(result["sources"].values()) == {"yaml"}
    assert result["execution"] == "not started"
    assert task_input.check(task_file) == {
        "schema_version": 1, "task_file": str(task_file), "valid": True, "errors": [],
    }


def test_partial_draft_is_valid_and_lists_exactly_the_plan_run_blockers():
    result = task_input.preview(PARTIAL)
    assert result["valid"] and not result["complete"]
    assert result["task"]["optimization"]["repository"] == str(FIXTURES)
    assert result["task"]["environment"]["backend"] == "cuda"
    assert result["task"]["acceptance"]["reference"] == str(FIXTURES / "<ACCEPTANCE_PLAN>")
    assert [item["field"] for item in result["blockers"]] == [
        "optimization.framework",
        "optimization.workload",
        "environment.baseline_command",
        "environment.candidate_command",
        "environment.repetitions",
        "environment.max_minutes",
        "acceptance.baseline_revision",
        "acceptance.metric_key",
        "acceptance.direction",
        "acceptance.metric_unit",
        "acceptance.min_improvement_pct",
    ]
    assert all(item["message"] == "missing; required for plan/run"
               for item in result["blockers"])
    assert result["sources"]["optimization.scenario"] == "default"
    assert result["sources"]["optimization.workload"] == "missing"


def test_packaged_template_is_valid_all_null_and_matches_the_schema(tmp_path):
    import yaml

    template = yaml.safe_load(task_input.template_text())
    schema = json.loads(task_input.schema_text())
    assert template["schema_version"] == 1
    assert set(template) == set(schema["properties"]) == {"schema_version", *task_input.SECTIONS}
    for section in task_input.SECTIONS:
        assert list(template[section]) == list(schema["properties"][section]["properties"])
        assert all(value is None for value in template[section].values())
    assert {f"{section}.{name}" for section in task_input.SECTIONS
            for name in schema["properties"][section]["properties"]} == set(task_input.BY_PATH)
    path = _write(tmp_path, task_input.template_text())
    result = task_input.preview(path)
    assert result["valid"] and not result["complete"]
    text = task_input.template_text()
    for field in task_input.FIELDS:
        line = next(line for line in text.splitlines() if line.strip().startswith(field.name + ":"))
        assert all(choice in line for choice in field.choices), field.path
    assert task_input.schema_text() == (RESOURCES / "schema.json").read_text(encoding="utf-8")
    assert task_input.template_text() == (RESOURCES / "template.yaml").read_text(
        encoding="utf-8")


def test_schema_patterns_match_the_python_contract():
    schema = json.loads(task_input.schema_text())
    acceptance = schema["properties"]["acceptance"]["properties"]
    key = acceptance["metric_key"]["anyOf"][1]
    assert key["pattern"] == task_input.DOTTED_KEY
    assert acceptance["required_trial_checks"]["anyOf"][1]["items"]["pattern"] == (
        task_input.DOTTED_KEY)
    ids = schema["properties"]["environment"]["properties"]["device_ids"]["anyOf"][1]
    assert ids["items"]["pattern"] == task_input.DEVICE_ID
    for field in task_input.FIELDS:
        spec = schema["properties"][field.section]["properties"][field.name]["anyOf"][1]
        if field.choices:
            assert spec["enum"] == list(field.choices), field.path


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_invalid_cases_are_rejected_at_their_field_paths(case, tmp_path):
    path = _write(tmp_path, case["yaml"])
    result = task_input.check(path)
    assert not result["valid"]
    assert sorted({error["field"] for error in result["errors"]}) == sorted(case["fields"])
    assert all(error["source"] == "yaml" for error in result["errors"])
    preview = task_input.preview(path)
    assert not preview["valid"] and not preview["complete"]


def test_json_schema_agrees_with_the_python_validator():
    jsonschema = pytest.importorskip("jsonschema")
    import yaml

    validator = jsonschema.Draft202012Validator(json.loads(task_input.schema_text()))
    validator.check_schema(validator.schema)
    for path in (COMPLETE, PARTIAL):
        assert validator.is_valid(yaml.safe_load(path.read_text(encoding="utf-8"))), path
    assert validator.is_valid(yaml.safe_load(task_input.template_text()))
    detected = [case for case in CASES if case.get("schema_detects", True)]
    assert len(detected) >= 30
    for case in detected:
        assert not validator.is_valid(yaml.safe_load(case["yaml"])), case["name"]
    # The documented gaps: JSON Schema alone accepts these, or they never load as YAML.
    for case in CASES:
        if case.get("schema_detects", True):
            continue
        try:
            data = yaml.safe_load(case["yaml"])
        except Exception:
            continue
        assert validator.is_valid(data), case["name"]


def test_omitted_flags_preserve_yaml_and_explicit_overrides_win(tmp_path, monkeypatch, capsys):
    task_file = _copy(tmp_path)
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    code, out = _main(capsys, "task", "preview", str(task_file), "--json")
    assert code == 0
    plain = json.loads(out)
    assert plain["task"]["environment"]["backend"] == "cuda"
    assert plain["task"]["environment"]["repetitions"] == 5
    assert plain["task"]["acceptance"]["min_improvement_pct"] == 2.5
    assert plain["task"]["environment"]["max_minutes"] == 90.0
    code, out = _main(capsys, "task", "preview", str(task_file), "--json",
                      "--repetitions", "7", "--repo", "other-checkout",
                      "--device-ids", "2, 3", "--baseline-command", "python b.py")
    assert code == 0
    result = json.loads(out)
    assert result["valid"] and result["complete"]
    assert result["task"]["environment"]["repetitions"] == 7
    assert result["task"]["optimization"]["repository"] == str(caller / "other-checkout")
    assert result["task"]["environment"]["device_ids"] == ["2", "3"]
    assert result["task"]["environment"]["baseline_command"] == ["python", "b.py"]
    for path in ("environment.repetitions", "optimization.repository",
                 "environment.device_ids", "environment.baseline_command"):
        assert result["sources"][path] == "cli"
    assert result["task"]["environment"]["backend"] == "cuda"
    assert result["sources"]["environment.backend"] == "yaml"
    expected = _expected_complete(task_file.parent)
    for section, values in expected.items():
        for name, value in values.items():
            if result["sources"][f"{section}.{name}"] == "yaml":
                assert result["task"][section][name] == value


def test_override_fills_a_missing_optional_field_and_is_itself_validated(tmp_path):
    path = _copy(tmp_path, PARTIAL)
    result = task_input.preview(path, {"backend": "ascend", "repetitions": 4,
                                       "python": "python3"})
    assert result["task"]["environment"]["backend"] == "ascend"
    assert result["task"]["environment"]["repetitions"] == 4
    assert result["task"]["environment"]["python"] == "python3"
    assert "environment.repetitions" not in {item["field"] for item in result["blockers"]}
    bad = task_input.preview(path, {"repetitions": 0, "max_minutes": 20000.0})
    assert not bad["valid"]
    assert {(error["field"], error["source"]) for error in bad["errors"]} == {
        ("environment.repetitions", "cli"), ("environment.max_minutes", "cli"),
    }


def test_invalid_yaml_field_stays_an_error_when_overridden(tmp_path, capsys):
    path = _write(tmp_path, COMPLETE.read_text(encoding="utf-8").replace(
        "repetitions: 5", "repetitions: 0"))
    code, out = _main(capsys, "task", "preview", str(path), "--json", "--repetitions", "7")
    result = json.loads(out)
    assert code == 1 and not result["valid"] and not result["complete"]
    assert result["errors"] == [{
        "field": "environment.repetitions", "message": "must be a positive integer",
        "source": "yaml",
    }]
    assert result["task"]["environment"]["repetitions"] == 7
    assert result["sources"]["environment.repetitions"] == "cli"


@pytest.mark.parametrize("flags, field", [
    (("--min-improvement-pct", "5"), "acceptance.min_improvement_pct"),
    (("--metric-key", "metrics.throughput"), "acceptance.metric_key"),
    (("--direction", "maximize"), "acceptance.direction"),
    (("--require-trial-check", "checks.other"), "acceptance.required_trial_checks"),
])
def test_conflicting_acceptance_flag_is_rejected(tmp_path, capsys, flags, field):
    task_file = _copy(tmp_path)
    code, out = _main(capsys, "task", "preview", str(task_file), "--json", *flags)
    result = json.loads(out)
    assert code == 1 and not result["valid"] and not result["complete"]
    assert [(error["field"], error["source"]) for error in result["errors"]] == [(field, "cli")]
    assert "conflicts with the task file" in result["errors"][0]["message"]
    assert result["task"] == _expected_complete(task_file.parent)


def test_equal_acceptance_flags_are_accepted_and_keep_the_yaml_source(tmp_path, capsys):
    task_file = _copy(tmp_path)
    code, out = _main(
        capsys, "task", "preview", str(task_file), "--json",
        "--min-improvement-pct", "2.5", "--metric-key", "metrics.latency_ms",
        "--direction", "minimize", "--metric-unit", "ms",
        "--comparison-scope", "external_command", "--require-trial-check", "checks.warm",
    )
    result = json.loads(out)
    assert code == 0 and result["valid"] and result["complete"]
    assert all(result["sources"][field.path] == "yaml"
               for field in task_input.FIELDS if field.acceptance)


def test_fields_in_a_non_mapping_section_are_invalid_not_missing(tmp_path):
    path = _write(tmp_path, "schema_version: 1\nenvironment: [cuda]\n")
    result = task_input.preview(path)
    assert {result["sources"][field.path] for field in task_input.FIELDS
            if field.section == "environment"} == {"invalid"}
    blocked = {item["field"]: item["message"] for item in result["blockers"]}
    assert blocked["environment.backend"].startswith("invalid")
    assert blocked["optimization.model"].startswith("missing")


def test_hostile_values_print_as_field_errors(tmp_path, capsys):
    for text in ('schema_version: 1\noptimization:\n  "\\ud800": 1\n  model: "\\udfff"\n',
                 "schema_version: 1\noptimization:\n  workload: 2024-1-1 25:00:00\n"):
        path = _write(tmp_path, text)
        for argv in (("validate", str(path)), ("preview", str(path), "--json")):
            code, out = _main(capsys, "task", *argv)
            assert code == 1
            out.encode("utf-8")


def test_none_override_counts_as_not_supplied():
    result = task_input.preview(COMPLETE, {"backend": None, "metric_key": None})
    assert result["valid"] and result["complete"]
    assert result["sources"]["environment.backend"] == "yaml"


def test_acceptance_flag_cannot_supply_a_value_missing_from_the_file():
    result = task_input.preview(PARTIAL, {"metric_key": "metrics.latency_ms"})
    assert [error["field"] for error in result["errors"]] == ["acceptance.metric_key"]
    assert result["task"]["acceptance"]["metric_key"] is None


def test_task_defaults_equal_the_plan_and_run_parser_defaults():
    for command in ("plan", "run"):
        args = arguments.parser().parse_args(
            [command, "--baseline-command", "b", "--candidate-command", "c"])
        for field in task_input.FIELDS:
            if field.default is None:
                continue
            value = getattr(args, field.dest)
            if field.kind == "ids":
                value = list(arguments.device_ids(args))
            assert task_input._normalize(field, field.default, "") == (
                list(value) if isinstance(value, (list, tuple)) else value), field.path
        for field in task_input.FIELDS:
            if field.flag is not None:
                value = field.choices[0] if field.choices else "1"
                _, unknown = arguments.parser().parse_known_args(
                    [command, "--baseline-command", "b", "--candidate-command", "c",
                     field.flag, value])
                assert unknown == [], field.flag


def test_preview_flags_have_no_defaults():
    args = arguments.parser().parse_args(["task", "preview", "x.yaml"])
    assert task_input.overrides_from(args) == {}
    assert args.json is False


def test_cli_preview_equals_the_python_preview_for_the_same_file(tmp_path):
    task_file = _copy(tmp_path)
    for argv, overrides in (([], None), (["--backend", "rocm", "--repetitions", "9"],
                                         {"backend": "rocm", "repetitions": 9})):
        completed = subprocess.run(
            [sys.executable, "-m", "inferrsi", "task", "preview", str(task_file), "--json",
             *argv],
            capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, check=False,
            env=dict(os.environ, PYTHONPATH=str(REPO / "src")),
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout) == task_input.preview(
            task_file, overrides, cwd=str(tmp_path))


def _tree(root: Path) -> dict[str, bytes | None]:
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
            for path in sorted(root.rglob("*"))}


def test_validate_and_preview_start_nothing_and_write_nothing(tmp_path, monkeypatch, capsys):
    task_file = _copy(tmp_path)
    invalid = _write(tmp_path, CASES[0]["yaml"])
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)

    def forbidden(*args, **kwargs):
        raise AssertionError("task validation must not start or inspect anything")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    for name in ("system", "posix_spawn", "posix_spawnp", "execv", "execve", "fork",
                 "mkdir", "makedirs"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, forbidden)
    monkeypatch.setattr(cli, "inspect_environment", forbidden)
    before = _tree(tmp_path)
    runs = [
        ("task", "validate", str(task_file)), ("task", "validate", str(task_file), "--json"),
        ("task", "preview", str(task_file)), ("task", "preview", str(task_file), "--json",
                                               "--repetitions", "7"),
        ("task", "validate", str(invalid)), ("task", "preview", str(invalid), "--json"),
        ("task", "preview", str(tmp_path / "missing.yaml"), "--json"),
        ("task", "preview", str(task_file), "--metric-key", "metrics.other"),
        ("task", "schema",), ("task", "template",),
    ]
    codes = [_main(capsys, *argv)[0] for argv in runs]
    assert codes == [0, 0, 0, 0, 1, 1, 1, 1, 0, 0]
    assert _tree(tmp_path) == before
    assert list(caller.iterdir()) == []


def test_text_output_lists_errors_values_and_blockers(capsys):
    code, out = _main(capsys, "task", "preview", str(PARTIAL))
    assert code == 0
    assert "valid: yes" in out and "complete: no" in out
    assert '  environment.backend = "cuda" [yaml]' in out
    assert "blocker acceptance.metric_key: missing; required for plan/run" in out
    assert out.rstrip().endswith("execution: not started")


def test_document_errors(tmp_path, capsys):
    big = _write(tmp_path, "schema_version: 1\n" + "#" * task_input.MAX_BYTES)
    assert task_input.check(big)["errors"][0]["message"] == "the task file exceeds 64 KiB"
    (tmp_path / "latin.yaml").write_bytes(b"schema_version: 1\nx: \xff\n")
    assert "UTF-8" in task_input.check(tmp_path / "latin.yaml")["errors"][0]["message"]
    broken = task_input.check(_write(tmp_path, "schema_version: [1\n"))
    assert broken["errors"][0]["field"] == "$"
    assert broken["errors"][0]["message"].startswith("invalid YAML at line")
    missing = task_input.check(tmp_path / "absent.yaml")
    assert missing["errors"][0]["message"].startswith("cannot read the task file")
    code, out = _main(capsys, "task", "validate", str(tmp_path / "absent.yaml"))
    assert code == 1 and "error $ (yaml): cannot read the task file" in out


def test_aliases_are_walked_once(tmp_path):
    lines = ["schema_version: 1", "a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    lines += [f"a{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 10) + "]" for i in range(1, 9)]
    result = task_input.check(_write(tmp_path, "\n".join(lines) + "\n"))
    assert {error["field"] for error in result["errors"]} == {f"a{i}" for i in range(9)}


def test_http_references_are_kept_verbatim_and_local_ones_resolve(tmp_path):
    for url in ("https://github.com/<OWNER>/<REPO>/issues/<NUMBER>",
                "https://example.com:8443/issues/1", "http://[::1]:8080/plan",
                "HTTPS://Example.com:/issues/1", "https://user@example.com/issues/1"):
        path = _write(tmp_path, f"schema_version: 1\nacceptance:\n  reference: '{url}'\n")
        result = task_input.preview(path)
        assert result["valid"] and result["errors"] == [], url
        assert result["task"]["acceptance"]["reference"] == url
        assert result["sources"]["acceptance.reference"] == "yaml"
    path = _write(tmp_path, "schema_version: 1\nacceptance:\n  reference: ../plan.md\n")
    assert task_input.preview(path)["task"]["acceptance"]["reference"] == str(
        tmp_path.parent / "plan.md")


@pytest.mark.parametrize("url, message", [
    ("https://:443", "must name a host in an HTTP(S) URL"),
    ("https://user:pw@:443/issues/1", "must name a host in an HTTP(S) URL"),
    ("https://example.com:notaport", "must use a port from 1 to 65535 in an HTTP(S) URL"),
    ("https://example.com:+443/issues/1",
     "must use a port from 1 to 65535 in an HTTP(S) URL"),
    ("https://example.com:65536", "must use a port from 1 to 65535 in an HTTP(S) URL"),
    ("https://exa mple.com/issues/1",
     "must not contain whitespace or control characters in an HTTP(S) URL"),
    ("ftp://example.invalid/plan", "must be an HTTP(S) issue URL or a local plan path"),
])
def test_malformed_reference_urls_name_the_problem(tmp_path, url, message):
    path = _write(tmp_path, f"schema_version: 1\nacceptance:\n  reference: '{url}'\n")
    result = task_input.preview(path)
    assert result["errors"] == [
        {"field": "acceptance.reference", "message": message, "source": "yaml"}]
    assert result["task"]["acceptance"]["reference"] is None
    assert result["sources"]["acceptance.reference"] == "invalid"
    blocked = {item["field"]: item["message"] for item in result["blockers"]}
    assert blocked["acceptance.reference"] == (
        "invalid; fix the reported error; required for plan/run")


@pytest.mark.parametrize("dest, field, value, message", [
    ("repo", "optimization.repository", "checkout\0", "must not contain a NUL character"),
    ("candidate_repo", "optimization.candidate_repository", "cand\0idate",
     "must not contain a NUL character"),
    ("python", "environment.python", "python3\0", "must not contain a NUL character"),
    ("python", "environment.python", ".venv/bin/py\0thon", "must not contain a NUL character"),
    ("baseline_command", "environment.baseline_command", "python b\0.py",
     "argv items must not contain a NUL character"),
    ("candidate_command", "environment.candidate_command", ["python", "c\0.py"],
     "argv items must not contain a NUL character"),
    ("validation_command", "environment.quality_command", "python\0 quality.py",
     "argv items must not contain a NUL character"),
])
def test_nul_in_an_explicit_override_is_rejected_before_normalization(
    tmp_path, dest, field, value, message,
):
    task_file = _copy(tmp_path)
    flag = task_input.BY_PATH[field].flag
    result = task_input.preview(task_file, {dest: value}, cwd=str(tmp_path))
    assert not result["valid"] and not result["complete"]
    assert result["errors"] == [
        {"field": field, "message": f"{flag} {message}", "source": "cli"}]
    section, name = field.split(".")
    assert result["task"][section][name] == _expected_complete(task_file.parent)[section][name]
    assert result["sources"][field] == "yaml"


def test_missing_pyyaml_is_a_document_error_not_a_traceback(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "yaml.py").write_text("raise ImportError('PyYAML unavailable')\n",
                                     encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(blocked), str(REPO / "src"), os.environ.get("PYTHONPATH", "")]))
    completed = subprocess.run(
        [sys.executable, "-m", "inferrsi", "task", "validate", str(COMPLETE), "--json"],
        capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, env=env, check=False,
    )
    assert completed.returncode == 1, completed.stderr
    assert "Traceback" not in completed.stderr
    error = json.loads(completed.stdout)["errors"][0]
    assert error["field"] == "$" and "PyYAML" in error["message"]


def test_importing_the_cli_does_not_load_yaml():
    completed = subprocess.run(
        [sys.executable, "-c",
         "import sys, inferrsi.apps.cli, inferrsi.apps.cli.task_input; "
         "assert 'yaml' not in sys.modules"],
        capture_output=True, text=True, check=False,
        env=dict(os.environ, PYTHONPATH=str(REPO / "src")),
    )
    assert completed.returncode == 0, completed.stderr


def test_package_data_and_core_dependency_cover_the_task_resources():
    metadata = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert "PyYAML>=6.0" in metadata["project"]["dependencies"]
    assert metadata["project"]["optional-dependencies"]["skills"] == ["PyYAML>=6.0"]
    root = REPO / "src" / "inferrsi"
    declared = {path.relative_to(root).as_posix()
                for pattern in metadata["tool"]["setuptools"]["package-data"]["inferrsi"]
                for path in root.glob(pattern) if path.is_file()}
    assert {"apps/cli/task-input/v1/schema.json",
            "apps/cli/task-input/v1/template.yaml"} <= declared
    assert sorted(path.name for path in RESOURCES.iterdir()) == ["schema.json", "template.yaml"]


def test_schema_and_template_commands_print_the_packaged_text(capsys):
    assert _main(capsys, "task", "schema") == (0, task_input.schema_text())
    assert _main(capsys, "task", "template") == (0, task_input.template_text())
