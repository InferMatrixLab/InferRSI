"""Identify the installed session code, including its knowledge capture, Find and Read paths.

The identity pins previously retained contexts through their individual hashes.
New captures may use the currently installed Knowledge internals. Version metadata
is generated at build time and does not define the session execution contract.
"""

import ast
from importlib.resources import files
from importlib.util import resolve_name
from pathlib import Path

from ..records.artifact_primitives import sha256

_KNOWLEDGE_ROOTS = (
    "inferrsi.knowledge.context_projection",
    "inferrsi.knowledge.knowledge_find",
    "inferrsi.knowledge.ranking_policy",
)
_ROOTS = (
    "inferrsi.harness.manager._session",
    "inferrsi.apps.workflows.campaign",
    "inferrsi.apps.workflows.decision_round",
    "inferrsi.apps.workflows.session_knowledge",
    "inferrsi.apps.workflows.knowledge",
    *_KNOWLEDGE_ROOTS,
)


def included_module(name):
    return (
        (name == "inferrsi" or name.startswith("inferrsi."))
        and name != "inferrsi._version"
        and (not name.startswith("inferrsi.knowledge.") or name in _KNOWLEDGE_ROOTS)
    )


def _imports(tree, package, path):
    nodes = list(ast.walk(tree))
    importlib_aliases = {"importlib"}
    import_function_aliases = {"__import__"}
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = resolve_name("." * node.level + name, package)
            yield name
            for alias in node.names:
                yield f"{name}.{alias.name}"
                if (name, alias.name) in (("builtins", "__import__"),
                                          ("importlib", "import_module")):
                    import_function_aliases.add(alias.asname or alias.name)
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in import_function_aliases
                or isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                and ((func.value.id in importlib_aliases and func.attr == "import_module")
                     or (func.value.id == "builtins" and func.attr == "__import__"))):
            continue
        argument = node.args[0] if node.args else None
        if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
            raise ValueError(
                f"Session runtime import must name a literal module in {path}:{node.lineno}"
            )
        yield resolve_name(argument.value, package)


def source_files(root):
    """Derive the internal import closure, including package initializers and lazy imports."""
    pending = list(_ROOTS)
    visited, sources = set(), set()
    while pending:
        name = pending.pop()
        if name in visited or not included_module(name):
            continue
        visited.add(name)
        parts = name.split(".")
        location = root.joinpath(*parts[1:])
        path = location / "__init__.py"
        if path.is_file():
            package = name
        else:
            path = location.with_suffix(".py")
            if not path.is_file():
                continue  # A from-import name can be an attribute instead of a module.
            package = name.rpartition(".")[0]
        if name != "inferrsi":
            pending.append(name.rpartition(".")[0])
        relative = path.relative_to(root).as_posix()
        sources.add(relative)
        pending.extend(_imports(ast.parse(path.read_bytes(), relative), package, relative))
    return sorted(sources)


def session_runtime_identity() -> dict[str, str]:
    """Hash the installed source files that define an ordinary session."""
    root = Path(str(files("inferrsi")))
    return {name: sha256(root / name) for name in source_files(root)}
