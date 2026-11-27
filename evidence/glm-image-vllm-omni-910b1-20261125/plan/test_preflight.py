"""CPU-only regressions for replaying the wrong candidate or a dirty snapshot."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from preflight import check_source, check_sources

from inferrsi.harness.candidates import identity


class ReplayInputs(unittest.TestCase):
    def test_same_tree(self):
        with tempfile.TemporaryDirectory() as where:
            tree = Path(where)
            with self.assertRaisesRegex(ValueError, "same tree"):
                check_sources(tree, tree / ".", {}, "")

    def test_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as where:
            tree = Path(where)
            source = tree / "vllm_omni"
            source.mkdir()
            module = source / "model.py"
            module.write_text("value = 1\n")
            subprocess.run(["git", "init", "-q", where], check=True)
            subprocess.run(["git", "-C", where, "add", "vllm_omni"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    where,
                    "-c",
                    "user.name=test",
                    "-c",
                    "user.email=test@example.org",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                check=True,
            )
            head = subprocess.check_output(
                ["git", "-C", where, "rev-parse", "HEAD"], text=True
            ).strip()
            expected = identity(tree, ["vllm_omni"])
            check_source(tree, head, expected, "Candidate")
            module.write_text("value = 2\n")
            with self.assertRaisesRegex(ValueError, "Candidate vllm_omni"):
                check_source(tree, head, expected, "Candidate")


if __name__ == "__main__":
    unittest.main()
