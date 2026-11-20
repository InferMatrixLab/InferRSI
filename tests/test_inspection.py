"""Inspection facts must not become accelerator compatibility claims."""

import importlib
import importlib.util
import inspect
import json
import os
import pickle
import subprocess
import sys
import unittest
from importlib import metadata
from pathlib import Path
from unittest.mock import patch

import pytest

from inferrsi.apps import inspection as host_inspection
from inferrsi.apps.host import commands, targets
from inferrsi.apps.host import inspection as facts
from inferrsi.apps.inspection import inspect_environment
from inferrsi.apps.legacy.reporting import write_report
from inferrsi.infra.artifacts import atomic_write_json

ROCM_INFO = (
    "=====================\n"
    "HSA Agents\n"
    "=====================\n"
    "Agent 1\n"
    "  Name:                    AMD EPYC 7742 64-Core Processor\n"
    "  Uuid:                    CPU-XX\n"
    "  Marketing Name:          AMD EPYC 7742 64-Core Processor\n"
    "  Device Type:             CPU\n"
    "Agent 2\n"
    "  Name:                    gfx942\n"
    "  Uuid:                    GPU-1234\n"
    "  Marketing Name:          AMD Instinct MI300X\n"
    "  Device Type:             GPU\n"
)


NPC_TABLE = (
    "+----------------------------------------------------------------------------------------+\n"
    "| npu-smi 23.0.3                   Version: 23.0.3                                       |\n"
    "+-------------------+-----------------+--------------------------------------------------+\n"
    "| NPU     Name      | Health          | Power(W)     Temp(C)       Hugepages-Usage(page) |\n"
    "| Chip    Device    | Bus-Id          | AICore(%)    Memory-Usage(MB)                    |\n"
    "+===================+=================+==================================================+\n"
    "| 0       910B3     | OK              | 93.5         34            0    / 0              |\n"
    "| 0       0         | 0000:C1:00.0    | 0            0    / 0     3301 / 65535         |\n"
    "+===================+=================+==================================================+\n"
    "| 1       310P3     | OK              | 88.1         36            0    / 0              |\n"
    "| 1       0         | 0000:C2:00.0    | 0            0    / 0     1200 / 32768         |\n"
    "+===================+=================+==================================================+\n"
)


class InspectionTests(unittest.TestCase):
    def inspect_cuda(self, rows, ids=("0",), model=None):
        def command(argv):
            if "-c" in argv:
                stdout = json.dumps({"python": "test", "packages": {"torch": "test-version"}})
            elif "topo" in argv:
                stdout = "test topology"
            else:
                stdout = rows
            return {"argv": argv, "returncode": 0, "stdout": stdout, "stderr": ""}

        with (
            patch(
                "inferrsi.apps.inspection.repository_identity",
                return_value={"available": True, "head": "test"},
            ),
            patch("inferrsi.apps.inspection._command", side_effect=command),
        ):
            return inspect_environment(".", "vllm_omni", "cuda", device_ids=ids, device_model=model)

    def test_requested_device_and_model_are_checked(self):
        rows = "0, GPU-A, NVIDIA A100, 999.0\n1, GPU-B, NVIDIA H200, 999.0\n"
        result = self.inspect_cuda(rows, ids=("1",), model="H200")
        self.assertEqual(result["device"]["status"], "available")
        self.assertEqual(result["device"]["devices"][1]["driver_version"], "999.0")
        self.assertEqual(result["compatibility"], "unverified")
        mismatch = self.inspect_cuda(rows, ids=("0",), model="H200")
        self.assertEqual(mismatch["device"]["status"], "device_model_mismatch")

    def test_successful_tool_without_requested_gpu_is_not_available(self):
        empty = self.inspect_cuda("")
        self.assertEqual(empty["device"]["status"], "unavailable")
        missing = self.inspect_cuda("0, GPU-A, NVIDIA H200, 999.0\n", ids=("8",))
        self.assertFalse(missing["device"]["selection_verified"])
        self.assertEqual(missing["device"]["status"], "unavailable")

    def inspect_tool(self, backend, stdout, ids=(), model=None):
        """A tool that exits zero and reports the given device table."""

        def command(argv):
            if "-c" in argv:
                stdout_value = json.dumps({"python": "test", "packages": {}})
            else:
                stdout_value = stdout
            return {"argv": argv, "returncode": 0, "stdout": stdout_value, "stderr": ""}

        with (
            patch(
                "inferrsi.apps.inspection.repository_identity",
                return_value={"available": True, "head": "test"},
            ),
            patch("inferrsi.apps.inspection._command", side_effect=command),
        ):
            return inspect_environment(
                ".", "vllm_omni", backend, device_ids=ids, device_model=model
            )

    def test_ascend_tool_exit_code_alone_does_not_qualify_a_device(self):
        # npu-smi exiting 0 says nothing about which NPU exists. Only a parsed
        # device row proves discovery; the requested ID must be present.
        table = NPC_TABLE
        result = self.inspect_tool("ascend", table, ids=("3",), model="Ascend910B")
        self.assertFalse(result["device"]["selection_verified"])
        self.assertNotEqual(result["device"]["status"], "available")
        present = self.inspect_tool("ascend", table, ids=("0",), model="Ascend910B")
        self.assertTrue(present["device"]["selection_verified"])
        self.assertEqual(present["device"]["status"], "available")
        wrong_model = self.inspect_tool("ascend", table, ids=("0",), model="Ascend310")
        self.assertNotEqual(wrong_model["device"]["status"], "available")

    def test_ascend_stray_number_is_not_a_device_id(self):
        # The requested ID appears only as a temperature value, never in a row's
        # ID column, so no record carries it.
        table = NPC_TABLE.replace("93.5         34", "93.5         3 ")
        result = self.inspect_tool("ascend", table, ids=("3",))
        self.assertFalse(result["device"]["selection_verified"])
        self.assertNotEqual(result["device"]["status"], "available")
        ids = [device["id"] for device in result["device"]["devices"]]
        self.assertEqual(ids, ["0", "1"])
        self.assertNotIn("3", ids)
        self.assertIn("Requested device IDs absent", result["device"]["reason"])

    def test_ascend_empty_output_never_qualifies_a_device(self):
        # No requested IDs and no parseable records is missing evidence, not proof.
        result = self.inspect_tool("ascend", "")
        self.assertFalse(result["device"]["selection_verified"])
        self.assertNotEqual(result["device"]["status"], "available")
        self.assertIn("No device records parsed", result["device"]["reason"])

    def test_ascend_unrequested_ids_still_require_records(self):
        result = self.inspect_tool("ascend", "npu-smi: no devices found")
        self.assertFalse(result["device"]["selection_verified"])
        self.assertNotEqual(result["device"]["status"], "available")

    def test_ascend_id_and_model_must_match_the_same_record(self):
        # NPU 1 is a 310P3; the requested 910B3 exists only on NPU 0.
        same = self.inspect_tool("ascend", NPC_TABLE, ids=("0",), model="910B3")
        self.assertEqual(same["device"]["status"], "available")
        self.assertTrue(same["device"]["selection_verified"])
        other = self.inspect_tool("ascend", NPC_TABLE, ids=("1",), model="910B3")
        self.assertEqual(other["device"]["status"], "device_model_mismatch")
        self.assertFalse(other["device"]["selection_verified"])
        both = self.inspect_tool("ascend", NPC_TABLE, ids=("0", "1"), model="910B3")
        self.assertNotEqual(both["device"]["status"], "available")

    def test_rocm_tool_exit_code_alone_does_not_qualify_a_device(self):
        info = ROCM_INFO
        missing = self.inspect_tool("rocm", info, ids=("GPU-9999",))
        self.assertFalse(missing["device"]["selection_verified"])
        self.assertNotEqual(missing["device"]["status"], "available")
        found = self.inspect_tool("rocm", info, ids=("GPU-1234",))
        self.assertEqual(found["device"]["status"], "available")

    def test_rocm_cpu_agent_is_not_an_accelerator(self):
        # The host CPU agent reports a Uuid and a marketing name too.
        result = self.inspect_tool("rocm", ROCM_INFO, ids=("CPU-XX",))
        self.assertFalse(result["device"]["selection_verified"])
        self.assertEqual([item["id"] for item in result["device"]["devices"]], ["GPU-1234"])

    def test_rocm_empty_output_never_qualifies_a_device(self):
        result = self.inspect_tool("rocm", "")
        self.assertFalse(result["device"]["selection_verified"])
        self.assertNotEqual(result["device"]["status"], "available")


class PythonInspectionTests(unittest.TestCase):
    def test_real_python_reports_requested_versions(self):
        result = inspect_environment(
            str(Path(__file__).resolve().parents[1]),
            "vllm_omni",
            "cpu",
            python=sys.executable,
        )
        probe = result["target_python"]
        self.assertEqual(probe["returncode"], 0, probe["stderr"])
        self.assertNotIn("parse_error", probe)
        environment = probe["environment"]
        self.assertEqual(environment["python"], sys.version)
        names = (
            "torch",
            "vllm",
            "vllm-omni",
            "vllm-afd-plugin",
            "vllm-rlt",
            "torch-npu",
            "nvidia-nccl-cu12",
            "nvidia-nccl-cu13",
            "nvidia-cuda-runtime-cu12",
            "nvidia-cuda-runtime-cu13",
            "mlx",
            "torch_musa",
            "vllm-musa",
            "mthreads-ml-py",
            "torchada",
            "mate",
        )
        self.assertEqual(set(environment["packages"]), set(names))
        for name in names:
            with self.subTest(package=name):
                try:
                    expected = metadata.version(name)
                except metadata.PackageNotFoundError:
                    expected = None
                self.assertEqual(environment["packages"][name], expected)
        self.assertEqual(result["device"]["status"], "available")
        self.assertEqual(result["compatibility"], "unverified")


def test_hostname_is_not_captured_in_environment_or_report(tmp_path):
    hostname = "private-host.example.invalid"
    with patch("inferrsi.apps.host.inspection.platform.node", return_value=hostname) as node:
        environment = InspectionTests().inspect_cuda("0, GPU-test, Synthetic GPU, 999.0\n")
    node.assert_not_called()
    assert "hostname" not in environment["host"]
    assert environment["host"]["platform"]
    assert environment["device"]["status"] == "available"
    atomic_write_json(tmp_path / "environment.json", environment)
    report = write_report(tmp_path)
    assert hostname not in (tmp_path / "environment.json").read_text(encoding="utf-8")
    assert hostname not in report.read_text(encoding="utf-8")


def _fake_command(argv):
    stdout = json.dumps({"python": "test", "packages": {}}) if "-c" in argv else ""
    return {"argv": argv, "returncode": 0, "stdout": stdout, "stderr": ""}


def test_canonical_binding_is_the_real_host_probe_and_git_identity():
    # #412 R1: the Apps composition binds the Infra facts API to this host.
    assert host_inspection._command is commands.probe_command
    assert host_inspection.repository_identity is targets.repository_identity
    assert host_inspection._inspect_environment is facts.inspect_environment
    assert inspect_environment.__module__ == "inferrsi.apps.inspection"
    assert str(inspect.signature(inspect_environment)) == (
        "(repo: str, repo_type: str, backend: str, *, device_ids: tuple[str, ...] = (), "
        "device_model: str | None = None, python: str | None = None) -> dict"
    )
    # The facts API keeps its own injectable ports and their real defaults.
    parameters = inspect.signature(facts.inspect_environment).parameters
    assert parameters["command"].default is commands.probe_command
    assert parameters["snapshot"].default is targets.repository_identity


def test_both_ports_are_read_from_the_canonical_module_on_each_call(monkeypatch):
    seen = []

    def snapshot(path):
        seen.append(("snapshot", path))
        return {"available": True, "head": "injected"}

    def command(argv):
        seen.append(("command", argv[0]))
        return _fake_command(argv)

    monkeypatch.setattr(host_inspection, "repository_identity", snapshot)
    monkeypatch.setattr(host_inspection, "_command", command)
    result = inspect_environment(".", "vllm_omni", "cpu", python="python-probe")
    assert seen[0] == ("snapshot", Path(".").resolve())
    assert ("command", "python-probe") in seen
    assert result["repository"] == {"available": True, "head": "injected"}
    assert result["target_python"]["environment"] == {"python": "test", "packages": {}}
    assert result["repository_pack"]["id"] == "vllm_omni"
    # Replacing a port again changes the very next call: nothing was captured early.
    monkeypatch.setattr(
        host_inspection, "repository_identity", lambda path: {"available": False}
    )
    assert inspect_environment(".", "vllm_omni", "cpu")["repository"] == {"available": False}


def test_port_failures_reach_the_caller_unchanged(monkeypatch):
    def broken(path):
        raise OSError("repository identity unavailable")

    def crashed(argv):
        raise RuntimeError("probe crashed")

    monkeypatch.setattr(host_inspection, "_command", _fake_command)
    monkeypatch.setattr(host_inspection, "repository_identity", broken)
    with pytest.raises(OSError, match="repository identity unavailable"):
        inspect_environment(".", "vllm_omni", "cpu")
    monkeypatch.setattr(
        host_inspection, "repository_identity", lambda path: {"available": False}
    )
    monkeypatch.setattr(host_inspection, "_command", crashed)
    with pytest.raises(RuntimeError, match="probe crashed"):
        inspect_environment(".", "vllm_omni", "cpu")
    # The pack reader still refuses an unknown repository type.
    monkeypatch.setattr(host_inspection, "_command", _fake_command)
    with pytest.raises(ValueError, match="Unknown repository type: not-a-pack"):
        inspect_environment(".", "not-a-pack", "cpu")


def test_probe_results_are_recorded_as_the_port_returned_them(monkeypatch):
    monkeypatch.setattr(
        host_inspection, "repository_identity", lambda path: {"available": False}
    )
    missing = {"returncode": None, "stdout": "", "stderr": "Executable not found"}
    monkeypatch.setattr(host_inspection, "_command", lambda argv: {"argv": argv, **missing})
    result = inspect_environment(".", "vllm_omni", "cpu", python="absent-python")
    assert result["target_python"]["argv"][0] == "absent-python"
    assert result["target_python"]["stderr"] == "Executable not found"
    assert "environment" not in result["target_python"]
    garbled = {"returncode": 0, "stdout": "not json", "stderr": ""}
    monkeypatch.setattr(host_inspection, "_command", lambda argv: {"argv": argv, **garbled})
    result = inspect_environment(".", "vllm_omni", "cpu")
    assert result["target_python"]["parse_error"] == (
        "Target Python did not emit a JSON environment"
    )
    assert result["compatibility"] == "unverified"


def test_retired_root_inspection_is_gone_and_host_facts_load_no_core():
    assert importlib.util.find_spec("inferrsi.inspection") is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("inferrsi.inspection")
    # A pickle that names the retired function no longer loads; the canonical one does.
    with pytest.raises(ModuleNotFoundError):
        pickle.loads(b"cinferrsi.inspection\ninspect_environment\n.")
    assert pickle.loads(pickle.dumps(inspect_environment)) is inspect_environment
    script = (
        "import sys\n"
        # #498 slice 3a: the facts API lives in apps/host and still loads no core module
        # and no Apps module outside its own package.
        "import inferrsi.apps.host.inspection\n"
        "cores = ('inferrsi.knowledge', 'inferrsi.harness', 'inferrsi.benchmark')\n"
        "loaded = [name for name in sys.modules if name.startswith(cores)]\n"
        "assert not loaded, loaded\n"
        "apps = [name for name in sys.modules if name.startswith('inferrsi.apps.')\n"
        "        and not name.startswith('inferrsi.apps.host')]\n"
        "assert not apps, apps\n"
        # The retired root binding reached the snapshot through the old run. The
        # canonical one loads no Benchmark module and no old-run composition.
        "import inferrsi.apps.inspection\n"
        "old_run = ('inferrsi.benchmark', 'inferrsi.apps.legacy', 'inferrsi.execution')\n"
        "loaded = [name for name in sys.modules if name.startswith(old_run)]\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    unittest.main()
