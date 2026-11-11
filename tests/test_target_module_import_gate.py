"""Guard new Knowledge / Harness / Benchmark / Apps import edges.

A passing scan is not module isolation. The target packages are not all
present, and the existing ``inferrsi.harness`` tree still mixes other layers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._gate_policy_support import (
    NEW_CORES,
    ROOT,
    blocker_kinds,
    cross_core_violations,
    exact_pairs,
    first_wave_report,
    load_manifest,
)


class TargetModuleImportGateTest(unittest.TestCase):
    def test_no_new_cross_core_imports(self) -> None:
        self.assertEqual(cross_core_violations(allowed=exact_pairs(load_manifest())), [])

    def test_first_wave_policy_holds_on_current_tree(self) -> None:
        self.assertEqual(first_wave_report().violations, ())

    def test_clean_scan_is_not_isolation(self) -> None:
        # Facts that hold at every stage.
        self.assertTrue((ROOT / "harness").is_dir())
        self.assertTrue((ROOT / "contracts.py").is_file())
        self.assertFalse((ROOT / "contracts").is_dir())
        # A01-4 staged model: packages may appear one at a time, but each
        # remaining trigger keeps overall false.
        report = first_wave_report()
        self.assertFalse(report.isolation_complete)
        for name in NEW_CORES:
            absent = not (ROOT / name).is_dir()
            self.assertEqual(f"absent: {name}/" in report.blockers, absent)
            self.assertNotIn(f"unscannable: {name}/", report.blockers)
        kinds = blocker_kinds(report)
        self.assertIn("allowlist", kinds)
        self.assertEqual(
            report.residuals,
            ("inferrsi.harness.skill_evaluation -> inferrsi.knowledge_operations",),
        )
        self.assertIn("residual", kinds)
        self.assertIn("harness reaches model/infra", kinds)

    def test_real_tree_allows_apps_and_same_core_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples = {
                "harness/probe.py": "from inferrsi import knowledge\n",
                "apps/probe.py": "import inferrsi.knowledge\n",
                "knowledge/bar.py": "VALUE = 1\n",
                "knowledge/foo.py": "from .bar import VALUE\n",
                "knowledge/out.py": "import inferrsi.harness\n",
                "benchmark/edge.py": "from inferrsi.benchmark import edge\n",
            }
            for relative, source in samples.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            violations = cross_core_violations(root)
        self.assertEqual(
            violations,
            [
                "harness/probe.py imports inferrsi.knowledge",
                "knowledge/out.py imports inferrsi.harness",
            ],
        )

    def test_layout_doc_states_the_same_limit(self) -> None:
        text = (
            Path(__file__).resolve().parents[1] / "docs" / "module-layout.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Isolation stays false", text)
        self.assertIn("Same-core imports are allowed", text)


if __name__ == "__main__":
    unittest.main()
