from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.repository import _gate_policy_support as support
from tests.repository._gate_policy_support import (
    IsolationReport,
    blocker_kinds,
    exact_pairs,
    first_wave_report,
    load_manifest,
    shell_sources,
)

MANIFEST = load_manifest()
PAIRS = exact_pairs(MANIFEST)
LEAF = MANIFEST["technical_leaf"]["module"]
# #412 R1 emptied the allowlist. The nine retired pair records stay in the manifest
# history. Staging them again drives the staged-pair rules that the gate still holds.
C2_RECORD = next(
    item for item in MANIFEST["revision_history"] if "retired_compatibility_pairs" in item
)
RETIRED_PAIRS = C2_RECORD["retired_compatibility_pairs"]
STAGED = {**MANIFEST, "compatibility_pairs": RETIRED_PAIRS}
STAGED_PAIRS = exact_pairs(STAGED)
SOURCES = shell_sources(STAGED)
EMPTY_ALLOWLIST = {**MANIFEST, "compatibility_pairs": []}
# The future neutral leaf, built from the manifest fragment and allowed imports.
LEAF_SOURCE = (
    '"""Raw repository-pack data."""\n\n'
    "from __future__ import annotations\n\n"
    "import json\n"
    "from importlib.resources import files\n"
    "from typing import Any\n\n"
    f"{MANIFEST['technical_leaf']['original_fragment']['source']}\n"
)
# Module paths assumed for synthetic graphs only; the gate never infers them.
SYNTHETIC_H_ENTRIES = (
    "inferrsi.harness.api",
    "inferrsi.harness.execution_service",
    "inferrsi.harness.records",
)
# #451 C2: the leaf lives in ``inferrsi.resources``, whose initializer imports nothing.
LEAF_FILE = "resources/repository_packs.py"
RESOURCES_INIT = '"""Packaged resources."""\n'
# Every first-wave trigger is cleared: no allowlist and no legacy mix.
CLEARED_TREE = {
    "__init__.py": "",
    "resources/__init__.py": RESOURCES_INIT,
    LEAF_FILE: LEAF_SOURCE,
    "knowledge/__init__.py": "",
    "knowledge/catalog.py": "from ..resources.repository_packs import REPO_TYPES\n",
    "benchmark/__init__.py": "",
    "apps/__init__.py": "",
    "apps/main.py": "from inferrsi.knowledge import catalog\nfrom inferrsi.harness import api\n",
    "harness/__init__.py": "",
    "harness/api.py": "VALUE = 1\n",
}
# The bounded contracts package (#451 C1, C2): the initializer's one export and five
# standalone modules.
CONTRACTS_INIT = (
    '"""Shared contracts."""\n\n'
    "from .runspec import RunSpec\n\n"
    '__all__ = ["RunSpec"]\n'
)
CONTRACTS_TREE = {
    "contracts/__init__.py": CONTRACTS_INIT,
    "contracts/json_v1.py": "import json\n",
    "contracts/runspec.py": "import math\n\n\nclass RunSpec:\n    pass\n",
    "contracts/_harness_errors.py": "from dataclasses import dataclass\n",
    "contracts/claim.py": "from enum import Enum\n",
    "contracts/evidence.py": "from pathlib import Path\n",
}

def _shell(importer: str) -> str:
    """A shape-valid static shell generated from the manifest export lists."""
    lines = ['"""Compatibility shell."""', "", "from __future__ import annotations", ""]
    seen: set[str] = set()
    for target, names in sorted(SOURCES[importer].items()):
        for name in sorted(names - seen):
            lines.append(f"from {target} import {name} as {name}")
            seen.add(name)
    quoted = ", ".join(f'"{name}"' for name in sorted(seen))
    return "\n".join([*lines, "", f"__all__ = [{quoted}]", ""])


def _k01_tree() -> dict[str, str]:
    """A K01-shaped tree that follows every first-wave rule."""
    files = {
        "__init__.py": "",
        "resources/__init__.py": RESOURCES_INIT,
        LEAF_FILE: LEAF_SOURCE,
        **CONTRACTS_TREE,
        "knowledge/__init__.py": '"""Knowledge."""\n',
        # K.catalog -> the data leaf is intra-closure, not a tenth pair.
        "knowledge/catalog.py": (
            "from ..resources import repository_packs\nfrom . import _source_snapshot\n"
        ),
        "knowledge/knowledge_operations.py": "from inferrsi.contracts import json_v1\n",
        "apps/host/__init__.py": "",
        "apps/host/inspection.py": "from ...resources.repository_packs import repository_pack\n",
        "harness/__init__.py": "",
        "harness/api.py": "VALUE = 1\n",
        "benchmark/__init__.py": "",
        "apps/__init__.py": "",
        "apps/main.py": "from inferrsi.knowledge import catalog\n",
    }
    for importer in SOURCES:
        name = importer.removeprefix("inferrsi.")
        files[f"{name}.py"] = _shell(importer)
        files.setdefault(f"knowledge/{name}.py", '"""Moved body."""\n')
    return files


# The one declared importer of the data leaf, as the real tree writes it. #498 slice 3a
# moved it from infra/inspection.py to apps/host/inspection.py.
INSPECTION = "from ...resources.repository_packs import repository_pack\n"
# #408 A1: the moved CLI parser reads the tuple through Knowledge and names no leaf.
PARSER = "from ...knowledge.catalog import BACKENDS, REPO_TYPES\n"
# The root parser that A1 deleted, as R1 left it. It is refused if it returns.
ARGUMENTS = (
    "from .knowledge.catalog import BACKENDS\n"
    "from .resources.repository_packs import REPO_TYPES\n"
)


def _r1_tree() -> dict[str, str]:
    """The post-A1 shape: the K01 tree with no root shell and the CLI under apps/cli."""
    files = {
        relative: source
        for relative, source in _k01_tree().items()
        if f"inferrsi.{relative.removesuffix('.py')}" not in SOURCES
    }
    files["apps/cli/__init__.py"] = "from .arguments import parser\n"
    files["apps/cli/arguments.py"] = PARSER
    return files


def _report(
    changes: dict[str, str | None],
    manifest: dict[str, Any] = MANIFEST,
    h_entries: tuple[str, ...] = SYNTHETIC_H_ENTRIES,
    base: dict[str, str] | None = None,
) -> IsolationReport:
    """Scan a temporary tree; a ``None`` change drops that file."""
    files = {**(_r1_tree() if base is None else base), **changes}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for relative, source in files.items():
            if source is None:
                continue
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        return first_wave_report(root, manifest, h_entries)


def _violated(report: IsolationReport, *parts: str) -> bool:
    return any(all(part in message for part in parts) for message in report.violations)


def _staged(changes: dict[str, str | None]) -> IsolationReport:
    """The K01 shape with the nine retired pairs staged again."""
    return _report(changes, manifest=STAGED, base=_k01_tree())


class ManifestTest(unittest.TestCase):
    def test_allowlist_is_empty_and_the_nine_retired_pairs_are_recorded(self) -> None:
        leaves = (
            "catalog",
            "_source_snapshot",
            "skill_catalog",
            "_skill_selection",
            "research",
            "knowledge_store",
            "knowledge_operations",
        )
        same_named = {(f"inferrsi.{n}", f"inferrsi.knowledge.{n}") for n in leaves}
        leaf_routes = {("inferrsi.catalog", LEAF), ("inferrsi.infra.inspection", LEAF)}
        # R1 ends at zero pairs: nothing is staged, so no shell source is declared.
        self.assertEqual(MANIFEST["compatibility_pairs"], [])
        self.assertEqual(PAIRS, frozenset())
        self.assertEqual(shell_sources(MANIFEST), {})
        # The record of what retired is the exact nine, kept with its export lists.
        self.assertEqual(len(RETIRED_PAIRS), 9)
        self.assertEqual(STAGED_PAIRS, same_named | leaf_routes)
        self.assertEqual({importer for importer, _ in same_named}, set(SOURCES))
        self.assertLess(set(SOURCES), support.RETIRED_ROOT_MODULES)
        self.assertEqual(LEAF, "inferrsi.resources.repository_packs")
        self.assertEqual(
            C2_RECORD["retired_catalog_two_routes"][
                "neutral_leaf_export"
            ]["target"],
            LEAF,
        )
        self.assertNotIn("catalog_two_routes", MANIFEST)
        self.assertFalse(
            [pair for pair in STAGED_PAIRS if "inferrsi._repo_pack_data" in pair],
            STAGED_PAIRS,
        )

    def test_catalog_routes_keep_repository_pack_out_of_knowledge(self) -> None:
        catalog = SOURCES["inferrsi.catalog"]
        self.assertNotIn("repository_pack", catalog["inferrsi.knowledge.catalog"])
        self.assertEqual(catalog[LEAF], {"REPO_TYPES", "repository_pack"})

    def test_fragment_hash_matches_recorded_source(self) -> None:
        # The recorded hash covers the fragment text plus its final newline.
        fragment = MANIFEST["technical_leaf"]["original_fragment"]
        text = fragment["source"] + "\n"
        self.assertEqual(
            hashlib.sha256(text.encode("utf-8")).hexdigest(), fragment["fragment_sha256"]
        )


class AllowlistTest(unittest.TestCase):
    """A01-1: only exact (importer, target) pairs pass, and R1 leaves none staged."""

    def test_r1_tree_passes_with_no_pair(self) -> None:
        report = _report({})
        self.assertEqual(report.violations, ())
        self.assertNotIn("allowlist", blocker_kinds(report))

    def test_nine_staged_pairs_still_pass_and_block(self) -> None:
        # The staged-pair rules were kept, not erased: the K01 shape is clean under
        # the nine retired pairs, and staging them is what blocks.
        report = _staged({})
        self.assertEqual(report.violations, ())
        self.assertNotIn(("inferrsi.knowledge.catalog", LEAF), STAGED_PAIRS)
        self.assertEqual(report.blockers, ("allowlist: 9 compatibility pairs",))
        self.assertFalse(report.isolation_complete)

    def test_adjacent_knowledge_target_fails(self) -> None:
        shell = _shell("inferrsi.catalog")
        shell += "from inferrsi.knowledge.catalog_extra import VALUE as VALUE\n"
        report = _staged({"catalog.py": shell, "knowledge/catalog_extra.py": "VALUE = 1\n"})
        self.assertTrue(_violated(report, "catalog.py imports inferrsi.knowledge"))
        self.assertTrue(
            _violated(report, "unlisted import from inferrsi.knowledge.catalog_extra")
        )

    def test_second_importer_fails(self) -> None:
        cases = (
            (
                "evaluation.py",
                "from inferrsi.knowledge.catalog import search_knowledge\n",
                "evaluation.py imports inferrsi.knowledge",
            ),
            (
                "apps/host/inspection.py",
                "from inferrsi.knowledge.catalog import REPO_TYPES\n",
                "inferrsi.apps.host.inspection reaches inferrsi.knowledge",
            ),
            (
                "evaluation.py",
                "from inferrsi.resources.repository_packs import repository_pack\n",
                "inferrsi.evaluation is a second importer of "
                "inferrsi.resources.repository_packs",
            ),
            (
                "harness/api.py",
                "from inferrsi.resources import repository_packs\n",
                "inferrsi.harness.api is a second importer of "
                "inferrsi.resources.repository_packs",
            ),
            (
                "benchmark/probe.py",
                "import inferrsi.resources.repository_packs\n",
                "inferrsi.benchmark.probe is a second importer of "
                "inferrsi.resources.repository_packs",
            ),
        )
        for manifest, base in ((MANIFEST, _r1_tree()), (STAGED, _k01_tree())):
            for path, source, expected in cases:
                with self.subTest(path=path, source=source, pairs=len(exact_pairs(manifest))):
                    report = _report({path: source}, manifest=manifest, base=base)
                    self.assertTrue(_violated(report, expected), report.violations)

    def test_only_declared_host_importer_may_use_the_leaf(self) -> None:
        # D020: host inspection -> the data leaf passes, and only apps.host.inspection is
        # the declared importer of that leaf (#498 slice 3a moved it from Infra).
        report = _report({})
        self.assertEqual(report.violations, ())
        host_leaf = {
            importer
            for importer in support.LEAF_IMPORTERS
            if importer.startswith("inferrsi.apps.host")
        }
        self.assertEqual(host_leaf, {"inferrsi.apps.host.inspection"})
        report = _report(
            {"apps/host/other.py": "from ...resources.repository_packs import REPO_TYPES\n"}
        )
        self.assertTrue(
            _violated(
                report,
                "inferrsi.apps.host.other is a second importer of "
                "inferrsi.resources.repository_packs",
            ),
            report.violations,
        )


def _importer_defects(line: str, name: str, other: str) -> tuple[tuple[str, str], ...]:
    """Every way a declared importer may not reach the leaf: (source, expected)."""
    relative = line.split(" import ")[0].removeprefix("from ")
    package = relative.removesuffix(".repository_packs")
    bound = f"import {name}"
    return (
        (line.replace(bound, f"import {other}"), f"imports unlisted name {LEAF}.{other}"),
        (
            line.replace(bound, f"import {name}, {other}"),
            f"imports unlisted name {LEAF}.{other}",
        ),
        (line.replace(bound, f"import {name} as loaded"), f"aliases {name} as loaded"),
        (line.replace(bound, "import *"), f"has a star import from {LEAF}"),
        (f"from {package} import repository_packs\n", f"imports {LEAF} as a module object"),
        (
            f"from {package} import repository_packs as packs\n",
            f"imports {LEAF} as a module object",
        ),
        (f"import {LEAF}\n", f"imports {LEAF} as a module object"),
        (f"import {LEAF} as packs\n", f"imports {LEAF} as a module object"),
        (line + "import inferrsi.resources\n", f"imports inferrsi.resources beside {LEAF}"),
        (
            line + f"from {package}.extra import VALUE\n",
            f"imports inferrsi.resources.extra.VALUE beside {LEAF}",
        ),
        (
            line + f"from {package} import extra\n",
            f"imports inferrsi.resources.extra beside {LEAF}",
        ),
        (f"def load():\n    {line}    return {name}\n", f"imports {LEAF} below module level"),
        (
            line + "import sys\nsys.modules['inferrsi._repo_pack_data'] = sys.modules[__name__]\n",
            "touches sys.modules",
        ),
        (
            line + f"import importlib\nimportlib.import_module('{LEAF}')\n",
            "has a dynamic import",
        ),
        (line + f"__import__('{LEAF}')\n", "has a dynamic import"),
    )


class PermanentLeafImporterTest(unittest.TestCase):
    """#412 R1: one exact importer of the data leaf, outside the staged allowlist."""

    def test_the_rule_is_one_importer_and_one_name_and_not_a_pair(self) -> None:
        self.assertEqual(
            support.LEAF_IMPORTERS,
            {"inferrsi.apps.host.inspection": frozenset({"repository_pack"})},
        )
        # #408 A1 removed the temporary parser entry; the gate declares nothing else.
        self.assertFalse(hasattr(support, "TEMPORARY_LEAF_IMPORTERS"))
        self.assertNotIn("temporary_importers", MANIFEST["technical_leaf"])
        self.assertEqual(MANIFEST["compatibility_pairs"], [])
        # No Knowledge, Harness or Benchmark module is declared, and no prefix. #498 slice
        # 3a moved the one importer into the Apps host package, which keeps Infra's limit.
        for importer in support.LEAF_IMPORTERS:
            self.assertTrue(importer.startswith("inferrsi.apps.host."), importer)
            self.assertNotIn(support._core_of(importer), ("knowledge", "harness", "benchmark"))
            self.assertNotIn("*", importer)

    def test_the_permanent_rule_alone_does_not_block(self) -> None:
        # The infra edge is admitted with nothing staged and adds no blocker.
        report = _report({})
        self.assertEqual(report.violations, ())
        self.assertEqual(report.blockers, ())
        self.assertTrue(report.isolation_complete)

    def test_a1_removed_the_temporary_parser_entry_and_nothing_replaced_it(self) -> None:
        report = _report({})
        self.assertEqual(report.violations, ())
        self.assertEqual(report.blockers, ())
        self.assertTrue(report.new_core_closure_isolated)
        # The moved parser reads through Knowledge. Naming the leaf from the parser, the
        # CLI package, another Apps module or a returning root file is a second importer.
        for path in ("apps/cli/arguments.py", "apps/cli/__init__.py", "apps/main.py",
                     "cli.py", "arguments.py"):
            with self.subTest(path=path):
                moved = _report(
                    {path: "from inferrsi.resources.repository_packs import REPO_TYPES\n"}
                )
                self.assertTrue(_violated(moved, f"is a second importer of {LEAF}"),
                                moved.violations)

    def test_the_edge_is_admitted_by_the_rule_and_not_by_an_erased_scan(self) -> None:
        with mock.patch.dict(support.LEAF_IMPORTERS, clear=True):
            report = _report({})
        self.assertTrue(
            _violated(report, f"inferrsi.apps.host.inspection is a second importer of {LEAF}"),
            report.violations,
        )
        # The root parser that A1 deleted is refused on every count if it returns, and
        # no blocker-only entry admits it any more.
        report = _report({"arguments.py": ARGUMENTS})
        for expected in (
            f"inferrsi.arguments is a second importer of {LEAF}",
            "inferrsi.arguments is a retired root module",
            "arguments.py imports inferrsi.knowledge",
        ):
            self.assertTrue(_violated(report, expected), report.violations)
        self.assertNotIn("temporary leaf importers", blocker_kinds(report))
        self.assertFalse(report.isolation_complete)

    def test_staging_the_infra_pair_again_blocks(self) -> None:
        pair = [item for item in RETIRED_PAIRS if item["importer"] == "infra.inspection"]
        self.assertEqual(len(pair), 1)
        report = _report(
            {}, manifest={**MANIFEST, "compatibility_pairs": pair}
        )
        self.assertEqual(report.violations, ())
        self.assertEqual(report.blockers, ("allowlist: 1 compatibility pairs",))

    def test_another_importer_fails(self) -> None:
        line = "from inferrsi.resources.repository_packs import repository_pack\n"
        paths = (
            "infra/other.py", "infra/inspection_helpers.py", "infra/__init__.py",
            "infra/platforms/__init__.py", "harness/api.py", "harness/runner.py",
            "benchmark/probe.py", "apps/main.py", "apps/inspection.py",
            "apps/host/prepared_environment.py", "model/probe.py",
            "cli.py", "arguments.py", "apps/cli/__init__.py", "apps/cli/arguments.py",
            "benchmark_operations.py", "apps/benchmark_operations.py", "summary_chart.py",
            "apps/views/summary_chart.py", "mindie_project.py", "apps/mindie/project.py",
            "_mindie_read_worker.py", "apps/mindie/read_worker.py", "helper.py", "catalog.py",
            "apps/integrations/mindie/project.py", "apps/integrations/mindie/read_worker.py",
            "_repo_pack_data.py",
        )
        for path in paths:
            with self.subTest(path=path):
                report = _report({path: line})
                module = "inferrsi." + path.removesuffix(".py").removesuffix(
                    "/__init__"
                ).replace("/", ".")
                self.assertTrue(
                    _violated(report, f"{module} is a second importer of {LEAF}"),
                    report.violations,
                )

    def test_declared_importer_shape_is_exact(self) -> None:
        declared = (
            ("apps/host/inspection.py", "inferrsi.apps.host.inspection", INSPECTION,
             "repository_pack", "REPO_TYPES"),
        )
        for path, module, line, name, other in declared:
            clean = _report({path: line, "resources/extra.py": None})
            self.assertEqual(clean.violations, ())
            for source, expected in _importer_defects(line, name, other):
                with self.subTest(module=module, source=source):
                    report = _report({path: source, "resources/extra.py": "VALUE = 1\n"})
                    self.assertTrue(
                        _violated(report, f"{module} ", expected), report.violations
                    )

    def test_hidden_routes_around_the_rule_fail(self) -> None:
        dynamic = f"import importlib\nimportlib.import_module('{LEAF}')\n"
        cases = (
            # A forwarding module under the retired leaf name, static or star.
            ({"_repo_pack_data.py": f"from {LEAF} import *\n"},
             f"inferrsi._repo_pack_data is a second importer of {LEAF}"),
            # The retired root catalog route back to the leaf.
            ({"catalog.py": _shell("inferrsi.catalog")},
             f"inferrsi.catalog is a second importer of {LEAF}"),
            ({"catalog.py": _shell("inferrsi.catalog")},
             "inferrsi.catalog is a retired root module"),
            # A re-export through the leaf's own initializer.
            ({"resources/__init__.py": RESOURCES_INIT + "from .repository_packs import "
                                                         "REPO_TYPES\n"},
             "inferrsi.resources imports inferrsi.resources.repository_packs.REPO_TYPES"),
            # A dynamic import from an undeclared Infra, Harness or Knowledge module.
            ({"infra/other.py": dynamic},
             "inferrsi.infra.other reaches an undeclared dynamic import"),
            ({"harness/api.py": dynamic},
             "inferrsi.harness.api reaches an undeclared dynamic import"),
            ({"knowledge/research.py": dynamic},
             "inferrsi.knowledge.research reaches an undeclared dynamic import"),
            # A module beside the leaf is not the leaf, for Knowledge either.
            ({"resources/extra.py": "VALUE = 1\n",
              "knowledge/research.py": "from inferrsi.resources import extra\n"},
             "inferrsi.knowledge.research reaches inferrsi.resources.extra"),
        )
        for changes, expected in cases:
            with self.subTest(expected=expected):
                report = _report(changes)
                self.assertTrue(_violated(report, expected), report.violations)
                self.assertFalse(report.isolation_complete)


class RetiredRootModuleTest(unittest.TestCase):
    """#412 R1 and #408 A1, A2 and #452 M1: the nineteen deleted root modules cannot return."""

    def test_the_retired_set_is_the_exact_eleven_and_absent_from_the_tree(self) -> None:
        self.assertEqual(support.RETIRED_BY_A1, {"inferrsi.cli", "inferrsi.arguments"})
        self.assertEqual(
            support.RETIRED_BY_A2, {"inferrsi.summary_chart", "inferrsi.benchmark_operations"}
        )
        self.assertEqual(
            support.RETIRED_BY_M1,
            {
                "inferrsi.mindie_project", "inferrsi.mindie_context", "inferrsi.mindie_mcp",
                "inferrsi._mindie_read_worker",
            },
        )
        self.assertEqual(
            support.RETIRED_ROOT_MODULES,
            support.RETIRED_BY_R1 | support.RETIRED_BY_A1 | support.RETIRED_BY_A2
            | support.RETIRED_BY_M1,
        )
        self.assertEqual(len(support.RETIRED_ROOT_MODULES), 19)
        self.assertEqual(
            support.RETIRED_BY_R1,
            {
                "inferrsi._skill_selection", "inferrsi._source_snapshot", "inferrsi.catalog",
                "inferrsi.knowledge_operations", "inferrsi.knowledge_store",
                "inferrsi.research", "inferrsi.skill_catalog", "inferrsi.evaluation",
                "inferrsi.execution", "inferrsi.reporting", "inferrsi.inspection",
            },
        )
        for module in support.RETIRED_ROOT_MODULES:
            name = module.removeprefix("inferrsi.")
            self.assertFalse((support.ROOT / f"{name}.py").exists(), name)
            self.assertFalse((support.ROOT / name).exists(), name)
        self.assertFalse(hasattr(support, "LEGACY_RUN_FORWARDERS"))

    def test_a_returning_file_fails_whatever_it_holds(self) -> None:
        for module in sorted(support.RETIRED_ROOT_MODULES):
            name = module.removeprefix("inferrsi.")
            bodies = ['"""Returned."""\n', "VALUE = 1\n"]
            if module in SOURCES:
                bodies.append(_shell(module))
            for path in (f"{name}.py", f"{name}/__init__.py"):
                for body in bodies:
                    with self.subTest(path=path, body=body[:24]):
                        report = _report({path: body})
                        self.assertIn(f"{module} is a retired root module", report.violations)
                        self.assertFalse(report.isolation_complete)

    def test_a_returning_shell_also_fails_as_a_cross_core_import(self) -> None:
        for module in sorted(SOURCES):
            name = module.removeprefix("inferrsi.")
            with self.subTest(module=module):
                report = _report({f"{name}.py": _shell(module)})
                self.assertTrue(
                    _violated(report, f"{name}.py imports inferrsi.knowledge"),
                    report.violations,
                )


SHELL_DEFECTS = (
    ("def research_knowledge():\n    return None\n", "function or class body research_knowledge"),
    ("class Shim:\n    pass\n", "function or class body Shim"),
    ("def __getattr__(name):\n    return name\n", "defines __getattr__"),
    ("import sys\nsys.modules[__name__] = sys\n", "touches sys.modules"),
    ("import importlib\nimportlib.import_module('inferrsi.knowledge')\n", "dynamic import"),
    ("__import__('inferrsi.knowledge.research')\n", "dynamic import"),
    ("from inferrsi.knowledge.research import *\n", "star import"),
    (
        "from inferrsi.knowledge.research import research_knowledge as found\n",
        "aliases research_knowledge as found",
    ),
    (
        "from inferrsi.knowledge.research import helper as helper\n",
        "unlisted name inferrsi.knowledge.research.helper",
    ),
    (
        "from inferrsi.knowledge.catalog import get_knowledge as get_knowledge\n",
        "unlisted import from inferrsi.knowledge.catalog",
    ),
    ("import json\n", "unlisted import of json"),
    ("VALUE = 1\n", "module-level assignment"),
    ("__all__ = ['research_knowledge'] + []\n", "__all__ is not a literal list"),
    ("__all__ = ('research_knowledge',)\n", "__all__ is not a literal list"),
)


class ShellShapeTest(unittest.TestCase):
    """A01-2: a shell is docstring, future import, listed imports, literal __all__."""

    def test_illegal_shell_shapes_fail(self) -> None:
        for snippet, expected in SHELL_DEFECTS:
            with self.subTest(snippet=snippet):
                report = _staged({"research.py": _shell("inferrsi.research") + snippet})
                self.assertTrue(
                    _violated(report, "inferrsi.research ", expected), report.violations
                )

    def test_old_leaf_keeping_a_body_beside_its_k_module_fails(self) -> None:
        # The declared export edge makes root catalog a shell once K.catalog
        # exists, so a second copy of the body is rejected.
        report = _staged(
            {
                "catalog.py": "def search_knowledge():\n    return []\n",
                "apps/host/inspection.py": "from ...catalog import search_knowledge\n",
            }
        )
        self.assertTrue(_violated(report, "inferrsi.catalog has a function or class body"))
        self.assertTrue(
            _violated(report, "inferrsi.apps.host.inspection reaches inferrsi.knowledge.catalog")
        )


class TransferGraphTest(unittest.TestCase):
    """Synthetic transfer graphs over absolute, relative, and package-name edges."""

    def test_knowledge_through_old_shell_fails(self) -> None:
        forms = (
            "from inferrsi.catalog import search_knowledge\n",
            "from .. import catalog\n",
            "from inferrsi import catalog\n",
            "import inferrsi.catalog\n",
        )
        for source in forms:
            with self.subTest(source=source):
                # The shell is back on disk: Knowledge may not reach it by any form.
                report = _report(
                    {"catalog.py": _shell("inferrsi.catalog"), "knowledge/research.py": source}
                )
                self.assertTrue(
                    _violated(report, "inferrsi.knowledge.research reaches inferrsi.catalog"),
                    report.violations,
                )

    def test_apps_through_old_shell_fails(self) -> None:
        source = "from inferrsi.knowledge_store import KnowledgeStore\n"
        # With or without the file, the retired name is an old root leaf for Apps.
        for shell in (None, _shell("inferrsi.knowledge_store")):
            with self.subTest(returned=shell is not None):
                report = _report({"apps/main.py": source, "knowledge_store.py": shell})
                self.assertTrue(
                    _violated(report, "inferrsi.apps.main reaches inferrsi.knowledge_store"),
                    report.violations,
                )

    def test_data_leaf_accepts_only_listed_stdlib_imports(self) -> None:
        self.assertFalse(_violated(_report({}), LEAF))
        hidden = LEAF_SOURCE.replace(
            "    if repo_type", "    from inferrsi import catalog\n    if repo_type", 1
        )
        dynamic = LEAF_SOURCE.replace("import json\n", "import importlib\nimport json\n")
        dynamic += "\n\ndef _load(name):\n    return importlib.import_module(name)\n"
        cases = (
            (hidden, "imports inferrsi.catalog"),
            (LEAF_SOURCE.replace("import json\n", "import json\nimport inferrsi.infra\n"),
             "imports inferrsi.infra"),
            # Relative forms resolve from the leaf's own package, inferrsi.resources.
            (LEAF_SOURCE.replace("import json\n", "import json\nfrom .. import catalog\n"),
             "imports inferrsi.catalog"),
            (LEAF_SOURCE.replace("import json\n", "import json\nfrom . import sibling\n"),
             "imports inferrsi.resources.sibling"),
            # The leaf never imports Harness to find a target-repository descriptor.
            (LEAF_SOURCE.replace("import json\n", "import json\nfrom ..harness import api\n"),
             "imports inferrsi.harness.api"),
            (LEAF_SOURCE.replace("import json\n", "import json\nimport inferrsi.harness\n"),
             "imports inferrsi.harness"),
            (dynamic, "has a dynamic import"),
            (LEAF_SOURCE.replace("import Any", "import Any, Dict"), "imports typing.Dict"),
            (LEAF_SOURCE + "\nEXTRA = 1\n", "defines EXTRA at top level"),
        )
        for source, expected in cases:
            with self.subTest(expected=expected):
                report = _report({LEAF_FILE: source})
                self.assertTrue(_violated(report, f"{LEAF} {expected}"), report.violations)

    def test_leaf_parent_initializer_must_stay_import_free(self) -> None:
        # #451 C2: Python runs inferrsi/resources/__init__.py with every leaf import.
        self.assertEqual(_report({}).violations, ())
        dynamic = "import importlib\nimportlib.import_module('inferrsi.harness')\n"
        cases = (
            ("from ..harness import api\n", "imports inferrsi.harness.api"),
            ("from inferrsi.knowledge import catalog\n", "imports inferrsi.knowledge.catalog"),
            ("import inferrsi.apps\n", "imports inferrsi.apps"),
            ("from . import repository_packs\n", "imports inferrsi.resources.repository_packs"),
            ("import json\n", "imports json"),
            (dynamic, "has a dynamic import"),
            ("__import__('inferrsi.harness')\n", "has a dynamic import"),
            ("def __getattr__(name):\n    raise AttributeError(name)\n",
             "has a FunctionDef statement"),
            ("VALUE = 1\n", "has a Assign statement"),
            ("open('pack.json')\n", "has a Expr statement"),
        )
        for snippet, expected in cases:
            with self.subTest(snippet=snippet):
                report = _report({"resources/__init__.py": RESOURCES_INIT + snippet})
                self.assertTrue(
                    _violated(report, "inferrsi.resources ", expected), report.violations
                )

    def test_core_import_in_the_leaf_parent_fails_every_closure_that_loads_it(self) -> None:
        report = _report({"resources/__init__.py": "from ..harness import api\n"})
        for importer in ("inferrsi.apps.host.inspection", "inferrsi.knowledge.catalog"):
            with self.subTest(importer=importer):
                self.assertTrue(
                    _violated(report, f"{importer} reaches inferrsi.harness"), report.violations
                )
        self.assertFalse(report.new_core_closure_isolated)

    def test_resources_prefix_exempts_no_adjacent_module(self) -> None:
        # Knowledge may load the leaf and its initializer, not a sibling beside them.
        report = _report(
            {
                "resources/extra.py": "VALUE = 1\n",
                "knowledge/research.py": "from inferrsi.resources import extra\n",
            }
        )
        self.assertTrue(
            _violated(report, "inferrsi.knowledge.research reaches inferrsi.resources.extra"),
            report.violations,
        )
        self.assertFalse(report.new_core_closure_isolated)

    def test_retired_root_leaf_is_outside_the_knowledge_closure(self) -> None:
        # Adding the old root file back does not restore it as the leaf.
        report = _report(
            {
                "_repo_pack_data.py": LEAF_SOURCE,
                "knowledge/research.py": "from .. import _repo_pack_data\n",
            }
        )
        self.assertTrue(
            _violated(report, "inferrsi.knowledge.research reaches inferrsi._repo_pack_data"),
            report.violations,
        )

    def test_host_inspection_through_root_catalog_fails(self) -> None:
        report = _report(
            {
                "catalog.py": _shell("inferrsi.catalog"),
                "apps/host/inspection.py": "from ...catalog import repository_pack\n",
            }
        )
        self.assertIn(
            "inferrsi.apps.host.inspection reaches inferrsi.knowledge.catalog: "
            "inferrsi.apps.host.inspection -> inferrsi.catalog -> inferrsi.knowledge.catalog",
            report.violations,
        )

    def test_infra_reaching_harness_benchmark_or_apps_fails(self) -> None:
        cases = (
            ("from inferrsi.harness import api\n", "inferrsi.harness.api"),
            ("import inferrsi.benchmark\n", "inferrsi.benchmark"),
            ("import inferrsi.apps.main\n", "inferrsi.apps.main"),
        )
        for source, target in cases:
            with self.subTest(source=source):
                report = _report({"infra/probe.py": source})
                self.assertTrue(_violated(report, f"inferrsi.infra.probe reaches {target}"))

    def test_undeclared_dynamic_edge_fails_closed(self) -> None:
        source = "import importlib\n\n\ndef load():\n    return importlib.import_module('x')\n"
        for path, module in (
            ("knowledge/research.py", "inferrsi.knowledge.research"),
            ("apps/host/inspection.py", "inferrsi.apps.host.inspection"),
        ):
            with self.subTest(path=path):
                report = _report({path: source})
                self.assertTrue(
                    _violated(report, f"{module} reaches an undeclared dynamic import in {module}")
                )


K_OPERATIONS = "inferrsi.knowledge.knowledge_operations"
CONTRACTS_INIT_DEFECTS = (
    ("from .claim import Verdict\n", "unlisted import from inferrsi.contracts.claim"),
    ("from . import json_v1\n", "unlisted import from inferrsi.contracts"),
    ("from inferrsi.apps import main\n", "unlisted import from inferrsi.apps"),
    ("from inferrsi.harness import api\n", "unlisted import from inferrsi.harness"),
    ("from .runspec import helper\n", "unlisted name inferrsi.contracts.runspec.helper"),
    ("def __getattr__(name):\n    raise AttributeError(name)\n", "defines __getattr__"),
    (
        "import sys\nsys.modules['inferrsi.runspec'] = sys.modules[__name__]\n",
        "touches sys.modules",
    ),
    ("import importlib\nimportlib.import_module('inferrsi.claim')\n", "dynamic import"),
    ("VALUE = 1\n", "module-level assignment"),
)


class ContractsPackageTest(unittest.TestCase):
    """#451 C1: one bounded contracts package. Exact modules, one export, no core import."""

    def test_knowledge_names_only_the_encoder_inside_the_package(self) -> None:
        allowed = (
            "from inferrsi.contracts import json_v1\n",
            "from inferrsi.contracts.json_v1 import encode\n",
            "import inferrsi.contracts.json_v1\n",
            "from ..contracts import json_v1\n",
        )
        for source in allowed:
            with self.subTest(source=source):
                report = _report({"knowledge/knowledge_operations.py": source})
                self.assertEqual(report.violations, ())
        refused = (
            ("from inferrsi.contracts import RunSpec\n", "imports inferrsi.contracts;"),
            ("from inferrsi.contracts import json_v1, RunSpec\n", "imports inferrsi.contracts;"),
            ("import inferrsi.contracts\n", "imports inferrsi.contracts;"),
            (
                "from inferrsi.contracts.runspec import RunSpec\n",
                "imports inferrsi.contracts.runspec;",
            ),
            ("from ..contracts import claim\n", "imports inferrsi.contracts.claim;"),
            ("from inferrsi.contracts.claim import Verdict\n", "reaches inferrsi.contracts.claim"),
            # #451 C2: the evidence path rules are a contracts module, not a Knowledge input.
            ("from inferrsi.contracts import evidence\n", "imports inferrsi.contracts.evidence;"),
            (
                "from ..contracts.evidence import EVIDENCE_SEGMENTS\n",
                "reaches inferrsi.contracts.evidence",
            ),
        )
        for source, expected in refused:
            with self.subTest(source=source):
                report = _report({"knowledge/knowledge_operations.py": source})
                self.assertTrue(_violated(report, K_OPERATIONS, expected), report.violations)

    def test_retired_root_encoder_is_outside_the_knowledge_closure(self) -> None:
        report = _report(
            {
                "_json_v1.py": "import json\n",
                "knowledge/knowledge_operations.py": "from inferrsi import _json_v1\n",
            }
        )
        self.assertTrue(
            _violated(report, f"{K_OPERATIONS} reaches inferrsi._json_v1"), report.violations
        )

    def test_package_prefix_exempts_no_undeclared_module(self) -> None:
        report = _report(
            {
                "contracts/extra.py": "VALUE = 1\n",
                "knowledge/knowledge_operations.py": "from inferrsi.contracts import extra\n",
            }
        )
        self.assertTrue(
            _violated(report, "inferrsi.contracts.extra is not a declared contracts module"),
            report.violations,
        )
        self.assertTrue(
            _violated(report, f"{K_OPERATIONS} reaches inferrsi.contracts.extra"),
            report.violations,
        )

    def test_initializer_is_limited_to_the_runspec_export(self) -> None:
        for snippet, expected in CONTRACTS_INIT_DEFECTS:
            with self.subTest(snippet=snippet):
                report = _report({"contracts/__init__.py": CONTRACTS_INIT + snippet})
                self.assertTrue(
                    _violated(report, "inferrsi.contracts ", expected), report.violations
                )
        shapes = (
            CONTRACTS_INIT.replace('["RunSpec"]', '["RunSpec", "runspec"]'),
            CONTRACTS_INIT.replace('["RunSpec"]', "[]"),
            CONTRACTS_INIT.replace("from .runspec import RunSpec\n", ""),
            CONTRACTS_INIT.replace("import RunSpec", "import RunSpec, RunSpec"),
        )
        for source in shapes:
            with self.subTest(source=source):
                report = _report({"contracts/__init__.py": source})
                self.assertTrue(
                    _violated(report, "inferrsi.contracts must re-export exactly RunSpec"),
                    report.violations,
                )
        aliased = CONTRACTS_INIT.replace("import RunSpec", "import RunSpec as Spec")
        report = _report({"contracts/__init__.py": aliased})
        self.assertTrue(_violated(report, "inferrsi.contracts aliases RunSpec as Spec"))

    def test_contract_modules_import_no_inferrsi_module(self) -> None:
        dynamic = (
            "import importlib\n\n\n"
            "def load(name):\n    return importlib.import_module(name)\n"
        )
        cases = (
            (
                "contracts/json_v1.py",
                "from inferrsi.knowledge import catalog\n",
                "inferrsi.contracts.json_v1 imports inferrsi.knowledge.catalog",
            ),
            (
                "contracts/json_v1.py",
                "from inferrsi.harness import api\n",
                "inferrsi.contracts.json_v1 imports inferrsi.harness.api",
            ),
            (
                "contracts/runspec.py",
                "from inferrsi.infra import artifacts\n",
                "inferrsi.contracts.runspec imports inferrsi.infra",
            ),
            (
                "contracts/claim.py",
                "from . import json_v1\n",
                "inferrsi.contracts.claim imports inferrsi.contracts.json_v1",
            ),
            ("contracts/claim.py", dynamic, "inferrsi.contracts.claim has a dynamic import"),
            # #451 C2: the path rules import no core, and never the Apps mkdir module.
            (
                "contracts/evidence.py",
                "from inferrsi.apps import evidence_layout\n",
                "inferrsi.contracts.evidence imports inferrsi.apps.evidence_layout",
            ),
            (
                "contracts/evidence.py",
                "from inferrsi.apps.storage import evidence_layout\n",
                "inferrsi.contracts.evidence imports inferrsi.apps.storage",
            ),
            (
                "contracts/evidence.py",
                "from ..harness import api\n",
                "inferrsi.contracts.evidence imports inferrsi.harness.api",
            ),
            (
                "contracts/evidence.py",
                "from . import runspec\n",
                "inferrsi.contracts.evidence imports inferrsi.contracts.runspec",
            ),
            ("contracts/evidence.py", dynamic, "inferrsi.contracts.evidence has a dynamic import"),
        )
        for path, source, expected in cases:
            with self.subTest(expected=expected):
                report = _report(
                    {"apps/evidence_layout.py": "VALUE = 1\n", path: source}
                )
                self.assertTrue(_violated(report, expected), report.violations)

    def test_apps_directory_creation_is_not_a_contracts_module(self) -> None:
        # #451 C2: mkdir stays in Apps. Directory creation belongs to Apps.
        self.assertIn("inferrsi.contracts.evidence", support.CONTRACTS_MODULES)
        self.assertEqual(len(support.CONTRACTS_MODULES), 6)
        self.assertFalse(
            [name for name in support.CONTRACTS_MODULES if "evidence_layout" in name]
        )
        clean = _report(
            {
                "apps/evidence_layout.py": (
                    "from inferrsi.contracts.evidence import evidence_subpaths\n"
                )
            }
        )
        self.assertEqual(clean.violations, ())
        report = _report({"contracts/evidence_layout.py": "from pathlib import Path\n"})
        self.assertTrue(
            _violated(
                report, "inferrsi.contracts.evidence_layout is not a declared contracts module"
            ),
            report.violations,
        )

    def test_core_reached_through_the_package_still_fails_its_importers(self) -> None:
        # The package grants no path: a core import inside it fails every closure that
        # loads it, here a new H entry and the Knowledge module that uses the encoder.
        report = _report(
            {
                "contracts/json_v1.py": "from inferrsi.apps import main\n",
                "harness/api.py": "from inferrsi.contracts import json_v1\n",
            }
        )
        for importer in ("inferrsi.harness.api", K_OPERATIONS):
            with self.subTest(importer=importer):
                self.assertTrue(
                    _violated(report, f"{importer} reaches inferrsi.apps"), report.violations
                )
        self.assertFalse(report.new_core_closure_isolated)


class HarnessEntryTest(unittest.TestCase):
    """A01-3: no harness module reaches Knowledge through an old root shell."""

    def test_new_h_entry_through_old_shell_fails(self) -> None:
        cases = (
            (
                "harness/api.py",
                "from inferrsi.knowledge_operations import KnowledgeReader\n",
                "inferrsi.harness.api reaches inferrsi.knowledge_operations",
            ),
            (
                "harness/records/__init__.py",
                "from ...catalog import search_knowledge\n",
                "inferrsi.harness.records reaches inferrsi.catalog",
            ),
            (
                "harness/execution_service.py",
                "from inferrsi.research import research_knowledge\n",
                "inferrsi.harness.execution_service reaches inferrsi.research",
            ),
        )
        for path, source, expected in cases:
            with self.subTest(path=path):
                report = _report({path: source})
                self.assertTrue(_violated(report, expected), report.violations)

    def test_entry_labels_are_not_inferred_as_paths(self) -> None:
        # A guessed run_store path is not a new H entry just because the
        # label exists, but it is still a harness module: importing an old
        # Knowledge leaf is a violation.
        report = _report(
            {"harness/records/__init__.py": "from ...catalog import search_knowledge\n"},
            h_entries=("inferrsi.harness.api",),
        )
        self.assertTrue(
            _violated(report, "inferrsi.harness.records reaches inferrsi.catalog"),
            report.violations,
        )

    def test_non_entry_harness_module_cannot_reach_an_old_leaf(self) -> None:
        cases = (
            (
                "from ..knowledge_operations import KnowledgeReader\n",
                "inferrsi.harness.runner reaches inferrsi.knowledge_operations",
            ),
            (
                "from inferrsi.catalog import search_knowledge\n",
                "inferrsi.harness.runner reaches inferrsi.catalog",
            ),
        )
        for source, expected in cases:
            with self.subTest(expected=expected):
                report = _report({"harness/runner.py": source})
                self.assertTrue(_violated(report, expected), report.violations)

    def test_former_residual_edge_fails_for_its_importer_and_dependents(self) -> None:
        # The edge that S01 removed has no exemption left: the importer fails,
        # and so does every harness module that reaches the leaf through it.
        tree = {
            "harness/skill_evaluation.py": "from ..knowledge_operations import KnowledgeReader\n",
            "harness/improvement.py": "from . import skill_evaluation\n",
        }
        report = _report(tree)
        self.assertIn(
            "inferrsi.harness.skill_evaluation reaches inferrsi.knowledge_operations: "
            "inferrsi.harness.skill_evaluation -> inferrsi.knowledge_operations",
            report.violations,
        )
        self.assertIn(
            "inferrsi.harness.improvement reaches inferrsi.knowledge_operations: "
            "inferrsi.harness.improvement -> inferrsi.harness.skill_evaluation"
            " -> inferrsi.knowledge_operations",
            report.violations,
        )
        self.assertNotIn("residual", blocker_kinds(report))
        self.assertFalse(report.isolation_complete)
        entry = "from inferrsi.harness import skill_evaluation\n"
        granted = _report({**tree, "harness/api.py": entry})
        self.assertIn(
            "inferrsi.harness.api reaches inferrsi.knowledge_operations: inferrsi.harness.api"
            " -> inferrsi.harness.skill_evaluation -> inferrsi.knowledge_operations",
            granted.violations,
        )
        self.assertFalse(granted.new_core_closure_isolated)

    def test_submodule_import_traverses_parent_package_init(self) -> None:
        parent = {
            "bridge/__init__.py": "from inferrsi.knowledge_operations import KnowledgeReader\n",
            "bridge/safe.py": "VALUE = 1\n",
        }
        cases = (
            ("import inferrsi.bridge.safe\n", "import package.submodule"),
            ("from inferrsi.bridge import safe\n", "from package import submodule"),
        )
        for source, form in cases:
            with self.subTest(form=form):
                report = _report({**parent, "harness/api.py": source})
                self.assertTrue(
                    _violated(
                        report,
                        "inferrsi.harness.api reaches inferrsi.knowledge_operations",
                    ),
                    report.violations,
                )
                self.assertFalse(report.new_core_closure_isolated)

    def test_transitive_path_through_root_helpers_fails(self) -> None:
        report = _report(
            {
                "harness/runner.py": "from inferrsi import helper_a\n",
                "helper_a.py": "from inferrsi import helper_b\n",
                "helper_b.py": (
                    "from inferrsi.knowledge_operations import KnowledgeReader\n"
                ),
            }
        )
        self.assertIn(
            "inferrsi.harness.runner reaches inferrsi.knowledge_operations: "
            "inferrsi.harness.runner -> inferrsi.helper_a -> inferrsi.helper_b"
            " -> inferrsi.knowledge_operations",
            report.violations,
        )

    def test_old_leaf_detection_is_not_sort_dependent(self) -> None:
        # A second path to the same leaf is found whichever edge is walked first.
        direct = {
            "harness/skill_evaluation.py": (
                "from ..knowledge_operations import KnowledgeReader\n"
            )
        }
        for name in ("aa_bridge", "zz_bridge"):
            with self.subTest(name=name):
                report = _report(
                    {
                        **direct,
                        "knowledge_operations.py": _shell("inferrsi.knowledge_operations"),
                        f"{name}.py": "from . import knowledge_operations\n",
                        "harness/runner.py": (
                            f"from . import skill_evaluation\nfrom .. import {name}\n"
                        ),
                    }
                )
                for module in ("runner", "skill_evaluation"):
                    self.assertTrue(
                        _violated(
                            report,
                            f"inferrsi.harness.{module} reaches inferrsi.knowledge_operations",
                        ),
                        report.violations,
                    )

    def test_h_entry_own_parent_init_is_walked(self) -> None:
        # Importing a new H entry executes its package init even when the
        # entry body has no imports.
        leak = {
            "harness/skill_evaluation.py": (
                "from ..knowledge_operations import KnowledgeReader\n"
            ),
            "harness/__init__.py": "from . import skill_evaluation\n",
        }
        expected = (
            "inferrsi.harness.api reaches inferrsi.knowledge_operations: "
            "inferrsi.harness.api -> inferrsi.harness -> "
            "inferrsi.harness.skill_evaluation -> inferrsi.knowledge_operations"
        )
        isolated = _report({**leak, "harness/api.py": "VALUE = 1\n"})
        self.assertIn(expected, isolated.violations)
        self.assertFalse(isolated.new_core_closure_isolated)
        sibling = _report(
            {
                **leak,
                "harness/util.py": "X = 1\n",
                "harness/api.py": "from . import util\n",
            }
        )
        self.assertIn(expected, sibling.violations)
        self.assertFalse(sibling.new_core_closure_isolated)

    def test_non_entry_own_parent_init_is_walked(self) -> None:
        # A non-entry with no imports of its own still reaches the old leaf
        # through the package init, and fails like an entry does.
        report = _report(
            {
                "harness/skill_evaluation.py": (
                    "from ..knowledge_operations import KnowledgeReader\n"
                ),
                "harness/__init__.py": "from . import skill_evaluation\n",
                "harness/runner.py": "VALUE = 1\n",
                "harness/api.py": "VALUE = 1\n",
            }
        )
        for module in ("runner", "api"):
            self.assertIn(
                f"inferrsi.harness.{module} reaches inferrsi.knowledge_operations: "
                f"inferrsi.harness.{module} -> inferrsi.harness -> "
                "inferrsi.harness.skill_evaluation -> inferrsi.knowledge_operations",
                report.violations,
            )

    def test_core_submodule_walk_includes_own_package_init(self) -> None:
        # Knowledge, benchmark, and apps package inits are already starts
        # under the same core rule, so a leak in those inits was already
        # detected from the package. Own-parent edges also attribute the
        # path from a submodule that Python actually loaded.
        cases = (
            (
                {
                    "knowledge/__init__.py": "from inferrsi import catalog\n",
                    "knowledge/catalog.py": "VALUE = 1\n",
                },
                "inferrsi.knowledge.catalog reaches inferrsi.catalog: "
                "inferrsi.knowledge.catalog -> inferrsi.knowledge -> inferrsi.catalog",
            ),
            (
                {
                    "benchmark/__init__.py": "from inferrsi import catalog\n",
                    "benchmark/probe.py": "VALUE = 1\n",
                },
                "inferrsi.benchmark.probe reaches inferrsi.catalog: "
                "inferrsi.benchmark.probe -> inferrsi.benchmark -> inferrsi.catalog",
            ),
            (
                {
                    "apps/__init__.py": "from inferrsi import catalog\n",
                    "apps/main.py": "VALUE = 1\n",
                },
                "inferrsi.apps.main reaches inferrsi.catalog: "
                "inferrsi.apps.main -> inferrsi.apps -> inferrsi.catalog",
            ),
        )
        for changes, expected in cases:
            with self.subTest(expected=expected):
                # ``from inferrsi import catalog`` names a module only while the file exists.
                report = _report({"catalog.py": _shell("inferrsi.catalog"), **changes})
                self.assertIn(expected, report.violations, report.violations)

    # This test is about the Harness edge rule. The synthetic Infra and Model packages it
    # builds are retired names since #498, which test_target_module_import_gate.py covers, so
    # the retirement rule is switched off here and nothing else changes.
    @mock.patch.object(support, "RETIRED_MODULES", frozenset())
    def test_returning_skill_evaluation_infra_edge_fails(self) -> None:
        # #410 counterexample: S01 removed skill_evaluation -> infra.artifacts.
        # Adding it back is reported hit by hit and keeps isolation false.
        tree = {
            "infra/__init__.py": "",
            "infra/artifacts.py": "VALUE = 1\n",
            "harness/skill_evaluation.py": "from ..infra.artifacts import VALUE\n",
            "harness/improvement.py": "from . import skill_evaluation\n",
        }
        cleared = _report({}, manifest=EMPTY_ALLOWLIST, base=CLEARED_TREE)
        self.assertEqual(cleared.harness_model_infra, ())
        self.assertTrue(cleared.isolation_complete)
        report = _report(tree, manifest=EMPTY_ALLOWLIST, base=CLEARED_TREE)
        self.assertEqual(
            report.harness_model_infra,
            (
                "inferrsi.harness.improvement -> inferrsi.harness.skill_evaluation"
                " -> inferrsi.infra",
                "inferrsi.harness.improvement -> inferrsi.harness.skill_evaluation"
                " -> inferrsi.infra.artifacts",
                "inferrsi.harness.skill_evaluation -> inferrsi.infra",
                "inferrsi.harness.skill_evaluation -> inferrsi.infra.artifacts",
            ),
        )
        self.assertEqual(
            report.blockers,
            (
                "harness reaches model/infra: inferrsi.harness.improvement -> "
                "inferrsi.harness.skill_evaluation -> inferrsi.infra (4 hits)",
            ),
        )
        self.assertFalse(report.isolation_complete)

    # This test is about the Harness edge rule. The synthetic Infra and Model packages it
    # builds are retired names since #498, which test_target_module_import_gate.py covers, so
    # the retirement rule is switched off here and nothing else changes.
    @mock.patch.object(support, "RETIRED_MODULES", frozenset())
    def test_returning_r2_harness_infra_edges_fail(self) -> None:
        # #412 R2 removed infra.artifacts from six Harness modules. Putting one edge back,
        # relative or absolute, top-level or inside a function, reports both the package
        # and the module edge; reaching another infra module or model also counts.
        infra = {"infra/__init__.py": "", "infra/artifacts.py": "VALUE = 1\n",
                 "infra/other.py": "VALUE = 1\n", "model/__init__.py": "",
                 "model/metrics.py": "VALUE = 1\n"}
        primitives = {"harness/records/artifact_primitives.py": "VALUE = 1\n",
                      "harness/records/atomic_json.py": "VALUE = 1\n"}
        modules = ("agent_sessions", "candidates", "optimization", "optimization_session",
                   "project", "task_protocol")
        clean = {f"harness/{name}.py": "from .records.artifact_primitives import VALUE\n"
                 for name in modules}
        cleared = _report({**infra, **primitives, **clean}, manifest=EMPTY_ALLOWLIST,
                          base=CLEARED_TREE)
        self.assertEqual(cleared.harness_model_infra, ())
        self.assertTrue(cleared.isolation_complete)
        sources = (
            ("from ..infra.artifacts import VALUE\n", "inferrsi.infra.artifacts"),
            ("def late():\n    from inferrsi.infra.artifacts import VALUE\n",
             "inferrsi.infra.artifacts"),
            # #498 retired infra.processes and infra.commands; other is a synthetic Infra module.
            ("from ..infra import other\n", "inferrsi.infra.other"),
            ("from inferrsi.model import metrics\n", "inferrsi.model.metrics"),
        )
        for name in modules:
            for source, target in sources:
                with self.subTest(module=name, source=source):
                    report = _report({**infra, **primitives, **clean,
                                      f"harness/{name}.py": source},
                                     manifest=EMPTY_ALLOWLIST, base=CLEARED_TREE)
                    package = target.rsplit(".", 1)[0]
                    self.assertEqual(
                        report.harness_model_infra,
                        (f"inferrsi.harness.{name} -> {package}",
                         f"inferrsi.harness.{name} -> {target}"),
                    )
                    self.assertFalse(report.isolation_complete)

    def test_mixed_harness_tree_is_not_an_isolated_core(self) -> None:
        tree = {"__init__.py": "", "harness/__init__.py": "", "harness/runner.py": "VALUE = 1\n"}
        report = _report({}, base=tree)
        self.assertEqual(report.violations, ())
        self.assertFalse(report.new_core_closure_isolated)
        self.assertFalse(report.isolation_complete)


class StagedIsolationTest(unittest.TestCase):
    """A01-4: any one trigger keeps overall isolation false."""

    def test_overall_true_only_when_every_trigger_is_cleared(self) -> None:
        report = _report({}, manifest=EMPTY_ALLOWLIST, base=CLEARED_TREE)
        self.assertEqual(report.blockers, ())
        self.assertTrue(report.new_core_closure_isolated)
        self.assertTrue(report.isolation_complete)

    # Three triggers build synthetic Infra and Model packages. Those are retired names since
    # #498, which test_target_module_import_gate.py covers, so the retirement rule is
    # switched off here and the trigger counts stay about the Harness edge and the others.
    @mock.patch.object(support, "RETIRED_MODULES", frozenset())
    def test_each_trigger_alone_keeps_overall_false(self) -> None:
        triggers = (
            ("absent: knowledge/", {"knowledge/__init__.py": None, "knowledge/catalog.py": None},
             EMPTY_ALLOWLIST),
            ("absent: benchmark/", {"benchmark/__init__.py": None}, EMPTY_ALLOWLIST),
            ("absent: apps/", {"apps/__init__.py": None, "apps/main.py": None}, EMPTY_ALLOWLIST),
            ("allowlist: 9 compatibility pairs", {}, STAGED),
            (
                "harness reaches model/infra: inferrsi.harness.skill_evaluation"
                " -> inferrsi.infra",
                {
                    "infra/__init__.py": "",
                    "infra/artifacts.py": "VALUE = 1\n",
                    "harness/skill_evaluation.py": "from ..infra.artifacts import VALUE\n",
                },
                EMPTY_ALLOWLIST,
            ),
            (
                "harness reaches model/infra: inferrsi.harness.runner -> inferrsi.infra",
                {
                    "infra/__init__.py": "",
                    "infra/local.py": "",
                    "harness/runner.py": "from inferrsi.infra import local\n",
                },
                EMPTY_ALLOWLIST,
            ),
            (
                "harness reaches model/infra: inferrsi.harness.runner -> inferrsi.bridge"
                " -> inferrsi.model",
                {
                    # A root helper that is not a retired name: the path alone blocks.
                    "bridge.py": "from inferrsi.model import metrics\n",
                    "model/__init__.py": "",
                    "model/metrics.py": "",
                    "harness/runner.py": "from inferrsi import bridge\n",
                },
                EMPTY_ALLOWLIST,
            ),
        )
        for expected, changes, manifest in triggers:
            with self.subTest(expected=expected):
                report = _report(changes, manifest=manifest, base=CLEARED_TREE)
                self.assertEqual(report.violations, ())
                self.assertEqual(len(report.blockers), 1, report.blockers)
                self.assertTrue(report.blockers[0].startswith(expected), report.blockers)
                self.assertFalse(report.isolation_complete)

    def test_empty_package_directories_are_unscannable(self) -> None:
        # Empty knowledge/, benchmark/, and apps/ directories must not make
        # isolation_complete true; an empty directory is not a scannable package.
        files = {
            relative: source
            for relative, source in CLEARED_TREE.items()
            if not relative.startswith(("knowledge/", "benchmark/", "apps/"))
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative, source in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            for name in ("knowledge", "benchmark", "apps"):
                (root / name).mkdir()
            report = first_wave_report(root, EMPTY_ALLOWLIST, SYNTHETIC_H_ENTRIES)
        self.assertFalse(report.isolation_complete)
        for name in ("knowledge", "benchmark", "apps"):
            self.assertIn(f"unscannable: {name}/", report.blockers)
            self.assertNotIn(f"absent: {name}/", report.blockers)

    def test_clean_new_core_graph_never_sets_overall_true(self) -> None:
        for report, kinds in (
            (_staged({}), {"allowlist"}),
        ):
            with self.subTest(kinds=kinds):
                self.assertEqual(report.violations, ())
                self.assertTrue(report.new_core_closure_isolated)
                self.assertEqual(blocker_kinds(report), kinds)
                self.assertFalse(report.isolation_complete)


if __name__ == "__main__":
    unittest.main()
