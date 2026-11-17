"""Guard new Knowledge / Harness / Benchmark / Apps import edges.

A passing scan is not module isolation. The target packages are not all
present, and the existing ``inferrsi.harness`` tree still mixes other layers.
"""

from __future__ import annotations

import ast
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


def _scan_tree(files: dict[str, str]) -> list[str]:
    """Cross-core violations of a synthetic package root holding only ``files``."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for relative, source in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        return cross_core_violations(root)


class TargetModuleImportGateTest(unittest.TestCase):
    def test_no_new_cross_core_imports(self) -> None:
        # #412 R1: nothing is allowlisted any more, and the tree is still clean.
        allowed = exact_pairs(load_manifest())
        self.assertEqual(allowed, frozenset())
        self.assertEqual(cross_core_violations(allowed=allowed), [])
        self.assertFalse(hasattr(support, "LEGACY_RUN_FORWARDERS"))
        # #408 A1 and A2: the CLI, its parser and the task launcher are under apps/, Apps by
        # first path segment. With the last move the exact flat-entry listing is gone, so no
        # root file is read as Apps and none of the old root files exists.
        self.assertFalse(hasattr(support, "APPLICATION_ENTRIES"))
        for retired in ("cli.py", "arguments.py", "benchmark_operations.py", "summary_chart.py"):
            self.assertFalse((ROOT / retired).exists(), retired)
        for moved in ("cli/__init__.py", "cli/arguments.py", "benchmark_operations.py",
                      "views/summary_chart.py"):
            self.assertTrue((ROOT / "apps" / moved).is_file(), moved)

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
        # #408 A1 and A2 each retired two more.
        self.assertEqual(len(support.RETIRED_BY_R1), 11)
        self.assertEqual(support.RETIRED_BY_A1, {"inferrsi.cli", "inferrsi.arguments"})
        self.assertEqual(
            support.RETIRED_BY_A2, {"inferrsi.summary_chart", "inferrsi.benchmark_operations"}
        )
        self.assertEqual(len(support.RETIRED_ROOT_MODULES), 15)
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
        # #412 R2 closed the six Harness modules: no Harness module reaches the
        # package-level ``inferrsi.infra``, ``inferrsi.infra.artifacts`` or
        # ``inferrsi.model``. What keeps isolation false is the five loaders that R3 closes.
        self.assertEqual(report.blockers, ("runtime resource loaders: 5",))
        self.assertEqual(report.harness_model_infra, ())
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
                # #408 A1: the CLI package is Apps by path. A root file that returns
                # under either old name is unlisted and fails like any other flat module.
                "apps/cli/__init__.py": "from inferrsi.benchmark.registry import builtin_tasks\n",
                "apps/cli/arguments.py": "from inferrsi.knowledge import catalog\n",
                "cli.py": "from inferrsi.apps.cli import main\n",
                "arguments.py": "from inferrsi.knowledge import catalog\n",
                # No root file is listed, so a module beside an old name gains nothing.
                "arguments_extra.py": "from inferrsi.knowledge import catalog\n",
                # #408 A2: the task launcher is Apps by path too. The root file that held
                # it is no longer an application entry and fails like the others.
                "apps/benchmark_operations.py": "import inferrsi.benchmark\n",
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
                "arguments.py imports inferrsi.knowledge",
                "arguments_extra.py imports inferrsi.knowledge",
                "benchmark/forbidden.py imports inferrsi.harness",
                "benchmark_operations.py imports inferrsi.benchmark",
                "cli.py imports inferrsi.apps",
                "harness/probe.py imports inferrsi.knowledge",
                "knowledge/out.py imports inferrsi.harness",
                "unowned.py imports inferrsi.benchmark",
            ],
        )

    def test_module_entry_admits_only_the_canonical_cli_delegation(self) -> None:
        # #408 A1: ``python -m inferrsi`` runs root ``__main__.py``, which must stay in the
        # root. The real file is the hand-over to the Apps CLI and nothing else.
        entry = (ROOT / support.MODULE_ENTRY).read_text(encoding="utf-8")
        self.assertEqual(
            [ast.unparse(node) for node in ast.parse(entry).body],
            ["from .apps.cli import main", "raise SystemExit(main())"],
        )
        self.assertEqual(support.MODULE_ENTRY, "__main__.py")
        self.assertEqual(support.MODULE_ENTRY_DELEGATION, ("inferrsi.apps.cli", "main"))
        # It passes by its own exact rule; since A2 no root file is an application entry.
        self.assertFalse(hasattr(support, "APPLICATION_ENTRIES"))
        self.assertEqual(_scan_tree({"__main__.py": entry}), [])
        self.assertEqual(_scan_tree({"__main__.py": "from inferrsi.apps.cli import main\n"}), [])
        # Positive control: without the rule the same file is refused, so the statement
        # passes by the rule and not by an erased scan.
        refused = ["__main__.py imports inferrsi.apps"]
        with mock.patch.object(support, "MODULE_ENTRY", "elsewhere.py"):
            self.assertEqual(_scan_tree({"__main__.py": entry}), refused)
        with mock.patch.object(support, "MODULE_ENTRY_DELEGATION", ("inferrsi.apps.cli", "run")):
            self.assertEqual(_scan_tree({"__main__.py": entry}), refused)
        with mock.patch.object(support, "MODULE_ENTRY_DELEGATION", ("inferrsi.apps", "cli")):
            self.assertEqual(_scan_tree({"__main__.py": entry}), refused)
        # The staged report carries the same result: the delegation adds no violation,
        # and another shape is a violation that keeps isolation false.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "__main__.py").write_text(entry, encoding="utf-8")
            self.assertEqual(first_wave_report(root).violations, ())
            (root / "__main__.py").write_text("from .apps import cli\n", encoding="utf-8")
            report = first_wave_report(root)
            self.assertEqual(report.violations, tuple(refused))
            self.assertFalse(report.isolation_complete)

    def test_module_entry_rule_covers_no_other_shape_target_or_file(self) -> None:
        line = "from .apps.cli import main\n"
        cases = (
            # Another name, a second name, an alias or a star import from the target.
            ("from .apps.cli import parser\n", "apps"),
            ("from .apps.cli import main, parser\n", "apps"),
            ("from .apps.cli import main as run\n", "apps"),
            ("from .apps.cli import main as main\n", "apps"),
            ("from .apps.cli import *\n", "apps"),
            # The target as a module object, and the Apps package itself.
            ("from .apps import cli\n", "apps"),
            ("import inferrsi.apps.cli\n", "apps"),
            ("import inferrsi.apps.cli as entry\n", "apps"),
            ("import inferrsi.apps\n", "apps"),
            ("from .apps import main\n", "apps"),
            # A module below the target, a module beside it and a lookalike of it.
            ("from .apps.cli.arguments import parser\n", "apps"),
            ("from .apps.cli import arguments\n", "apps"),
            ("from .apps.cli.main import main\n", "apps"),
            ("from .apps.cli_extra import main\n", "apps"),
            ("from .apps.inspection import main\n", "apps"),
            ("from .apps.legacy.run import main\n", "apps"),
            # The same line below module level, an import fallback included.
            ("def run():\n    from .apps.cli import main\n    return main()\n", "apps"),
            ("if True:\n    from .apps.cli import main\n", "apps"),
            (
                "try:\n    from .apps.cli import main\nexcept ImportError:\n    main = None\n",
                "apps",
            ),
            # Beside the admitted line every other core import still fails.
            (line + "from .apps.views import dashboard\n", "apps"),
            (line + "from .apps.cli.arguments import parser\n", "apps"),
            (line + "from .apps.cli import main as run\n", "apps"),
            (line + "from .knowledge.catalog import BACKENDS\n", "knowledge"),
            (line + "import inferrsi.benchmark\n", "benchmark"),
            (line + "def late():\n    from inferrsi.knowledge import catalog\n", "knowledge"),
            # The same name in another core is not the target.
            ("from .knowledge.cli import main\n", "knowledge"),
            ("from .benchmark.cli import main\n", "benchmark"),
        )
        for source, core in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    _scan_tree({"__main__.py": source}), [f"__main__.py imports inferrsi.{core}"]
                )
        # No other file is the module entry. A root file beside it, a returning root CLI
        # shell and a ``__main__`` under any package fail with the very same statement.
        absolute = "from inferrsi.apps.cli import main\n"
        others = (
            "main.py", "__main__extra.py", "_main.py", "cli.py", "arguments.py", "helper.py",
            "harness/__main__.py", "knowledge/__main__.py", "benchmark/__main__.py",
            "model/__main__.py", "infra/__main__.py", "resources/__main__.py",
        )
        for path in others:
            with self.subTest(path=path):
                self.assertEqual(_scan_tree({path: absolute}), [f"{path} imports inferrsi.apps"])
        # All of them at once, with the real entry beside them: only the entry passes.
        entry = (ROOT / support.MODULE_ENTRY).read_text(encoding="utf-8")
        together = {path: absolute for path in others}
        self.assertEqual(
            _scan_tree({"__main__.py": entry, **together}),
            sorted(f"{path} imports inferrsi.apps" for path in others),
        )
        # Apps itself never needed the rule.
        self.assertEqual(_scan_tree({"apps/__main__.py": absolute}), [])

    def test_layout_doc_states_the_same_limit(self) -> None:
        text = (
            Path(__file__).resolve().parents[1] / "docs" / "module-layout.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Isolation stays false", text)
        self.assertIn("Same-core imports are allowed", text)


if __name__ == "__main__":
    unittest.main()
