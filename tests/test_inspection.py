"""Inspection facts must not become accelerator compatibility claims."""

import json
import sys
import unittest
from importlib import metadata
from pathlib import Path
from unittest.mock import patch

from inferrsi.harness.reporting import write_report
from inferrsi.infra.artifacts import atomic_write_json
from inferrsi.inspection import inspect_environment

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
                "inferrsi.execution.repository_identity",
                return_value={"available": True, "head": "test"},
            ),
            patch("inferrsi.inspection._command", side_effect=command),
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
                "inferrsi.execution.repository_identity",
                return_value={"available": True, "head": "test"},
            ),
            patch("inferrsi.inspection._command", side_effect=command),
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
    with patch("inferrsi.infra.inspection.platform.node", return_value=hostname) as node:
        environment = InspectionTests().inspect_cuda("0, GPU-test, Synthetic GPU, 999.0\n")
    node.assert_not_called()
    assert "hostname" not in environment["host"]
    assert environment["host"]["platform"]
    assert environment["device"]["status"] == "available"
    atomic_write_json(tmp_path / "environment.json", environment)
    report = write_report(tmp_path)
    assert hostname not in (tmp_path / "environment.json").read_text(encoding="utf-8")
    assert hostname not in report.read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
