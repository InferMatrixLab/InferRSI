"""Finite service/sender lifecycle controls; no GPU, evaluator or model outputs."""

import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_quality as collect  # noqa: E402


class QualityCollection(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ("source", "prepared", "tokens", "model"):
            (self.root / name).mkdir()
        self.args = types.SimpleNamespace(
            source=self.root / "source",
            prepared=self.root / "prepared",
            tokenized=self.root / "tokens",
            model=self.root / "model",
            manifest=self.root / "source-manifest.json",
            output=self.root / "out",
            retrieval_fixture=self.root / "retrieval.jsonl",
        )
        (self.args.source / "run.py").write_text("# finite source fixture\n")
        (self.args.prepared / "cohorts.json").write_text("{}\n")
        (self.args.prepared / "prepared.json").write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": "cohorts.json",
                            "sha256": collect.sha(self.args.prepared / "cohorts.json"),
                        }
                    ]
                }
            )
        )
        (self.args.tokenized / "tokens.jsonl").write_text("{}\n")
        (self.args.tokenized / "tokenized.json").write_text(
            json.dumps(
                {
                    "prepared_sha256": collect.sha(self.args.prepared / "prepared.json"),
                    "tokens_sha256": collect.sha(self.args.tokenized / "tokens.jsonl"),
                    "thinking": False,
                }
            )
        )
        self.manifest = {
            "files": {"run.py": collect.sha(self.args.source / "run.py")},
            "prepared_sha256": collect.sha(self.args.prepared / "prepared.json"),
            "tokenized_sha256": collect.sha(self.args.tokenized / "tokenized.json"),
            "generation_config_sha256": "1" * 64,
        }
        self.args.manifest.write_text(json.dumps(self.manifest))
        self.args.manifest_sha256 = collect.sha(self.args.manifest)
        self.argv = ["collect_quality.py"]
        for name in ("source", "prepared", "tokenized", "model", "manifest", "output"):
            self.argv += ["--" + name, str(getattr(self.args, name))]
        self.argv += ["--retrieval-fixture", str(self.args.retrieval_fixture)]
        self.argv += ["--manifest-sha256", self.args.manifest_sha256, "--phase", "final"]
        self.cleanup = {
            "cleanup_complete": True,
            "forced": False,
            "exit_code": 0,
            "owned_group_remaining": 0,
            "cleanup_errors": [],
        }

    def test_actual_input_guards(self):
        self.assertEqual(collect.verify(self.args), self.manifest)
        for path in (
            self.args.manifest,
            self.args.source / "run.py",
            self.args.prepared / "cohorts.json",
            self.args.tokenized / "tokens.jsonl",
        ):
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaises(ValueError):
                collect.verify(self.args)
            path.write_bytes(original)

    def exercise(self, sender, cleanup=None, dead=False):
        process = MagicMock()
        process.poll.return_value = 1 if dead else None
        health = MagicMock()
        health.__enter__.return_value.status = 200
        observed = {"argv": []}

        def run_sender(*args, **kwargs):
            observed["argv"].append(copy.deepcopy(sys.argv))
            raise sender

        with (
            patch.object(sys, "argv", self.argv.copy()),
            patch.object(collect.signal, "signal"),
            patch.object(collect.subprocess, "Popen", return_value=process) as launch,
            patch.object(collect.urllib.request, "urlopen", return_value=health),
            patch.object(collect.runpy, "run_path", side_effect=run_sender),
            patch.object(collect, "terminate_owned", return_value=cleanup or self.cleanup) as stop,
            patch.dict(
                collect.os.environ,
                {"PYTHONHOME": "/untrusted", "VLLM_USE_V1": "0", "NANOVLLM_GDN": "native"},
            ),
        ):
            try:
                collect.main()
            finally:
                self.assertEqual(stop.call_count, 1)
                command = launch.call_args.args[0]
                env = launch.call_args.kwargs["env"]
                self.assertEqual(command[1], "-IBu")
                self.assertNotIn("PYTHONHOME", env)
                self.assertNotIn("VLLM_USE_V1", env)
                self.assertNotIn("NANOVLLM_GDN", env)
        return observed

    def test_success_uses_fixed_final_sender(self):
        result = self.exercise(SystemExit(0))
        self.assertEqual(len(result["argv"]), 2)
        self.assertTrue(result["argv"][1][0].endswith("run_retrieval.py"))
        self.assertIn(str(self.args.retrieval_fixture), result["argv"][1])
        self.assertIn("final", result["argv"][0])
        self.assertIn("1800", result["argv"][0])
        self.assertIn("baseline", result["argv"][0])
        self.assertTrue((self.args.output / "sender-complete.json").exists())
        self.assertEqual(json.loads((self.args.output / "cleanup.json").read_text()), self.cleanup)

    def test_sender_failure_keeps_cleanup_without_completion(self):
        with self.assertRaises(RuntimeError):
            self.exercise(SystemExit(2))
        self.assertFalse((self.args.output / "sender-complete.json").exists())
        self.assertTrue((self.args.output / "cleanup.json").exists())

    def test_cancellation_keeps_cleanup(self):
        with self.assertRaises(KeyboardInterrupt):
            self.exercise(KeyboardInterrupt())
        self.assertFalse((self.args.output / "sender-complete.json").exists())
        self.assertTrue((self.args.output / "cleanup.json").exists())

    def test_dead_startup_still_cleans(self):
        with self.assertRaises(RuntimeError):
            self.exercise(SystemExit(0), dead=True)

    def test_failed_cleanup_rejects_successful_sender(self):
        with self.assertRaises(RuntimeError):
            self.exercise(SystemExit(0), cleanup={**self.cleanup, "forced": True})


if __name__ == "__main__":
    unittest.main()
