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

# #412 R3: a by-path load, as in the MoE grader and the Qwen21 evaluator.
LOADER = (
    "import importlib.util\n"
    "def load(path, name):\n"
    "    spec = importlib.util.spec_from_file_location(name, path)\n"
    "    module = importlib.util.module_from_spec(spec)\n"
    "    spec.loader.exec_module(module)\n"
    "    return module\n"
)


def _report(root, files):
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return first_wave_report(root)


def _module(relative):
    return "inferrsi." + relative.removesuffix(".py").replace("/", ".")


def test_retired_loader_tables_do_not_return():
    # R3 admits by file location, so no table names a task, a function or a module.
    for name in ("RESOURCE_LOADERS", "EVALUATOR_LOADERS"):
        assert not hasattr(support, name), name


@pytest.mark.parametrize("relative", [
    "benchmark/tasks/moe-forward-npu/grader.py",
    # Any bundle and any file name: nothing in the gate names a task.
    "benchmark/tasks/a-new-task/evaluate.py",
])
def test_bundle_program_may_load_files_by_path_and_is_listed(tmp_path, relative):
    module_scope = ("import importlib.util\n"
                    "spec = importlib.util.spec_from_file_location('c', 'c.py')\n"
                    "module = importlib.util.module_from_spec(spec)\n")
    two_calls = LOADER + "\nload('a.py', 'a')\nother = importlib.util.module_from_spec(spec)\n"
    for index, source in enumerate((LOADER, two_calls, module_scope)):
        report = _report(tmp_path / str(index), {relative: source})
        # The synthetic tree lacks the other cores, so only their "absent" blockers remain.
        assert report.violations == ()
        assert blocker_kinds(report) == {"absent"}
        assert report.runtime_execution == (
            f"{_module(relative)}: importlib.util.module_from_spec executes files loaded "
            "by path in-process",)


@pytest.mark.parametrize("extra", [
    "\nimport importlib\nimportlib.import_module('inferrsi.knowledge')\n",
    "\n__import__('json')\n",
    "\nfrom importlib.util import module_from_spec\n",
    "\nimport importlib.util as util\nutil.module_from_spec(spec)\n",
    "\nimportlib.util.find_spec('inferrsi.knowledge')\n",
    "\nfrom importlib.util import find_spec\nfind_spec('inferrsi.knowledge')\n",
    # Review of 2d0fa29: aliases of find_spec are the same name-based lookup.
    "\nfrom importlib.util import find_spec as resolve\n"
    "spec = resolve('inferrsi.knowledge')\nmodule = importlib.util.module_from_spec(spec)\n",
    "\nimport importlib.util as util\nutil.find_spec('inferrsi.knowledge')\n",
    "\nimport importlib.machinery\nimportlib.machinery.PathFinder.find_spec('inferrsi')\n",
])
def test_bundle_program_name_based_lookups_still_fail(tmp_path, extra):
    report = _report(tmp_path, {"benchmark/tasks/moe-forward-npu/grader.py": LOADER + extra})
    assert any("dynamic import" in item for item in report.violations)
    assert not report.isolation_complete


@pytest.mark.parametrize("importer, source", [
    # Review of 2d0fa29: without __init__.py a bundle is still a namespace package, so
    # an identifier-named bundle program is importable. The gate rejects that import.
    ("benchmark/runner.py", "from inferrsi.benchmark.tasks.new_task import evaluate\n"),
    ("benchmark/runner.py", "import inferrsi.benchmark.tasks.new_task.evaluate\n"),
    ("benchmark/runner.py", "from .tasks.new_task import evaluate\n"),
    ("apps/runner.py", "from inferrsi.benchmark.tasks.new_task import evaluate\n"),
    ("benchmark/tasks/other_task/evaluate.py",
     "from inferrsi.benchmark.tasks.new_task import evaluate\n"),
])
def test_package_code_may_not_import_a_bundle_program(tmp_path, importer, source):
    target = "inferrsi.benchmark.tasks.new_task.evaluate"
    report = _report(tmp_path, {"benchmark/tasks/new_task/evaluate.py": LOADER,
                                importer: source})
    assert f"{_module(importer)} imports task bundle program {target}" in report.violations
    assert not report.isolation_complete


def test_bundle_program_static_cross_core_import_still_fails(tmp_path):
    report = _report(tmp_path, {
        "knowledge/catalog.py": "VALUE = 1\n",
        "benchmark/tasks/moe-forward-npu/grader.py": LOADER + "from inferrsi.knowledge "
                                                     "import catalog\n"})
    assert any("imports inferrsi.knowledge" in item for item in report.violations)


def test_a_finder_class_in_a_bundle_program_is_not_a_lookup(tmp_path):
    # The Qwen21 and TTS import guards define a find_spec method; defining it is not a call.
    guard = ("import importlib.util\nclass Guard:\n"
             "    def find_spec(self, fullname, path=None, target=None):\n"
             "        return importlib.util.spec_from_loader(fullname, self)\n")
    report = _report(tmp_path, {"benchmark/tasks/qwen3-tts-npu/baseline.py": guard})
    assert report.violations == () and report.runtime_execution == ()


@pytest.mark.parametrize("files", [
    # The bundle directory becomes an importable package.
    {"benchmark/tasks/moe-forward-npu/__init__.py": ""},
    # tasks itself does not make a bundle program out of a deeper file.
    {"benchmark/tasks/moe-forward-npu/sub/grader.py": LOADER},
])
def test_only_files_directly_in_a_non_package_bundle_are_bundle_programs(tmp_path, files):
    report = _report(tmp_path, {"benchmark/tasks/moe-forward-npu/grader.py": LOADER, **files})
    assert any("dynamic import" in item for item in report.violations)


@pytest.mark.parametrize("relative", [
    "benchmark/registry.py",
    "benchmark/tasks.py",
    # The Harness protocol loader that R3 retired, and its neighbours.
    "harness/task_protocol.py",
    "harness/other_protocol.py",
    "apps/benchmark_operations.py",
    "knowledge/data/skills/scripts/loader.py",
])
def test_by_path_loading_is_admitted_nowhere_else(tmp_path, relative):
    report = _report(tmp_path, {relative: LOADER})
    assert any("dynamic import" in item for item in report.violations)
    assert report.runtime_execution == ()


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
        # #408 A1 and A2 and #452 M1: the CLI, its parser, the task launcher and the MindIE
        # adapter are under apps/, Apps by first path segment. With the A2 move the exact
        # flat-entry listing is gone, so no root file is read as Apps and none of the old
        # root files exists.
        self.assertFalse(hasattr(support, "APPLICATION_ENTRIES"))
        for retired in ("cli.py", "arguments.py", "benchmark_operations.py", "summary_chart.py",
                        "mindie_project.py", "mindie_context.py", "mindie_mcp.py",
                        "_mindie_read_worker.py"):
            self.assertFalse((ROOT / retired).exists(), retired)
        for moved in ("cli/__init__.py", "cli/arguments.py", "benchmark_operations.py",
                      "views/summary_chart.py", "mindie/project.py", "mindie/context.py",
                      "mindie/mcp.py", "mindie/read_worker.py"):
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
        # #408 A1 and A2 each retired two more, and #452 M1 retired four.
        self.assertEqual(len(support.RETIRED_BY_R1), 11)
        self.assertEqual(support.RETIRED_BY_A1, {"inferrsi.cli", "inferrsi.arguments"})
        self.assertEqual(
            support.RETIRED_BY_A2, {"inferrsi.summary_chart", "inferrsi.benchmark_operations"}
        )
        self.assertEqual(len(support.RETIRED_BY_M1), 4)
        self.assertEqual(len(support.RETIRED_ROOT_MODULES), 19)
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
        # #412 R3: every staged trigger is gone, so the final tree is fully isolated in
        # the static import-closure sense.
        report = first_wave_report()
        for name in NEW_CORES:
            self.assertTrue((ROOT / name).is_dir())
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
        # R2 closed the Harness -> Infra/Model edges; R3 retired the five temporary
        # resource loaders and their blocker.
        self.assertFalse(hasattr(support, "RESOURCE_LOADERS"))
        self.assertEqual(report.harness_model_infra, ())
        self.assertEqual(report.blockers, ())
        self.assertTrue(report.new_core_closure_isolated)
        self.assertTrue(report.isolation_complete)
        # Static closure is not runtime isolation: the two evaluators that time submitted
        # code still load frozen run files by path in-process, and the report says so.
        self.assertEqual(report.runtime_execution, (
            "inferrsi.benchmark.tasks.moe-forward-npu.grader: "
            "importlib.util.module_from_spec executes files loaded by path in-process",
            "inferrsi.benchmark.tasks.qwen21-denoise-npu.benchmark: "
            "importlib.util.module_from_spec executes files loaded by path in-process",
        ))

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
