"""Common discovery/launch behavior works with a task added only as resources."""

import json

import pytest

from inferrsi import benchmark_operations
from inferrsi.benchmark import registry
from inferrsi.cli import main


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_library_root", lambda: tmp_path)
    return tmp_path


def write_registry(library, value):
    (library / "index.json").write_text(json.dumps(value), encoding="utf-8")


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_new_task_needs_only_package_and_registry(library, capsys, exit_code):
    package = library / "new-workload"
    package.mkdir()
    write_registry(library, {"schema_version": 1, "packages": [package.name]})
    manifest = {"id": "independent-task-id", "arbitrary-task-setting": [1, 2]}
    (package / "task.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "benchmark.py").write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    assert main(["benchmarks", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == [package.name]
    assert main(["benchmarks", "show", package.name]) == 0
    assert json.loads(capsys.readouterr().out)["manifest"] == manifest
    receipt = library / "receipt.json"
    arguments = ["--unknown-to-framework", "value with spaces", "中文"]
    assert main(["benchmarks", "run", package.name, str(receipt), *arguments]) == exit_code
    assert json.loads(receipt.read_text(encoding="utf-8")) == arguments
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("value", [
    [], {}, {"schema_version": True, "packages": []},
    {"schema_version": 2, "packages": []},
    {"schema_version": 1, "packages": "a-task"},
    {"schema_version": 1, "packages": ["a-task", "a-task"]},
])
def test_invalid_registry_is_rejected(library, value):
    write_registry(library, value)
    with pytest.raises(ValueError):
        registry.builtin_tasks()


@pytest.mark.parametrize("name", ["../escape", "a/b", "a\\b", "/absolute", ".", "", None, 1])
def test_unsafe_registry_names_are_rejected(library, name):
    write_registry(library, {"schema_version": 1, "packages": [name]})
    with pytest.raises(ValueError, match="Invalid task package name"):
        registry.builtin_tasks()


def test_registered_package_must_exist(library):
    write_registry(library, {"schema_version": 1, "packages": ["absent-task"]})
    with pytest.raises(ValueError, match="Missing registered task package"):
        registry.task_resources("absent-task")


def test_registered_entry_must_exist(library):
    (library / "empty-task").mkdir()
    write_registry(library, {"schema_version": 1, "packages": ["empty-task"]})
    with pytest.raises(ValueError, match="Missing benchmark.py"):
        benchmark_operations.run_task("empty-task", [])


def test_application_injects_executor_and_preserves_script_imports(library):
    package = library / "new-workload"
    package.mkdir()
    write_registry(library, {"schema_version": 1, "packages": [package.name]})
    (package / "helper.py").write_text("VALUE = 42\n", encoding="utf-8")
    (package / "benchmark.py").write_text(
        "from helper import VALUE\n"
        "assert VALUE == 42\n"
        "assert execute_trial.__module__ == 'inferrsi.harness.scenarios.external'\n",
        encoding="utf-8",
    )
    assert main(["benchmarks", "run", package.name]) == 0
