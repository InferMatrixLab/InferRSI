"""Discovery and normal entry points for the packaged NPU workloads."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.benchmark.registry import builtin_tasks, describe_task, task_resources
from inferrsi.cli import main
from inferrsi.harness import optimization_session

EXPECTED = {
    "moe-forward-npu": "moe-shared-ep2-npu-v1",
    "qwen21-denoise-npu": "qwen21-denoise-npu-v1",
    "qwen3-tts-npu": "qwen3-tts-npu-v2",
}


def test_cli_lists_the_three_packaged_workloads(capsys):
    assert main(["benchmarks", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == sorted(EXPECTED)
    assert builtin_tasks() == sorted(EXPECTED)


@pytest.mark.parametrize("name,task_id", EXPECTED.items())
def test_cli_show_reads_the_relocated_manifest(name, task_id, capsys):
    assert main(["benchmarks", "show", name]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["package"] == name
    assert result["manifest"]["id"] == task_id
    assert result["manifest"]["backend"] == "ascend"
    for resource in result["files"]:
        assert task_resources(name).joinpath(resource).is_file()
    assert {"task.json", "TASK.md", "baseline.py", "LICENSE"} <= set(result["files"])
    assert "benchmark.py" in result["files"]


def test_cwd_package_cannot_shadow_packaged_task(tmp_path, monkeypatch):
    shadow = tmp_path / "qwen3-tts-npu"
    shadow.mkdir()
    (shadow / "task.json").write_text('{"id": "shadow"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert describe_task("qwen3-tts-npu")["manifest"]["id"] == EXPECTED["qwen3-tts-npu"]


@pytest.mark.parametrize("name", ["missing-task", "../qwen3-tts-npu"])
def test_unknown_packages_are_rejected(name):
    with pytest.raises(ValueError, match="Unknown engineering benchmark"):
        task_resources(name)


def test_discovery_does_not_import_device_libraries():
    script = """
import sys
from inferrsi.benchmark.registry import builtin_tasks, describe_task
for name in builtin_tasks():
    describe_task(name)
assert not {'torch', 'torch_npu', 'qwen_tts', 'vllm', 'vllm_omni'} & sys.modules.keys()
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=15)


@pytest.mark.parametrize("name", EXPECTED)
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


@pytest.mark.parametrize("name", EXPECTED)
@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_generic_launcher_preserves_task_arguments_and_status(name, exit_code, monkeypatch):
    arguments = ["--task-specific-flag", "value with spaces"]
    monkeypatch.setattr(sys, "dont_write_bytecode", True)

    def call(command, *, env):
        assert command == [
            sys.executable, str(Path(optimization_session.__file__).resolve()),
            str(task_resources(name).joinpath("benchmark.py")), *arguments
        ]
        assert (Path(env["PYTHONPATH"].split(os.pathsep)[0]) / "inferrsi" / "cli.py").is_file()
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        return exit_code

    monkeypatch.setattr("subprocess.call", call)
    assert main(["benchmarks", "run", name, *arguments]) == exit_code
