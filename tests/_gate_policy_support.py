"""First-wave isolation gate helpers (P0b, revised through #408 A2).

Imported by the import-gate and isolation-policy tests. This is a test
support module, not a runtime package.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "src" / "inferrsi"
MANIFEST = REPO / "docs" / "legacy-knowledge-manifest.json"
NEW_CORES = ("knowledge", "benchmark", "apps")
CORE_NAMES = ("knowledge", "harness", "benchmark", "apps")
# No root file is application assembly. A1 (#408) moved the CLI and its parser into
# ``apps/cli/``, and A2 (#408) moved the task launcher to ``apps/benchmark_operations.py``.
# With that last move the ``APPLICATION_ENTRIES`` listing is gone: Apps is the
# ``inferrsi.apps`` package by its first path segment and nothing else, so a root
# ``cli.py``, ``arguments.py`` or ``benchmark_operations.py`` that returns is an unlisted
# flat module.
# #408 A1, permanent: ``python -m inferrsi`` runs root ``__main__.py``, which stays in
# the package root and hands over to the canonical Apps CLI. The gate admits that one
# statement and nothing wider: this exact root file, this exact target module and this
# exact name, bound by a plain module-level ``from <target> import <name>`` line. It is
# not an application entry, so the file is never treated as Apps. Every
# other import in it of Apps, Knowledge or Benchmark fails as in any flat module. So do
# an alias, a second name, a star import, the target imported as a module object, a
# module beside or below the target, and the same line below module level. No other
# file is covered, in the root or under a package.
MODULE_ENTRY = "__main__.py"
MODULE_ENTRY_DELEGATION = ("inferrsi.apps.cli", "main")
# Reviewed execution boundaries: owner function (or module scope) and the exact
# local spec variable. They execute task resources/candidate code, not a hidden
# core compatibility import. Their presence keeps isolation incomplete.
RESOURCE_LOADERS = {
    "inferrsi.harness.task_protocol": ("protocol", "spec"),
    "inferrsi.benchmark.tasks.moe-forward-npu.benchmark": ("<module>", "_process_spec"),
    "inferrsi.benchmark.tasks.moe-forward-npu.grader": ("load", "spec"),
    "inferrsi.benchmark.tasks.qwen21-denoise-npu.benchmark": ("load", "spec"),
    "inferrsi.benchmark.tasks.qwen3-tts-npu.benchmark": ("<module>", "_evaluation_spec"),
}
# #412 R1 deleted these eleven root modules: the seven Knowledge shells, the three
# old-run forwarders and the root inspection binding. None is registered any more.
# A file that returns under one of these names is a violation by itself, and every
# checked closure still treats the name as an old root leaf it may not reach.
RETIRED_BY_R1 = frozenset(
    {
        "inferrsi._skill_selection",
        "inferrsi._source_snapshot",
        "inferrsi.catalog",
        "inferrsi.knowledge_operations",
        "inferrsi.knowledge_store",
        "inferrsi.research",
        "inferrsi.skill_catalog",
        "inferrsi.evaluation",
        "inferrsi.execution",
        "inferrsi.reporting",
        "inferrsi.inspection",
    }
)
# #408 A1 deleted the root CLI and its parser the same way, with no forwarder or alias.
# The implementation is ``inferrsi.apps.cli`` and ``inferrsi.apps.cli.arguments``.
RETIRED_BY_A1 = frozenset({"inferrsi.cli", "inferrsi.arguments"})
# #408 A2 deleted the root chart renderer and task launcher the same way. The
# implementations are ``inferrsi.apps.views.summary_chart`` and
# ``inferrsi.apps.benchmark_operations``.
RETIRED_BY_A2 = frozenset({"inferrsi.summary_chart", "inferrsi.benchmark_operations"})
# #452 M1 deleted the four root MindIE files the same way. The adapter is the
# ``inferrsi.apps.mindie`` package: ``project``, ``context``, ``mcp`` and ``read_worker``.
RETIRED_BY_M1 = frozenset(
    {
        "inferrsi.mindie_project",
        "inferrsi.mindie_context",
        "inferrsi.mindie_mcp",
        "inferrsi._mindie_read_worker",
    }
)
RETIRED_ROOT_MODULES = RETIRED_BY_R1 | RETIRED_BY_A1 | RETIRED_BY_A2 | RETIRED_BY_M1
# #412 R1, permanent: the one importer of the neutral data leaf outside
# ``inferrsi.knowledge``, with the only name it may bind (D020: Infra reads one pack
# description and reaches no Knowledge or Harness). This is not a manifest
# ``compatibility_pairs`` entry: it never counts toward the allowlist blocker and it
# does not retire. It covers this one module and this one name, bound by a plain
# module-level ``from <leaf> import <name>`` line. Another importer, another name, an
# alias, the leaf imported as a module object, a nested import, a ``sys.modules`` use
# or a dynamic import fails. No ``inferrsi.resources.`` prefix is ever allowed.
# ``technical_leaf.permanent_importers`` in the manifest restates this rule and
# records that it needs formal architecture review.
LEAF_IMPORTERS = {
    "inferrsi.infra.inspection": frozenset({"repository_pack"}),
}
# #408 A1 removed the temporary entry that let root ``arguments.py`` bind REPO_TYPES from
# the leaf, together with its ``temporary leaf importers`` blocker. Nothing replaced it:
# the moved parser reads the same tuple object through ``inferrsi.knowledge.catalog``,
# and an Apps module that names the leaf fails as a second importer like any other.
# New H entries: module paths whose closures count toward the new-core result.
# H01 added ``run_store`` and ``errors``; H02 added the public ``api`` with
# ``execution_service``, ``input_binding`` and ``local_process``.
NEW_H_ENTRIES = (
    "inferrsi.harness.api",
    "inferrsi.harness.errors",
    "inferrsi.harness.execution_service",
    "inferrsi.harness.input_binding",
    "inferrsi.harness.local_process",
    "inferrsi.harness.run_store",
)
# Shared data/byte contracts (#451 C1). This exact module list is the whole package. A
# new module is a reviewed change to this list; an ``inferrsi.contracts.`` prefix never
# exempts anything.
CONTRACTS_PACKAGE = "inferrsi.contracts"
# The P0a canonical encoder; the new K closure may use it and the data leaf.
CANONICAL_ENCODER = "inferrsi.contracts.json_v1"
# The initializer's single import. Python runs the initializer for every contracts
# import, so a module that may use the encoder also loads these two names, and no other.
CONTRACTS_INIT_EXPORT = ("inferrsi.contracts.runspec", "RunSpec")
# #451 C2 adds exactly one module: the evidence segment and path rules. Directory
# creation is ``inferrsi.apps.evidence_layout`` and is not a contracts module.
CONTRACTS_EVIDENCE = "inferrsi.contracts.evidence"
CONTRACTS_MODULES = frozenset(
    {
        CONTRACTS_PACKAGE,
        CANONICAL_ENCODER,
        CONTRACTS_INIT_EXPORT[0],
        "inferrsi.contracts.claim",
        CONTRACTS_EVIDENCE,
    }
)
# Names that load or build modules at run time. Any use fails closed.
# P0b scans only these three spellings; getattr, exec, eval, runpy, and
# pkgutil are intentionally out of scope here.
DYNAMIC_IMPORT_NAMES = frozenset({"__import__", "import_module", "module_from_spec"})


def _from_base(node: ast.ImportFrom, package: str) -> str:
    """Absolute module named by an ``ImportFrom`` inside ``package``."""
    if not node.level:
        return node.module or ""
    parts = package.split(".")
    keep = parts[: len(parts) - node.level + 1]
    return ".".join(keep + ([node.module] if node.module else []))


def _is_entry_delegation(node: ast.stmt, package: str) -> bool:
    """The module entry's one admitted statement, in its exact plain shape."""
    module, name = MODULE_ENTRY_DELEGATION
    return (
        isinstance(node, ast.ImportFrom)
        and _from_base(node, package) == module
        and [(alias.name, alias.asname) for alias in node.names] == [(name, None)]
    )


def _modules_in_source(
    source: str, package_parts: list[str], module_entry: bool = False
) -> list[str]:
    """Resolve import targets, including ``from package import name`` forms.

    For the module entry only, its admitted delegation statement is left out where it
    stands at module level. Every other import in that file is resolved as usual.
    """
    package = ".".join(package_parts)
    tree = ast.parse(source)
    admitted = {
        id(node)
        for node in tree.body
        if module_entry and _is_entry_delegation(node, package)
    }
    names: list[str] = []
    for node in ast.walk(tree):
        if id(node) in admitted:
            continue
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
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
        module_entry=relative.as_posix() == MODULE_ENTRY,
    )


def _module_name(relative: Path) -> str:
    parts = relative.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(("inferrsi", *parts))


def _module_index(root: Path) -> dict[str, Path]:
    return {_module_name(path.relative_to(root)): path for path in sorted(root.rglob("*.py"))}


def _resolve(name: str, modules: dict[str, Path]) -> str:
    """Map ``module.attribute`` to its module; keep submodule names."""
    parent = name.rpartition(".")[0]
    if name not in modules and parent in modules and modules[parent].name != "__init__.py":
        return parent
    return name


def cross_core_violations(
    root: Path = ROOT, allowed: frozenset[tuple[str, str]] = frozenset()
) -> list[str]:
    """One message per forbidden importer and target core.

    Same-core imports, including relative imports rewritten to absolute
    names, are allowed. Apps may import the other cores. Every other import
    of ``inferrsi.knowledge``, ``inferrsi.benchmark``, or ``inferrsi.apps``
    is forbidden, as is Knowledge or Benchmark importing Harness. ``allowed``
    holds exact (importer module, target module) pairs; a prefix never counts.
    The one other admission is the ``MODULE_ENTRY`` delegation statement: that
    exact statement in that exact root file, and no other import in it.
    """
    modules = _module_index(root)
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        importer = relative.parts[0] if len(relative.parts) > 1 else ""
        importer_module = _module_name(relative)
        for module in _imported_modules(path, root):
            target = _core_of(module)
            if target is None or importer == "apps" or importer == target:
                continue
            if target == "harness" and importer not in ("knowledge", "benchmark"):
                continue
            if (importer_module, _resolve(module, modules)) in allowed:
                continue
            found.add((relative.as_posix(), target))
    return [f"{path} imports inferrsi.{target}" for path, target in sorted(found)]


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def exact_pairs(manifest: dict[str, Any]) -> frozenset[tuple[str, str]]:
    """The exact (importer module, target module) compatibility allowlist."""
    return frozenset(
        (f"inferrsi.{item['importer']}", item["target"])
        for item in manifest["compatibility_pairs"]
    )


def shell_sources(manifest: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    """Staged root shell -> {exact target: names that shell may re-export}.

    Empty since #412 R1 emptied ``compatibility_pairs``. A pair that review stages
    again is held to the same shell shape as before.
    """
    leaf = manifest["technical_leaf"]["module"]
    leaf_names = set(manifest["technical_leaf"]["two_symbols"])
    sources: dict[str, dict[str, set[str]]] = {}
    for item in manifest["compatibility_pairs"]:
        if _core_of(item["target"]) == "knowledge":
            exports = item["exports"]
            names = set(exports["public"]) | set(exports["private_used"])
            sources.setdefault(f"inferrsi.{item['importer']}", {})[item["target"]] = names
    for item in manifest["compatibility_pairs"]:
        importer = f"inferrsi.{item['importer']}"
        if item["target"] == leaf and importer in sources:
            sources[importer][leaf] = leaf_names
    return sources


@dataclass(frozen=True)
class _Graph:
    trees: dict[str, ast.Module]
    packages: dict[str, str]
    edges: dict[str, set[str]]


def _package_ancestors(name: str, modules: dict[str, Path]) -> set[str]:
    """Parent packages whose ``__init__`` Python executes on this import.

    Used both for import targets and for the imported module itself. The
    root ``inferrsi`` package init is excluded; it runs for every import
    and is not a business edge.
    """
    parts = name.split(".")
    found: set[str] = set()
    for end in range(2, len(parts)):
        parent = ".".join(parts[:end])
        if parent in modules:
            found.add(parent)
    return found


def _direct_targets(tree: ast.Module, package: str, modules: dict[str, Any]) -> set[str]:
    """Resolved ``inferrsi.*`` targets written in one module, without parent inits."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            for alias in node.names:
                candidate = f"{base}.{alias.name}"
                found.add(candidate if candidate in modules else base)
    return {name for name in found if name.startswith("inferrsi.")}


def _edges(tree: ast.Module, package: str, modules: dict[str, Path]) -> set[str]:
    """Resolved ``inferrsi.*`` targets of every import in one module."""
    resolved = _direct_targets(tree, package, modules)
    ancestors: set[str] = set()
    for name in resolved:
        ancestors.update(_package_ancestors(name, modules))
    return resolved | ancestors


def _scan(root: Path, pairs: frozenset[tuple[str, str]]) -> _Graph:
    """The ``src/inferrsi/**`` transfer graph plus manifest-declared edges."""
    modules = _module_index(root)
    trees = {name: ast.parse(path.read_text(encoding="utf-8")) for name, path in modules.items()}
    packages = {
        name: ".".join(("inferrsi", *path.relative_to(root).parts[:-1]))
        for name, path in modules.items()
    }
    edges = {name: _edges(trees[name], packages[name], modules) for name in modules}
    # Importing a module also executes its own parent package inits, even
    # when the module body has no imports of its own.
    for name in modules:
        edges[name].update(_package_ancestors(name, modules))
    # A declared export edge counts once both ends exist, even if unwritten.
    for importer, target in pairs:
        if importer in modules and target in modules:
            edges[importer].add(target)
    return _Graph(trees, packages, edges)


def _resource_loader(tree: ast.Module, module: str) -> ast.Attribute | None:
    declaration = RESOURCE_LOADERS.get(module)
    if declaration is None:
        return None
    matches = []

    def visit(node, owner="<module>"):
        if isinstance(node, ast.ClassDef):
            owner += ".<class>." + node.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = node.name if owner == "<module>" else owner + "." + node.name
        if (isinstance(node, ast.Call) and owner == declaration[0]
                and ast.unparse(node.func) == "importlib.util.module_from_spec"
                and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Name) and node.args[0].id == declaration[1]):
            matches.append(node.func)
        for child in ast.iter_child_nodes(node):
            visit(child, owner)

    visit(tree)
    return matches[0] if len(matches) == 1 else None


def _has_dynamic_import(tree: ast.Module, module: str = "") -> bool:
    declared = _resource_loader(tree, module)
    for node in ast.walk(tree):
        if node is declared:
            continue
        if isinstance(node, ast.Name) and node.id in DYNAMIC_IMPORT_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in DYNAMIC_IMPORT_NAMES:
            return True
        if isinstance(node, ast.ImportFrom) and any(
            alias.name in DYNAMIC_IMPORT_NAMES for alias in node.names
        ):
            return True
    return False


def _walk(
    start: str, edges: dict[str, set[str]], forbidden: Callable[[str], bool]
) -> tuple[list[str], list[tuple[str, str]]]:
    """Breadth-first closure. Forbidden nodes are reported, not expanded."""
    parents: dict[str, str | None] = {start: None}
    queue = [start]
    expanded: list[str] = []
    hits: list[tuple[str, str]] = []
    for node in queue:  # the queue grows while it is read
        if node != start and forbidden(node):
            chain = [node]
            while parents[chain[-1]] is not None:
                chain.append(parents[chain[-1]])
            hits.append((node, " -> ".join(reversed(chain))))
            continue
        expanded.append(node)
        for target in sorted(edges.get(node, ())):
            if target not in parents:
                parents[target] = node
                queue.append(target)
    return expanded, hits


def _closure_violations(
    start: str, graph: _Graph, forbidden: Callable[[str], bool]
) -> list[str]:
    expanded, hits = _walk(start, graph.edges, forbidden)
    found = [f"{start} reaches {node}: {path}" for node, path in hits]
    found += [
        f"{start} reaches an undeclared dynamic import in {node}"
        for node in expanded
        if node in graph.trees and _has_dynamic_import(graph.trees[node], node)
    ]
    return found


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _assigned_names(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _literal_all(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.value, ast.List)
        and all(
            isinstance(item, ast.Constant) and isinstance(item.value, str)
            for item in node.value.elts
        )
    )


def _shell_errors(
    module: str, tree: ast.Module, package: str, sources: dict[str, set[str]]
) -> list[str]:
    """A01-2: a compatibility shell is docstring, future, listed imports, __all__."""
    errors: list[str] = []
    for index, node in enumerate(tree.body):
        if index == 0 and _is_docstring(node):
            continue
        if isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            if base == "__future__":
                continue
            if base not in sources:
                errors.append(f"{module} has an unlisted import from {base}")
                continue
            for alias in node.names:
                if alias.name == "*":
                    errors.append(f"{module} has a star import from {base}")
                elif alias.asname not in (None, alias.name):
                    errors.append(f"{module} aliases {alias.name} as {alias.asname}")
                elif alias.name not in sources[base]:
                    errors.append(f"{module} imports unlisted name {base}.{alias.name}")
        elif isinstance(node, ast.Import):
            names = ", ".join(alias.name for alias in node.names)
            errors.append(f"{module} has an unlisted import of {names}")
        elif "__all__" in _assigned_names(node):
            if not _literal_all(node):
                errors.append(f"{module} __all__ is not a literal list of constant strings")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == "__getattr__"
        ):
            errors.append(f"{module} defines __getattr__")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            errors.append(f"{module} has a function or class body {node.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            errors.append(f"{module} has a module-level assignment")
        else:
            errors.append(f"{module} has a {type(node).__name__} statement")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        ):
            errors.append(f"{module} touches sys.modules")
            break
    if _has_dynamic_import(tree):
        errors.append(f"{module} has a dynamic import")
    return errors


def _allowed_key(entry: str) -> str:
    """``from M import n`` -> ``M.n``; a bare dotted entry stays as is."""
    if not entry.startswith("from "):
        return entry
    node = ast.parse(entry).body[0]
    return f"{node.module}.{node.names[0].name}"


def _leaf_errors(
    tree: ast.Module, technical_leaf: dict[str, Any], package: str = "inferrsi"
) -> list[str]:
    """The neutral data leaf: listed stdlib imports anywhere, two symbols only.

    ``package`` is the leaf's own package, so a relative import is reported by the
    module it really names.
    """
    module = technical_leaf["module"]
    allowed = {_allowed_key(entry) for entry in technical_leaf["allowed_imports"]}
    symbols = set(technical_leaf["two_symbols"])
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            names = [base if base in allowed else f"{base}.{alias.name}" for alias in node.names]
        else:
            continue
        errors.extend(f"{module} imports {name}" for name in names if name not in allowed)
    if _has_dynamic_import(tree):
        errors.append(f"{module} has a dynamic import")
    defined: set[str] = set()
    for index, node in enumerate(tree.body):
        if (index == 0 and _is_docstring(node)) or isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        else:
            names = _assigned_names(node) or [type(node).__name__]
        for name in names:
            if name in symbols:
                defined.add(name)
            else:
                errors.append(f"{module} defines {name} at top level")
    errors.extend(f"{module} lacks {name}" for name in sorted(symbols - defined))
    return errors


def _leaf_importer_errors(
    module: str, tree: ast.Module, package: str, leaf: str, names: frozenset[str]
) -> list[str]:
    """A declared leaf importer: listed names, plain module-level from-imports only.

    Nothing else under the leaf's package is covered: the leaf as a module object, the
    package itself and a module beside the leaf all fail.
    """
    parent = leaf.rpartition(".")[0]
    top_level = {id(node) for node in tree.body}
    errors: list[str] = []

    def outside(target: str) -> list[str]:
        if target == leaf:
            return [f"{module} imports {leaf} as a module object"]
        if _matches(target, parent):
            return [f"{module} imports {target} beside {leaf}"]
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                errors += outside(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            if base != leaf:
                for alias in node.names:
                    errors += outside(f"{base}.{alias.name}")
                continue
            if id(node) not in top_level:
                errors.append(f"{module} imports {leaf} below module level")
            for alias in node.names:
                if alias.name == "*":
                    errors.append(f"{module} has a star import from {leaf}")
                elif alias.name not in names:
                    errors.append(f"{module} imports unlisted name {leaf}.{alias.name}")
                elif alias.asname not in (None, alias.name):
                    errors.append(f"{module} aliases {alias.name} as {alias.asname}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        ):
            errors.append(f"{module} touches sys.modules")
            break
    if _has_dynamic_import(tree):
        errors.append(f"{module} has a dynamic import")
    return errors


def _initializer_errors(module: str, tree: ast.Module, package: str) -> list[str]:
    """A parent initializer of the data leaf: a docstring and no other statement.

    Python runs it on every import of the leaf, so it may import nothing at all, not
    even a standard-library module, and may define nothing.
    """
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            errors += [f"{module} imports {alias.name}" for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            errors += [f"{module} imports {base}.{alias.name}" for alias in node.names]
    if _has_dynamic_import(tree):
        errors.append(f"{module} has a dynamic import")
    for index, node in enumerate(tree.body):
        if (index == 0 and _is_docstring(node)) or isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        errors.append(f"{module} has a {type(node).__name__} statement")
    return errors


def _contracts_errors(graph: _Graph) -> list[str]:
    """The bounded contracts package: declared modules, one initializer export, no core.

    The initializer is a static shell that re-exports ``RunSpec`` from its own
    ``runspec`` module and nothing else. Every other declared module imports no
    ``inferrsi.*`` module at all, so loading the package cannot load a core, Apps,
    Infra or Model module. An undeclared module under the package fails outright.
    """
    export_module, export_name = CONTRACTS_INIT_EXPORT
    errors: list[str] = []
    for name in sorted(name for name in graph.trees if _matches(name, CONTRACTS_PACKAGE)):
        tree, package = graph.trees[name], graph.packages[name]
        if name not in CONTRACTS_MODULES:
            errors.append(f"{name} is not a declared contracts module")
        elif name == CONTRACTS_PACKAGE:
            errors += _shell_errors(name, tree, package, {export_module: {export_name}})
            imported = [
                alias.name
                for node in tree.body
                if isinstance(node, ast.ImportFrom) and _from_base(node, package) == export_module
                for alias in node.names
            ]
            exported = [
                item.value
                for node in tree.body
                if "__all__" in _assigned_names(node) and _literal_all(node)
                for item in node.value.elts
            ]
            if imported != [export_name] or exported != [export_name]:
                errors.append(f"{name} must re-export exactly {export_name}")
        else:
            errors += [
                f"{name} imports {target}"
                for target in sorted(_direct_targets(tree, package, graph.trees))
            ]
            if _has_dynamic_import(tree):
                errors.append(f"{name} has a dynamic import")
    return errors


def _model_or_infra(module: str) -> bool:
    return _matches(module, "inferrsi.model") or _matches(module, "inferrsi.infra")


@dataclass(frozen=True)
class IsolationReport:
    """Staged first-wave result (A01-4).

    ``new_core_closure_isolated`` covers only the new-core closures present in
    the tree. It never stands in for ``isolation_complete``.
    """

    violations: tuple[str, ...]
    # Every remaining ``harness`` path into Model or Infra, one per hit.
    harness_model_infra: tuple[str, ...]
    blockers: tuple[str, ...]
    new_core_closure_isolated: bool

    @property
    def isolation_complete(self) -> bool:
        return not self.blockers


def blocker_kinds(report: IsolationReport) -> set[str]:
    return {blocker.split(":", 1)[0] for blocker in report.blockers}


def first_wave_report(
    root: Path = ROOT,
    manifest: dict[str, Any] | None = None,
    h_entries: tuple[str, ...] = NEW_H_ENTRIES,
) -> IsolationReport:
    """Exact first-wave policy over ``root`` plus the staged isolation result."""
    manifest = load_manifest() if manifest is None else manifest
    pairs = exact_pairs(manifest)
    leaf = manifest["technical_leaf"]["module"]
    sources = shell_sources(manifest)
    # A retired root module stays an old root leaf for every closure rule below.
    old_leaves = set(sources) | RETIRED_ROOT_MODULES
    graph = _scan(root, pairs)
    modules = sorted(graph.trees)

    violations = cross_core_violations(root, pairs)
    violations += [
        f"{name} is a retired root module"
        for name in modules
        if name in RETIRED_ROOT_MODULES and name not in sources
    ]
    # Outside Knowledge the leaf has its one permanent importer and any staged pair
    # that names it. Every other importer fails.
    declared_importers = dict(LEAF_IMPORTERS)
    leaf_importers = {importer for importer, target in pairs if target == leaf}
    leaf_importers |= set(declared_importers)
    violations += [
        f"{name} is a second importer of {leaf}"
        for name in modules
        if leaf in graph.edges[name]
        and name not in leaf_importers
        and _core_of(name) != "knowledge"
    ]
    for name in sorted(set(declared_importers) & set(modules)):
        violations += _leaf_importer_errors(
            name, graph.trees[name], graph.packages[name], leaf, declared_importers[name]
        )
    for name in sorted(set(sources) & set(modules)):
        # A staged root leaf that reaches into K or the data leaf is a shell.
        if any(_core_of(t) == "knowledge" or t == leaf for t in graph.edges[name]):
            violations += _shell_errors(
                name, graph.trees[name], graph.packages[name], sources[name]
            )
    if leaf in graph.trees:
        violations += _leaf_errors(
            graph.trees[leaf], manifest["technical_leaf"], graph.packages[leaf]
        )
    # #451 C2: the leaf sits in a package, so Python runs that package's initializer
    # with it. Only those exact parent initializers join the leaf, and each must stay
    # import-free. A sibling module under the same package gains nothing.
    leaf_parents = _package_ancestors(leaf, graph.trees)
    for parent in sorted(leaf_parents):
        violations += _initializer_errors(parent, graph.trees[parent], graph.packages[parent])
    violations += _contracts_errors(graph)
    # Inside the contracts package a Knowledge module may name only the encoder. The
    # initializer and its RunSpec module load with that import and are never named.
    violations += [
        f"{name} imports {target}; Knowledge may import only {CANONICAL_ENCODER} there"
        for name in modules
        if _core_of(name) == "knowledge"
        for target in sorted(
            _direct_targets(graph.trees[name], graph.packages[name], graph.trees)
        )
        if _matches(target, CONTRACTS_PACKAGE) and target != CANONICAL_ENCODER
    ]
    encoder_closure = (CANONICAL_ENCODER, CONTRACTS_PACKAGE, CONTRACTS_INIT_EXPORT[0])

    def outside_knowledge(node: str) -> bool:
        return (
            _core_of(node) != "knowledge"
            and node != leaf
            and node not in leaf_parents
            and node not in encoder_closure
        )

    def benchmark_forbidden(node: str) -> bool:
        return _core_of(node) in ("knowledge", "harness", "apps") or node in old_leaves

    def h_entry_forbidden(node: str) -> bool:
        # Every harness module, including a new H entry, may not reach a new
        # core, an old root leaf, or the data leaf. No importer is exempt.
        return _core_of(node) in NEW_CORES or node in old_leaves or node == leaf

    rules: dict[str, Callable[[str], bool]] = {
        "knowledge": outside_knowledge,
        "benchmark": benchmark_forbidden,
        # Apps calls core public APIs and never passes through an old root leaf,
        # which since #412 R1 includes the three retired old-run forwarders.
        "apps": lambda node: node in old_leaves,
    }
    starts = [(name, rules[_core_of(name)]) for name in modules if _core_of(name) in rules]
    starts += [(name, h_entry_forbidden) for name in h_entries if name in graph.trees]
    new_core = [v for name, rule in starts for v in _closure_violations(name, graph, rule)]
    infra = [
        v
        for name in modules
        if _matches(name, "inferrsi.infra")
        for v in _closure_violations(name, graph, lambda node: _core_of(node) is not None)
    ]

    # Non-entry harness modules follow the same rule on the same full graph.
    # They add violations without counting toward the new-core result.
    declared = set(h_entries)
    harness_extra = [
        message
        for name in modules
        if _core_of(name) == "harness" and name not in declared
        for message in _closure_violations(name, graph, h_entry_forbidden)
    ]
    violations += new_core + infra + harness_extra

    blockers = []
    for name in (*NEW_CORES, "harness"):
        package = root / name
        if not package.is_dir():
            blockers.append(f"absent: {name}/")
        elif not any(package.rglob("*.py")):
            # An empty directory is not a present, scannable package (A01-4).
            blockers.append(f"unscannable: {name}/")
    # #412 R1 left the manifest with no pair. One that review stages again blocks.
    if pairs:
        blockers.append(f"allowlist: {len(pairs)} compatibility pairs")
    legacy = [
        path
        for name in modules
        if _core_of(name) == "harness"
        for _, path in _walk(name, graph.edges, _model_or_infra)[1]
    ]
    if legacy:
        blockers.append(f"harness reaches model/infra: {legacy[0]} ({len(legacy)} hits)")
    if violations:
        blockers.append(f"violations: {len(violations)}")
    resource_loaders = [name for name in modules
                        if _resource_loader(graph.trees[name], name) is not None]
    if resource_loaders:
        blockers.append(f"runtime resource loaders: {len(resource_loaders)}")
    return IsolationReport(
        tuple(violations), tuple(legacy), tuple(blockers),
        bool(starts) and not new_core and not resource_loaders,
    )

