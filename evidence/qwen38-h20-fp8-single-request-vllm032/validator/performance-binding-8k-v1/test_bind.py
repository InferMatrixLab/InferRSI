"""Synthetic receipt controls only; raw HTTP audit is explicitly mocked here."""

import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bind as binding  # noqa: E402

COMPONENT = Path(
    os.environ.get(
        "PERFORMANCE_COMPONENT_DIR",
        str(Path(__file__).resolve().parent.parent / "fp8-projections-search-v1"),
    )
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BindingControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.component = self.root / "component"
        shutil.copytree(COMPONENT, self.component)
        self.run = self.root / "run"
        self.run.mkdir()
        self.lock = digest(self.component / "component.sha256")
        self.identities = json.loads((self.component / "source-identities.json").read_bytes())
        self.fixture = self.root / "fixture.json"
        self.fixture.write_text("{}\n")
        self.terminal = self.root / "terminal.txt"
        self.good_terminal = (
            "JobId=4242 JobState=COMPLETED ExitCode=0:0 RunTime=00:20:00 "
            "AllocTRES=cpu=8,gres/gpu=1 Restarts=0 SuspendTime=None\n"
        )
        self.terminal.write_text(self.good_terminal)
        component_names = [
            line.split("  ", 1)[1]
            for line in (self.component / "component.sha256").read_text().splitlines()
        ]
        for phase in ("before", "after"):
            (self.run / f"component-{phase}.txt").write_text(
                "".join(f"{name}: OK\n" for name in component_names)
            )
            (self.run / f"source-{phase}.txt").write_text(
                "".join(f"{name}: OK\n" for name in self.identities["source_files"])
            )
        (self.run / "exit-code.txt").write_text("0\n")
        (self.run / "postflight-status.tsv").write_text(
            "".join(
                f"{name}\t0\n"
                for name in ("model_runtime", "overlay", "engine_source", "component")
            )
        )
        write(
            self.run / "device.private.json",
            {
                "capability": [9, 0],
                "name": "NVIDIA H20",
                "uuid": "GPU-synthetic",
                "job": "4242",
                "cuda_visible_devices": "0",
                "torch": "2.13.0+cu130",
                "cuda": "13.0",
            },
        )
        model = json.loads((self.component / "model-byte-integrity.json").read_bytes())
        baseline = json.loads((self.component / "baseline-provenance.json").read_bytes())
        guard = {
            "model_report_sha256": digest(self.component / "model-byte-integrity.json"),
            "model_files_verified": len(model["files"]),
            "model_revision": model["revision"],
            "baseline_provenance_sha256": digest(self.component / "baseline-provenance.json"),
            "baseline_revision": baseline["source_revision"],
            "wheel_sha256": baseline["wheel_sha256"],
            "packages": baseline["packages"],
            "python": baseline["python"],
            "release_files": {f"vllm/synthetic_{i}.py": "1" * 64 for i in range(5446)},
        }
        overlay = {
            "files_verified": 899,
            "manifest_sha256": "3c427abc1f5f76abca793e0f5696e641fca99867620a66540e594ee975a0e1bc",
            "operator_binary_sha256": (
                "0042598bc0770e70bc4ea4b9c3d27d8efc8e395d6f766d41e939c746c2bd3046"
            ),
        }
        for phase in ("before", "after"):
            write(self.run / f"integrity-{phase}.json", guard)
            write(self.run / f"overlay-{phase}.json", overlay)
        shapes = [
            (name, sizes, m)
            for name, sizes in (
                ("mlp", [17408, 17408]),
                ("full_attention", [12288, 1024, 1024]),
                ("delta_net", [10240, 6144]),
            )
            for m in (1, 32)
        ] + [("mlp", [17408, 17408], 8192)]
        operators = []
        for name, sizes, m in shapes:
            backend = "flashinfer" if m < 32 else "deepgemm"
            operators.append(
                {
                    "group": name,
                    "shape": [m, 5120, sum(sizes)],
                    "parts": sizes,
                    "weight_and_scale_copy_exact": True,
                    "output_view_layout_valid": True,
                    "separate_vs_merged_diagnostics": [],
                    "selected_backend": backend,
                    "kernel_calls": {
                        "flashinfer": int(m < 32),
                        "deepgemm": int(m >= 32),
                        "triton": 0,
                    },
                    "changed_input_graph": [
                        {"input": kind, "exact": True, "finite": True}
                        for kind in ("zero", "new_random")
                    ],
                }
            )
        write(
            self.run / "operators.json",
            {
                "complete": True,
                "rows": operators,
                "observer_sha256": digest(self.component / "operator_probe.py"),
            },
        )
        loader = {
            "projection_layout": "merged",
            "fp8_linear_modules": 256,
            "dequantized": False,
            "backend": "flashinfer_small_m_deepgemm_prefill",
        }
        prewarm = {
            "policy": "full_context",
            "buckets": {"10240": {"capture_seconds": 1.0, "resident_MiB": 1.0}},
            "started_unix": 1.0,
            "completed_unix": 2.0,
            "total_seconds": 1.0,
            "resident_MiB_total": 1.0,
        }
        write(
            self.run / "graph.json",
            {
                "complete": True,
                "state_exact": True,
                "predictions": 16,
                "graph_replays": 15,
                "capacity": 10240,
                "projection_layout": "merged",
                "prefill_attention": "native",
                "loader": loader,
                "prewarm": prewarm,
                "rows": [
                    {"step": i, "exact": True, "finite": True, "max_abs": 0.0} for i in range(16)
                ],
            },
        )
        self.observations = [
            {
                "phase": "protocol",
                "mode": "paired",
                "projection_layout": "merged",
                "prefill_attention": "native",
                "observer_sha256": digest(self.component / "collect.py"),
                "client_sha256": "f31fae8c573ecc4bf8e31dae03823502e71404333e8111f4b535432758302b29",
                "source_hashes": {
                    k: v
                    for k, v in self.identities["source_files"].items()
                    if k.startswith("nanovllm/qwen38/") and k.endswith(".py")
                },
            }
        ]
        fp8 = {
            "modules": 256,
            "executed_modules": 256,
            "actual_dtypes_valid": True,
            "backend": "flashinfer_small_m_deepgemm_prefill",
            "kernel_calls": {"triton": 0, "flashinfer": 256, "deepgemm": 256},
        }
        origins = {}
        for name, checksum in self.identities["source_files"].items():
            if name.startswith("nanovllm/") and name.endswith(".py"):
                parts = list(Path(name).with_suffix("").parts)
                if parts[-1] == "__init__":
                    parts.pop()
                origins[".".join(parts)] = {
                    "path": str(self.run / "source" / name),
                    "sha256": checksum,
                }
        for rep in range(3):
            self.observations += [
                {
                    "phase": "ready",
                    "arm": "candidate",
                    "repetition": rep,
                    "loader_report": loader,
                    "graph_prewarm": prewarm,
                },
                {
                    "phase": "postflight",
                    "arm": "candidate",
                    "repetition": rep,
                    "fp8_execution": fp8,
                },
            ]
            write(
                self.run / f"http/candidate-r{rep}/candidate-health.private.json",
                {
                    "loader_report": loader,
                    "graph_prewarm": prewarm,
                    "fp8_execution": fp8,
                    "module_origins": origins,
                    "device_type": "cuda",
                    "device_count": 1,
                    "device_model": "NVIDIA H20",
                },
            )
        self.save_observations()
        self.raw_audit = {
            "raw_accounting_valid": True,
            "verdict": "INCONCLUSIVE",
            "measurements": [
                {
                    "arm": arm,
                    "repetition": rep,
                    "case": f"n8192-s{i}",
                    "input_tokens": 8192,
                    "output_tokens": 2048,
                    "ttft_s": 1.0,
                    "latency_s": 21.47,
                    "tpot_s": 0.01,
                }
                for arm in ("baseline", "candidate")
                for rep in range(3)
                for i in range(10)
            ],
        }
        write(self.run / "raw-audit.json", self.raw_audit)

    def save_observations(self):
        path = self.run / "http/observations.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in self.observations))

    def execute(self):
        with patch.object(binding, "audit", return_value=copy.deepcopy(self.raw_audit)) as audit:
            result = binding.bind(self.component, self.run, self.fixture, self.terminal, self.lock)
            self.assertEqual(audit.call_count, 1)
            return result

    def mutate_json(self, relative, callback):
        path = self.run / relative
        value = json.loads(path.read_bytes())
        callback(value)
        write(path, value)

    def test_valid_bound_shape_reaches_real_reducer_without_campaign_pass(self):
        result = self.execute()
        self.assertEqual(result["campaign_verdict"], "INCONCLUSIVE")
        self.assertEqual(len(result["rows"]), 60)
        self.assertTrue(all(row["valid"] is True for row in result["rows"]))
        self.assertEqual(
            {row["metric"] for row in result["statistics"]["metrics"]}, {"ttft_s", "tpot_s"}
        )

    def test_terminal_failed_wrong_job_restart_suspend_or_gpu_rejected(self):
        for old, new in (
            ("COMPLETED", "FAILED"),
            ("JobId=4242", "JobId=4243"),
            ("Restarts=0", "Restarts=1"),
            ("SuspendTime=None", "SuspendTime=date"),
            ("gres/gpu=1", "gres/gpu=2"),
            ("ExitCode=0:0", "ExitCode=0:9"),
        ):
            with self.subTest(old=old):
                with self.assertRaises((ValueError, KeyError)):
                    binding.check_terminal(self.good_terminal.replace(old, new), "4242")

    def test_terminal_duplicate_or_empty_fields_rejected(self):
        for prefix in ("JobState=FAILED ", "JobState= ", "JobId=wrong ", "ExitCode=0:9 "):
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValueError):
                    binding.check_terminal(prefix + self.good_terminal, "4242")

    def test_duplicate_json_key_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text('{"complete":false,"complete":true}')
        with self.assertRaises(ValueError):
            binding.read(path)

    def test_runtime_postflight_or_archive_identity_rejected(self):
        self.mutate_json("integrity-after.json", lambda value: value.update(python="wrong"))
        with self.assertRaises(ValueError):
            self.execute()

    def test_component_byte_change_rejected(self):
        with (self.component / "operator_probe.py").open("a") as handle:
            handle.write("\n# changed\n")
        with self.assertRaises(ValueError):
            self.execute()

    def test_missing_postflight_rejected(self):
        (self.run / "postflight-status.tsv").write_text("model_runtime\t0\n")
        with self.assertRaises(ValueError):
            self.execute()

    def test_bad_actual_module_hash_rejected(self):
        self.mutate_json(
            "http/candidate-r1/candidate-health.private.json",
            lambda value: value["module_origins"]["nanovllm.qwen38.model"].update(sha256="0" * 64),
        )
        with self.assertRaises(ValueError):
            self.execute()

    def test_missing_actual_health_rejected(self):
        (self.run / "http/candidate-r1/candidate-health.private.json").unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.execute()

    def test_actual_http_graph_disabled_rejected(self):
        self.mutate_json(
            "http/candidate-r1/candidate-health.private.json",
            lambda value: value.update(graph_prewarm={}),
        )
        with self.assertRaises(ValueError):
            self.execute()

    def test_ready_graph_wrong_policy_rejected(self):
        self.observations[1] = copy.deepcopy(self.observations[1])
        self.observations[1]["graph_prewarm"]["policy"] = "buckets"
        self.save_observations()
        with self.assertRaises(ValueError):
            self.execute()

    def test_operator_partial_or_wrong_backend_rejected(self):
        self.mutate_json(
            "operators.json", lambda value: value["rows"][0].update(selected_backend="triton")
        )
        with self.assertRaises(ValueError):
            self.execute()

    def test_operator_changed_input_mismatch_rejected(self):
        self.mutate_json(
            "operators.json",
            lambda value: value["rows"][0]["changed_input_graph"][0].update(exact=False),
        )
        with self.assertRaises(ValueError):
            self.execute()

    def test_saved_raw_audit_disagreement_rejected(self):
        self.mutate_json("raw-audit.json", lambda value: value.update(raw_accounting_valid=False))
        with self.assertRaises(ValueError):
            self.execute()

    def test_frozen_observer_identity_mismatch_rejected(self):
        self.observations[0]["observer_sha256"] = "0" * 64
        self.save_observations()
        with self.assertRaises(ValueError):
            self.execute()

    def test_changed_operator_overlay_rejected(self):
        self.mutate_json("overlay-after.json", lambda value: value.update(files_verified=898))
        with self.assertRaises(ValueError):
            self.execute()


if __name__ == "__main__":
    unittest.main()
