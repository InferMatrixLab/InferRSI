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
