"""Guard new Knowledge / Harness / Benchmark / Apps import edges.

A passing scan is not module isolation. The target packages are not all
present, and the existing ``inferrsi.harness`` tree still mixes other layers.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "inferrsi"
NEW_CORES = ("knowledge", "benchmark", "apps")
FORBIDDEN_FROM_LEGACY = tuple(f"inferrsi.{name}" for name in NEW_CORES)


def _imported_modules(path: Path) -> list[str]:
    return _modules_in_source(
        path.read_text(encoding="utf-8"),
        ["inferrsi", *path.relative_to(ROOT).parts[:-1]],
    )


def _modules_in_source(source: str, package_parts: list[str]) -> list[str]:
    package = ".".join(package_parts)
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join(keep + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            names.append(base)
    return names


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def cross_core_violations(root: Path = ROOT) -> list[str]:
    """Imports that would connect the target cores outside Apps."""
    violations = []
    for path in sorted(root.rglob("*.py")):
        importer = path.relative_to(root).parts[0] if path.parent != root else ""
        for module in _imported_modules(path):
            if importer == "apps":
                continue
            for prefix in FORBIDDEN_FROM_LEGACY:
                if _matches(module, prefix):
                    violations.append(f"{path.relative_to(root)} imports {module}")
            if importer in ("knowledge", "benchmark"):
                for other in ("inferrsi.harness", "inferrsi.apps", "inferrsi.knowledge", "inferrsi.benchmark"):
                    own = f"inferrsi.{importer}"
                    if other != own and _matches(module, other):
                        violations.append(f"{path.relative_to(root)} imports {module}")
    return violations


def isolation_complete(root: Path = ROOT) -> bool:
    """True only when the target packages exist and the legacy mix is gone.

    This slice never sets that condition. Callers must not treat an empty
    violation list as isolation.
    """
    if any(not (root / name).is_dir() for name in NEW_CORES):
        return False
    harness = root / "harness"
    if not harness.is_dir():
        return False
    for path in harness.rglob("*.py"):
        for module in _imported_modules(path):
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

    def test_detector_flags_a_new_core_import_outside_apps(self) -> None:
        def forbidden(importer: str, source: str) -> bool:
            if importer == "apps":
                return False
            return any(
                _matches(module, prefix)
                for module in _modules_in_source(source, ["inferrsi", importer])
                for prefix in FORBIDDEN_FROM_LEGACY
            )

        self.assertTrue(forbidden("harness", "import inferrsi.knowledge\n"))
        self.assertFalse(forbidden("apps", "import inferrsi.knowledge\n"))

    def test_layout_doc_states_the_same_limit(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath("docs/module-layout.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Isolation stays false", text)


if __name__ == "__main__":
    unittest.main()
