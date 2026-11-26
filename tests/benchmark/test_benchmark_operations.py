"""Discovery and launch for registered benchmark packages."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.workflows import benchmark_operations
from inferrsi.benchmark import registry
from inferrsi.harness.executor import _benchmark_child

PACKAGED_WORKLOADS = {
    "moe-forward-npu": "moe-shared-ep2-npu-v1",
    "qwen21-denoise-npu": "qwen21-denoise-npu-v1",
    "qwen3-tts-npu": "qwen3-tts-npu-v2",
}


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_library_root", lambda: tmp_path)
    return tmp_path


def write_registry(library, value):
    (library / "index.json").write_text(json.dumps(value), encoding="utf-8")


def test_iterative_listing_uses_packaged_files_without_executing_them(library, capsys):
    names = ["z-task", "directory-task", "a-task"]
    write_registry(library, {"schema_version": 1, "packages": names})
    for name in names:
        (library / name).mkdir()
    (library / "directory-task" / "optimization.py").mkdir()

    assert main(["benchmarks", "list", "--iterative"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    for name in ("z-task", "a-task"):
        (library / name / "optimization.py").write_text(
            'raise AssertionError("Discovery executed the task protocol")\n', encoding="utf-8",
        )
    assert main(["benchmarks", "list", "--iterative"]) == 0
    assert json.loads(capsys.readouterr().out) == ["a-task", "z-task"]


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
        "assert execute_trial.__module__ == 'inferrsi.harness.executor.trials.external'\n",
        encoding="utf-8",
    )
    assert main(["benchmarks", "run", package.name]) == 0


@pytest.mark.parametrize("startup_shadow", ["cwd", "other-runtime"])
def test_direct_task_child_uses_the_selected_runtime_before_host_imports(tmp_path, startup_shadow):
    runner = Path(_benchmark_child.__file__).resolve()
    shadow = tmp_path / "other-runtime"
    shadow.mkdir()
    (shadow / "inferrsi.py").write_text("raise RuntimeError('wrong inherited runtime')\n")
    (tmp_path / "inferrsi.py").write_text("raise RuntimeError('wrong cwd runtime')\n")
    task = tmp_path / "task"
    task.mkdir()
    (task / "helper.py").write_text("VALUE = 42\n")
    entry = task / "benchmark.py"
    entry.write_text(
        "import importlib.util, sys\nfrom pathlib import Path\nfrom helper import VALUE\n"
        "assert VALUE == 42\n"
        "assert Path(execute_trial.__code__.co_filename).resolve() == "
        "Path(sys.argv[1]).resolve()\n"
        "assert importlib.util.find_spec('project') is None\n"
        "assert importlib.util.find_spec('candidates') is None\n"
        "print('selected runtime and task helper')\n",
        encoding="utf-8",
    )
    # Windows can start an extended-path script with an empty sys.path[0].
    # Recreate that startup without relying on host path-length limits. The
    # isolated child also starts without any installed/editable InferRSI.
    bootstrap = (
        "import runpy,sys; entry=runpy.run_path(sys.argv[1]); "
        "sys.path.insert(0,sys.argv[3]); "
        "entry['_run_entry'](sys.argv[2],[sys.argv[4]])"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", bootstrap, str(runner), str(entry),
         "" if startup_shadow == "cwd" else str(shadow),
         str(runner.parent / "trials/external.py")],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "selected runtime and task helper"


def test_cli_lists_the_three_packaged_workloads(capsys):
    assert main(["benchmarks", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == sorted(PACKAGED_WORKLOADS)
    assert registry.builtin_tasks() == sorted(PACKAGED_WORKLOADS)


def test_cli_lists_packaged_iterative_workloads(capsys):
    assert main(["benchmarks", "list", "--iterative"]) == 0
    assert json.loads(capsys.readouterr().out) == ["moe-forward-npu", "qwen21-denoise-npu"]


def test_benchmark_list_help_documents_iterative(capsys):
    with pytest.raises(SystemExit) as result:
        main(["benchmarks", "list", "--help"])
    assert result.value.code == 0
    assert "--iterative" in capsys.readouterr().out


@pytest.mark.parametrize("name,task_id", PACKAGED_WORKLOADS.items())
def test_cli_show_reads_the_relocated_manifest(name, task_id, capsys):
    assert main(["benchmarks", "show", name]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["package"] == name
    assert result["manifest"]["id"] == task_id
    assert result["manifest"]["backend"] == "ascend"
    for resource in result["files"]:
        assert registry.task_resources(name).joinpath(resource).is_file()
    assert {"task.json", "TASK.md", "baseline.py", "LICENSE"} <= set(result["files"])
    assert "benchmark.py" in result["files"]


def test_cwd_package_cannot_shadow_packaged_task(tmp_path, monkeypatch):
    shadow = tmp_path / "qwen3-tts-npu"
    shadow.mkdir()
    (shadow / "task.json").write_text('{"id": "shadow"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    manifest = registry.describe_task("qwen3-tts-npu")["manifest"]
    assert manifest["id"] == PACKAGED_WORKLOADS["qwen3-tts-npu"]


@pytest.mark.parametrize("name", ["missing-task", "../qwen3-tts-npu"])
def test_unknown_packages_are_rejected(name):
    with pytest.raises(ValueError, match="Unknown engineering benchmark"):
        registry.task_resources(name)


def test_discovery_does_not_import_device_libraries():
    script = """
import sys
from inferrsi.apps.cli import main
from inferrsi.apps.workflows import benchmark_operations
from inferrsi.benchmark.registry import builtin_tasks, describe_task
for name in builtin_tasks():
    describe_task(name)
assert main(["benchmarks", "list", "--iterative"]) == 0
assert not {'torch', 'torch_npu', 'qwen_tts', 'vllm', 'vllm_omni'} & sys.modules.keys()
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=15)


@pytest.mark.parametrize("name", PACKAGED_WORKLOADS)
def test_packaged_task_entry_help_needs_no_npu(name):
    result = subprocess.run(
        [sys.executable, "-m", "inferrsi", "benchmarks", "run", name, "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    markers = {
        "moe-forward-npu": ("--pairs", "--candidate"),
        "qwen21-denoise-npu": ("--candidate", "--check-only"),
        "qwen3-tts-npu": ("prepare", "serve", "collect", "assess"),
    }
    assert all(marker in result.stdout for marker in markers[name])


@pytest.mark.parametrize("name", PACKAGED_WORKLOADS)
@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_generic_launcher_preserves_task_arguments_and_status(name, exit_code, monkeypatch):
    arguments = ["--task-specific-flag", "value with spaces"]
    monkeypatch.setattr(sys, "dont_write_bytecode", True)

    def call(command, *, env):
        assert command == [
            sys.executable, str(Path(_benchmark_child.__file__).resolve()),
            str(registry.task_resources(name).joinpath("benchmark.py")), *arguments
        ]
        package = Path(env["PYTHONPATH"].split(os.pathsep)[0]) / "inferrsi"
        assert (package / "apps" / "cli" / "__init__.py").is_file()
        assert not (package / "cli.py").exists()
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        return exit_code

    monkeypatch.setattr("subprocess.call", call)
    assert main(["benchmarks", "run", name, *arguments]) == exit_code
