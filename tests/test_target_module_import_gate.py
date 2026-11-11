"""Guard new Knowledge / Harness / Benchmark / Apps import edges.

A passing scan is not module isolation. The target packages are not all
present, and the existing ``inferrsi.harness`` tree still mixes other layers.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "inferrsi"
NEW_CORES = ("knowledge", "benchmark", "apps")
CORE_NAMES = ("knowledge", "harness", "benchmark", "apps")
LEGACY_MONITORING_IMPORTS = {
    "cli.py": {
        "inferrsi.apps.views.dashboard": ("write_dashboard",),
        "inferrsi.apps.views.live": ("serve_dashboard",),
    },
    "harness/dashboard.py": {
        "inferrsi.apps.views.dashboard": (
            "dashboard_snapshot", "render_dashboard", "write_dashboard",
        ),
    },
    "harness/dashboard_data.py": {
        "inferrsi.apps.views.dashboard_data": ("load_dashboard",),
        "inferrsi.apps.views.trace": ("EVENT_TYPES", "PHASE_STAGES"),
    },
    "harness/dashboard_external.py": {
        "inferrsi.apps.views.dashboard_external": ("external_record", "metric_chart"),
    },
    "harness/dashboard_live.py": {
        "inferrsi.apps.views.live": ("DashboardHandler", "DashboardServer", "serve_dashboard"),
    },
    "harness/dashboard_timeline.py": {
        "inferrsi.apps.views.dashboard_timeline": ("temporal_chart",),
    },
}
MONITORING_SHIM_FILES = tuple(
    path for path in LEGACY_MONITORING_IMPORTS if path.startswith("harness/")
)
MONITORING_SHIMS = {
    "inferrsi." + path.removesuffix(".py").replace("/", ".")
    for path in MONITORING_SHIM_FILES
}


def _modules_in_source(
    source: str, package_parts: list[str], forwards: dict[str, tuple[str, ...]],
) -> list[str]:
    """Resolve import targets, including ``from package import name`` forms."""
    package = ".".join(package_parts)
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = package.split(".")[
                    : len(package.split(".")) - node.level + 1
                ]
                base = ".".join(keep + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            allowed = forwards.get(base, ())
            if all(alias.name in allowed for alias in node.names):
                continue
            if base:
                names.append(base)
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                names.append(candidate)
    return names


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _core_of(module: str) -> str | None:
    for name in CORE_NAMES:
        if _matches(module, f"inferrsi.{name}"):
            return name
    return None


def _imported_modules(
    path: Path, root: Path, *, allow_monitoring_forwards: bool = False,
) -> list[str]:
    relative = path.relative_to(root)
    forwards = LEGACY_MONITORING_IMPORTS.get(relative.as_posix(), {}) if (
        allow_monitoring_forwards
    ) else {}
    return _modules_in_source(
        path.read_text(encoding="utf-8"),
        ["inferrsi", *relative.parts[:-1]],
        forwards,
    )


def cross_core_violations(root: Path = ROOT) -> list[str]:
    """One message per forbidden importer and target core.

    Same-core imports, including relative imports rewritten to absolute
    names, are allowed. Apps may import the other cores. The CLI and the
    monitoring compatibility shims have exact forwarding exceptions. Core
    modules and Apps may not import those legacy shims.
    """
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        importer = relative.parts[0] if len(relative.parts) > 1 else ""
        filename = relative.as_posix()
        for module in _imported_modules(path, root, allow_monitoring_forwards=True):
            if importer in CORE_NAMES and any(_matches(module, shim) for shim in MONITORING_SHIMS):
                found.add((filename, module))
                continue
            target = _core_of(module)
            if target is None or importer == "apps" or importer == target:
                continue
            if target == "harness" and importer not in ("knowledge", "benchmark"):
                continue
            found.add((filename, f"inferrsi.{target}"))
    return [f"{path} imports {target}" for path, target in sorted(found)]


def isolation_complete(root: Path = ROOT) -> bool:
    """True only after the target packages exist and the legacy mix is gone."""
    if any(not (root / name).is_dir() for name in NEW_CORES):
        return False
    if any((root / path).is_file() for path in MONITORING_SHIM_FILES):
        return False
    harness = root / "harness"
    if not harness.is_dir():
        return False
    for path in harness.rglob("*.py"):
        for module in _imported_modules(path, root):
            if _matches(module, "inferrsi.model") or _matches(module, "inferrsi.infra"):
                return False
    return not cross_core_violations(root)


class TargetModuleImportGateTest(unittest.TestCase):
    def test_no_new_cross_core_imports(self) -> None:
        self.assertEqual(cross_core_violations(), [])

    def test_clean_scan_is_not_isolation(self) -> None:
        absent = [name for name in NEW_CORES if not (ROOT / name).is_dir()]
        self.assertEqual(absent, ["knowledge", "benchmark"])
        self.assertTrue((ROOT / "harness").is_dir())
        self.assertTrue((ROOT / "contracts.py").is_file())
        self.assertFalse((ROOT / "contracts").is_dir())
        self.assertFalse(isolation_complete())

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

    def test_monitoring_forwards_allow_only_their_existing_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples = {
                "cli.py": (
                    "from .apps.views.dashboard import write_dashboard\n"
                    "import inferrsi.apps.views.dashboard as dashboard\n"
                ),
                "harness/dashboard.py": "from ..apps.views.dashboard import render_dashboard\n",
                "harness/dashboard_live.py": "from ..apps.views.live import *\n",
                "harness/dashboard_data.py": "from ..apps.views.trace import _read_events\n",
                "harness/core.py": "from .dashboard import render_dashboard\n",
            }
            for relative, source in samples.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            self.assertEqual(cross_core_violations(root), [
                "cli.py imports inferrsi.apps",
                "harness/core.py imports inferrsi.harness.dashboard",
                "harness/core.py imports inferrsi.harness.dashboard.render_dashboard",
                "harness/dashboard_data.py imports inferrsi.apps",
                "harness/dashboard_live.py imports inferrsi.apps",
            ])

    def test_legacy_monitoring_shims_only_reexport(self) -> None:
        for path in MONITORING_SHIM_FILES:
            module = ast.parse((ROOT / path).read_text(encoding="utf-8"))
            self.assertIsNotNone(ast.get_docstring(module), path)
            for node in module.body[1:]:
                self.assertIsInstance(node, ast.ImportFrom, path)
                self.assertTrue(all(name.asname == name.name for name in node.names), path)


if __name__ == "__main__":
    unittest.main()
