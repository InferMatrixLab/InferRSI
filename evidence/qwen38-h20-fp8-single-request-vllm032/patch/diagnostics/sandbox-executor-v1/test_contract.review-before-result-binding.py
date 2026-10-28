"""Host-only acceptance/rejection controls. No model/evaluator code is executed."""

import copy
import hashlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract
import fixtures

# Only this host-only test stubs an unused legacy helper dependency if absent.
try:
    import psutil  # noqa: F401
except ImportError:
    sys.modules["psutil"] = types.ModuleType("psutil")
import executor


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.identity = fixtures.create(self.inputs)
        self.maximum = 67108864
        _, self.export, self.samples = self.validate()
        self.value = {
            "hash": self.export["evalplus_dataset_md5"],
            "eval": {
                identity: [
                    {"solution": row["solution"], "base_status": "pass", "plus_status": "pass"}
                ]
                for identity, row in self.samples.items()
            },
        }

    def validate(self, **changes):
        return contract.inputs(self.inputs, **{**self.identity, **changes}, maximum=self.maximum)

    def reject_result(self, value):
        with self.assertRaises(ValueError):
            contract.results(contract.canonical(value), self.export, self.samples, self.maximum)

    def rebind(self):
        samples = (self.inputs / contract.INPUT_NAMES[0]).read_bytes()
        dataset = (self.inputs / contract.INPUT_NAMES[1]).read_bytes()
        raw = contract.canonical(
            {
                **self.export,
                "samples_sha256": contract.sha(samples),
                "dataset_sha256": contract.sha(dataset),
                "evalplus_dataset_md5": hashlib.md5(dataset).hexdigest(),
            }
        )
        (self.inputs / "human-export.json").write_bytes(raw)
        self.identity["export_sha256"] = contract.sha(raw)

    def test_valid_and_large_result(self):
        raw = contract.canonical(self.value)
        self.assertGreater(len(raw), 1048576)
        self.assertEqual(
            set(contract.results(raw, self.export, self.samples, self.maximum)), set(self.samples)
        )

    def test_wrong_export_hash(self):
        with self.assertRaises(ValueError):
            self.validate(export_sha256="0" * 64)

    def test_real_v5_export_marker_and_wrong_types(self):
        self.assertEqual(
            set(self.export),
            {
                "samples_sha256",
                "dataset_sha256",
                "evalplus_dataset_md5",
                "task_ids",
                "generated_code_executed",
            },
        )
        self.assertIs(self.export["generated_code_executed"], False)
        for marker in (True, 0, "false", None):
            value = {**self.export, "generated_code_executed": marker}
            raw = contract.canonical(value)
            (self.inputs / "human-export.json").write_bytes(raw)
            with self.assertRaises(ValueError):
                self.validate(export_sha256=contract.sha(raw))
        value.pop("generated_code_executed")
        raw = contract.canonical(value)
        (self.inputs / "human-export.json").write_bytes(raw)
        with self.assertRaises(ValueError):
            self.validate(export_sha256=contract.sha(raw))

    def test_wrong_cohort_hash(self):
        with self.assertRaises(ValueError):
            self.validate(cohort_sha256="0" * 64)

    def test_tampered_samples(self):
        path = self.inputs / contract.INPUT_NAMES[0]
        path.write_bytes(path.read_bytes().replace(b"ArithmeticError", b"ValueError"))
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_samples_even_with_rebound_digest(self):
        path = self.inputs / contract.INPUT_NAMES[0]
        path.write_bytes(path.read_bytes() + path.read_bytes().splitlines()[0] + b"\n")
        self.rebind()
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_sample_even_with_rebound_digest(self):
        path = self.inputs / contract.INPUT_NAMES[0]
        path.write_bytes(b"\n".join(path.read_bytes().splitlines()[1:]) + b"\n")
        self.rebind()
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_dataset_even_with_rebound_digest(self):
        path = self.inputs / contract.INPUT_NAMES[1]
        path.write_bytes(path.read_bytes() + path.read_bytes().splitlines()[0] + b"\n")
        self.rebind()
        with self.assertRaises(ValueError):
            self.validate()

    def test_input_byte_cap(self):
        self.maximum = 1048576
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_json_and_nonfinite(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.assertRaises(ValueError):
                contract.decode(raw)

    def test_result_truncated_or_oversized(self):
        raw = contract.canonical(self.value)
        for data, cap in ((raw[:-1], self.maximum), (raw, 1048576), (b"", self.maximum)):
            with self.assertRaises(ValueError):
                contract.results(data, self.export, self.samples, cap)

    def test_result_wrong_task_and_duplicate(self):
        value = copy.deepcopy(self.value)
        value["eval"].pop("Synthetic/correct")
        self.reject_result(value)
        value = copy.deepcopy(self.value)
        value["eval"]["Synthetic/correct"] *= 2
        self.reject_result(value)

    def test_result_wrong_solution_status_dataset(self):
        for key, replacement in (("solution", "different"), ("plus_status", "unknown")):
            value = copy.deepcopy(self.value)
            value["eval"]["Synthetic/correct"][0][key] = replacement
            self.reject_result(value)
        self.reject_result({**self.value, "hash": "0" * 32})

    def test_policy_digest_and_unqualified_scope(self):
        path = executor.SOURCE / "policy.json"
        raw = path.read_bytes()
        policy = contract.policy(path, contract.sha(raw))
        self.assertFalse(policy["qualified"])
        self.assertEqual(policy["as_bytes"], 4294967296)
        with self.assertRaises(ValueError):
            contract.policy(path, "0" * 64)
        changed = self.root / "policy.json"
        value = {**policy, "qualified": True}
        changed.write_bytes(contract.canonical(value))
        with self.assertRaises(ValueError):
            contract.policy(changed, contract.sha(changed.read_bytes()))

    def test_actual_command_and_new_limits(self):
        path = executor.SOURCE / "policy.json"
        digest = contract.sha(path.read_bytes())
        policy = contract.policy(path, digest)
        locators = {
            "bwrap": "/tool/bwrap",
            "python_root": "/runtime/python",
            "site_root": "/runtime/site",
            "python_relative": "bin/python3.12",
            "system_libraries": {},
        }
        args = executor.command(locators, self.inputs, policy, digest, **self.identity)
        for target, size in (("/work", "268435456"), ("/dev/shm", "33554432")):
            self.assertEqual(args[args.index(target) - 2], size)
        self.assertIn("/opt/executor/inner.py", args)
        self.assertIn("/input", args)
        with (
            mock.patch.object(executor.os, "sched_getaffinity", return_value={3, 4}, create=True),
            mock.patch.object(executor.os, "sched_setaffinity", create=True),
            mock.patch.object(executor.resource, "setrlimit") as setlimit,
        ):
            executor.limits(policy)
        self.assertIn(
            mock.call(executor.resource.RLIMIT_AS, (4294967296, 4294967296)),
            setlimit.call_args_list,
        )
        self.assertIn(mock.call(executor.resource.RLIMIT_CPU, (120, 120)), setlimit.call_args_list)

    def test_existing_output_rejected_before_capability(self):
        output = self.root / "old-output"
        output.mkdir()
        args = types.SimpleNamespace(
            inputs=self.inputs,
            output=output,
            bundle=self.root,
            policy_sha256=contract.sha((executor.SOURCE / "policy.json").read_bytes()),
            **self.identity,
        )
        with mock.patch.object(executor.supervisor, "capability") as capability:
            with self.assertRaises(FileExistsError):
                executor.evaluate_export(args)
            capability.assert_not_called()


if __name__ == "__main__":
    unittest.main()
