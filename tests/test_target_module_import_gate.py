"""Guard new Knowledge / Harness / Benchmark / Apps import edges.

A passing scan is not module isolation. The target packages are not all
present, and the existing ``inferrsi.harness`` tree still mixes other layers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from tests import _gate_policy_support as support
from tests._gate_policy_support import (
    NEW_CORES,
    ROOT,
    blocker_kinds,
    cross_core_violations,
    exact_pairs,
    first_wave_report,
    load_manifest,
)


@pytest.mark.parametrize("extra", [
    "\nimport importlib\nimportlib.import_module('inferrsi.knowledge')\n",
    "\nimportlib.util.module_from_spec(spec)\n",
    "\ndef another():\n    return importlib.util.module_from_spec(spec)\n",
])
def test_declared_resource_loader_does_not_allow_an_extra_dynamic_edge(tmp_path, extra):
    task = tmp_path / "harness/task_protocol.py"
    task.parent.mkdir()
    source = ("import importlib.util\ndef protocol():\n"
              "    return importlib.util.module_from_spec(spec)\n")
    task.write_text(source, encoding="utf-8")
    report = first_wave_report(tmp_path)
    assert not report.violations
    assert "runtime resource loaders" in blocker_kinds(report)
    assert not report.isolation_complete
    task.write_text(source + extra, encoding="utf-8")
    assert any("dynamic import" in item for item in first_wave_report(tmp_path).violations)


def test_resource_loader_declaration_does_not_cover_an_adjacent_module(tmp_path):
    task = tmp_path / "harness/other_protocol.py"
    task.parent.mkdir()
    task.write_text(
        "import importlib.util\ndef protocol():\n"
        "    return importlib.util.module_from_spec(spec)\n",
        encoding="utf-8",
    )
    assert any("dynamic import" in item for item in first_wave_report(tmp_path).violations)


class TargetModuleImportGateTest(unittest.TestCase):
    def test_no_new_cross_core_imports(self) -> None:
        # #412 R1: nothing is allowlisted any more, and the tree is still clean.
        allowed = exact_pairs(load_manifest())
        self.assertEqual(allowed, frozenset())
        self.assertEqual(cross_core_violations(allowed=allowed), [])
        self.assertFalse(hasattr(support, "LEGACY_RUN_FORWARDERS"))
        # The root CLI parser now names Knowledge itself. Its exact application-entry
        # listing is what admits that, and each listed file exists in the root, so an
        # entry cannot outlive the file that A1 or A2 removes.
        self.assertEqual(
            support.APPLICATION_ENTRIES, ("cli.py", "arguments.py", "benchmark_operations.py")
        )
        for entry in support.APPLICATION_ENTRIES:
            self.assertTrue((ROOT / entry).is_file(), entry)
        with mock.patch.object(
            support, "APPLICATION_ENTRIES", ("cli.py", "benchmark_operations.py")
        ):
            self.assertEqual(cross_core_violations(), ["arguments.py imports inferrsi.knowledge"])

    def test_first_wave_policy_holds_on_current_tree(self) -> None:
        self.assertEqual(first_wave_report().violations, ())

    def test_clean_scan_is_not_isolation(self) -> None:
        # Facts that hold at every stage.
        self.assertTrue((ROOT / "benchmark" / "registry.py").is_file())
        self.assertTrue((ROOT / "harness").is_dir())
        # #451 C1, C2: the shared data/byte contracts are one bounded package with exactly
        # these files. The single-file re-export and its three root siblings are retired.
        self.assertEqual(
            sorted(path.name for path in (ROOT / "contracts").iterdir() if path.is_file()),
            ["__init__.py", "claim.py", "evidence.py", "json_v1.py", "runspec.py"],
        )
        for retired in ("contracts.py", "_json_v1.py", "runspec.py", "claim.py",
                        "_repo_pack_data.py", "evidence_paths.py"):
            self.assertFalse((ROOT / retired).exists(), retired)
        # #412 R1: the eleven retired root modules are gone, with no package in their place.
        self.assertEqual(len(support.RETIRED_ROOT_MODULES), 11)
        for module in support.RETIRED_ROOT_MODULES:
            name = module.removeprefix("inferrsi.")
            self.assertFalse((ROOT / f"{name}.py").exists(), name)
            self.assertFalse((ROOT / name).exists(), name)
        self.assertTrue((ROOT / "apps" / "inspection.py").is_file())
        self.assertEqual(
            support.CONTRACTS_MODULES,
            {
                "inferrsi.contracts",
                "inferrsi.contracts.claim",
                "inferrsi.contracts.evidence",
                "inferrsi.contracts.json_v1",
                "inferrsi.contracts.runspec",
            },
        )
        # #451 C2: the neutral leaf package holds the import-free initializer and the
        # leaf. Directory creation is an Apps module, outside the contracts set.
        self.assertEqual(
            sorted(path.name for path in (ROOT / "resources").iterdir() if path.is_file()),
            ["__init__.py", "repository_packs.py"],
        )
        self.assertTrue((ROOT / "apps" / "evidence_layout.py").is_file())
        # A01-4 staged model: packages may appear one at a time, but each
        # remaining trigger keeps overall false.
        report = first_wave_report()
        self.assertFalse(report.isolation_complete)
        for name in NEW_CORES:
            absent = not (ROOT / name).is_dir()
            self.assertEqual(f"absent: {name}/" in report.blockers, absent)
            self.assertNotIn(f"unscannable: {name}/", report.blockers)
        kinds = blocker_kinds(report)
        # #412 R1: the allowlist is empty and no old-run forwarder is registered.
        self.assertNotIn("allowlist", kinds)
        self.assertNotIn("legacy run forwarders", kinds)
        # No residual: the gate registers no exempt edge, and the scan above
        # already fails any harness module that reaches an old root leaf.
        self.assertFalse(hasattr(support, "REGISTERED_RESIDUALS"))
        self.assertFalse(hasattr(report, "residuals"))
        self.assertNotIn("residual", kinds)
        self.assertEqual(report.violations, ())
        # What keeps isolation false after R1: the parser entry due in A1, the six
        # Harness modules that R2 closes and the five loaders that R3 closes.
        self.assertEqual(
            report.blockers,
            (
                "temporary leaf importers: 1",
                "harness reaches model/infra: inferrsi.harness.agent_sessions -> "
                "inferrsi.infra (12 hits)",
                "runtime resource loaders: 5",
            ),
        )
        self.assertEqual(len(report.harness_model_infra), 12)
        self.assertFalse(report.new_core_closure_isolated)

    def test_split_skill_eval_modules_reach_no_model_or_infra(self) -> None:
        # S01: the split Harness modules own their writes and digests. The
        # remaining harness -> model/infra hits belong to other modules.
        report = first_wave_report()
        for name in (
            "skill_evaluation",
            "improvement",
            "artifact_sandbox",
            "atomic_json",
        ):
            with self.subTest(module=name):
                self.assertTrue((ROOT / "harness" / f"{name}.py").is_file())
                self.assertEqual(
                    [
                        path
                        for path in report.harness_model_infra
                        if path.startswith(f"inferrsi.harness.{name} -> ")
                    ],
                    [],
                )
        for name in ("skill_eval_diagnostic", "skill_eval_engineering"):
            self.assertFalse((ROOT / "harness" / f"{name}.py").exists())

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
                "benchmark/forbidden.py": "import inferrsi.harness\n",
                "cli.py": "from inferrsi.benchmark.registry import builtin_tasks\n",
                "arguments.py": "from inferrsi.knowledge import catalog\n",
                # The listing is the exact file name: a module beside it gains nothing.
                "arguments_extra.py": "from inferrsi.knowledge import catalog\n",
                "benchmark_operations.py": "import inferrsi.benchmark\n",
                "unowned.py": "import inferrsi.benchmark\n",
            }
            for relative, source in samples.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            violations = cross_core_violations(root)
        self.assertEqual(
            violations,
            [
                "arguments_extra.py imports inferrsi.knowledge",
                "benchmark/forbidden.py imports inferrsi.harness",
                "harness/probe.py imports inferrsi.knowledge",
                "knowledge/out.py imports inferrsi.harness",
                "unowned.py imports inferrsi.benchmark",
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
