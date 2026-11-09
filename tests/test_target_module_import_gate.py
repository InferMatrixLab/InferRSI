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


def _modules_in_source(source: str, package_parts: list[str]) -> list[str]:
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
            if base:
                names.append(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
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


def _imported_modules(path: Path, root: Path) -> list[str]:
    relative = path.relative_to(root)
    return _modules_in_source(
        path.read_text(encoding="utf-8"),
        ["inferrsi", *relative.parts[:-1]],
    )


def cross_core_violations(root: Path = ROOT) -> list[str]:
    """One message per forbidden importer and target core.

    Same-core imports, including relative imports rewritten to absolute
    names, are allowed. Apps may import the other cores. Every other import
    of ``inferrsi.knowledge``, ``inferrsi.benchmark``, or ``inferrsi.apps``
    is forbidden, as is Knowledge or Benchmark importing Harness.
    """
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        importer = relative.parts[0] if len(relative.parts) > 1 else ""
        for module in _imported_modules(path, root):
            target = _core_of(module)
            if target is None or importer == "apps" or importer == target:
                continue
            if target == "harness" and importer not in ("knowledge", "benchmark"):
                continue
            found.add((relative.as_posix(), target))
    return [f"{path} imports inferrsi.{target}" for path, target in sorted(found)]


def isolation_complete(root: Path = ROOT) -> bool:
    """True only after the target packages exist and the legacy mix is gone."""
    if any(not (root / name).is_dir() for name in NEW_CORES):
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
        self.assertEqual(absent, ["knowledge", "benchmark", "apps"])
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


if __name__ == "__main__":
    unittest.main()
