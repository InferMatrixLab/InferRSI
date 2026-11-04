"""Host-only binding/capacity controls; never execute a solution."""

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract
import data_binding


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.dataset = (
            json.dumps(
                {
                    "task_id": "Synthetic/one",
                    "prompt": "def f():\n",
                    "canonical_solution": "    return 1\n",
                    "base_input": [[1]],
                    "plus_input": [[2, "\u0000😀"]],
                },
                ensure_ascii=False,
            )
            + "\n"
        ).encode()
        self.compressed = gzip.compress(self.dataset)
        self.lock = {
            "gzip_sha256": contract.sha(self.compressed),
            "dataset_sha256": contract.sha(self.dataset),
            "dataset_bytes": len(self.dataset),
            "task_count": 1,
            "cohort_sha256": contract.sha(contract.canonical(["Synthetic/one"])),
        }
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gz = self.root / "data.gz"
        self.gz.write_bytes(self.compressed)

    def payload(self):
        with patch.object(data_binding, "lock", return_value=self.lock):
            identity = data_binding.create(self.gz, self.root / "input")
            return contract.inputs(self.root / "input", **identity, maximum=67108864)

    def test_complete_binding(self):
        raw, export, samples = self.payload()
        with patch.object(data_binding, "lock", return_value=self.lock):
            data_binding.validate(raw, export, samples)

    def test_gzip_drift(self):
        self.gz.write_bytes(b"wrong")
        with (
            patch.object(data_binding, "lock", return_value=self.lock),
            self.assertRaisesRegex(ValueError, "compressed dataset"),
        ):
            data_binding.create(self.gz, self.root / "input")

    def test_dataset_drift(self):
        raw, export, samples = self.payload()
        raw["humaneval-subset.jsonl"] += b"\n"
        with (
            patch.object(data_binding, "lock", return_value=self.lock),
            self.assertRaisesRegex(ValueError, "full dataset"),
        ):
            data_binding.validate(raw, export, samples)

    def test_model_solution_rejected(self):
        raw, export, samples = self.payload()
        raw["humaneval-solutions.jsonl"] = raw["humaneval-solutions.jsonl"].replace(
            b"return 1", b"return 2"
        )
        with (
            patch.object(data_binding, "lock", return_value=self.lock),
            self.assertRaisesRegex(ValueError, "canonical references"),
        ):
            data_binding.validate(raw, export, samples)

    def test_missing_task_rejected(self):
        raw, export, samples = self.payload()
        with (
            patch.object(data_binding, "lock", return_value=self.lock),
            self.assertRaisesRegex(ValueError, "full cohort"),
        ):
            data_binding.validate(raw, export, {})

    def test_capacity_includes_escaping_and_failure_details(self):
        report = data_binding.capacity(self.dataset, 67108864)
        self.assertEqual(report["solution_serialization_bound_bytes"], 402653184)
        self.assertGreater(report["result_upper_bound_bytes"], 402653184)
        self.assertLess(report["result_upper_bound_bytes"], 536870912)

    def test_policy_preserves_official_defaults(self):
        path = Path(__file__).parent / "policy.json"
        selected = contract.policy(path, contract.sha(path.read_bytes()))
        self.assertGreater(selected["cpu_seconds"], selected["wall_seconds"])
        self.assertEqual(selected["evalplus"]["memory_override"], None)
        self.assertEqual(selected["evalplus"]["timeout_override"], None)
        self.assertIs(selected["qualified"], False)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            contract.decode(b'{"task_id":"x","task_id":"y"}')


if __name__ == "__main__":
    unittest.main()
