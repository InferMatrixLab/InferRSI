"""Compatibility and dependency checks for the implemented #490 slices."""

import ast
import inspect
import json
import pickle
from importlib import import_module
from importlib.util import resolve_name
from pathlib import Path
from types import ModuleType
from typing import get_origin

import pytest

from tests import _gate_policy_support as support
from tests.test_contracts_package import IO_CONTROL, IO_PROBE, _fresh

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "src/inferrsi"
MIGRATIONS = json.loads((REPO / "docs/apps-module-migrations.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", MIGRATIONS, ids=lambda entry: entry["old"])
def test_shim_is_an_explicit_export_of_the_same_objects(entry):
    relative = entry["old"].replace(".", "/")
    path = REPO / "src" / (relative + ("/__init__.py" if entry.get("package") else ".py"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    statements = list(tree.body)
    if entry.get("script_entry"):
        guard = statements.pop()
        assert ast.dump(guard) == ast.dump(ast.parse(
            f'if __name__ == "__main__":\n    {entry["script_entry"]}()\n'
        ).body[0])
    docstring, *imports, declared = statements
    assert isinstance(docstring, ast.Expr) and isinstance(docstring.value, ast.Constant)
    package = entry["old"] if entry.get("package") else entry["old"].rpartition(".")[0]
    imported_names = []
    for imported in imports:
        assert isinstance(imported, ast.ImportFrom)
        target = resolve_name("." * imported.level + (imported.module or ""), package)
        for name in imported.names:
            assert name.asname is None and name.name != "*"
            module_export = entry.get("module_exports", {}).get(name.name)
            if module_export:
                assert target + "." + name.name == module_export["old"]
            else:
                assert target == entry["canonical"]
            imported_names.append(name.name)
    assert sorted(imported_names) == sorted(entry["exports"])
    if entry.get("script_entry"):
        assert len(imports) == 1 and imports[0].level == 0
    assert isinstance(declared, ast.Assign)
    assert [target.id for target in declared.targets] == ["__all__"]
    assert ast.literal_eval(declared.value) == entry["exports"]
    old, canonical = import_module(entry["old"]), import_module(entry["canonical"])
    assert old.__all__ == entry["exports"]
    old_modules = {item["old"] for item in MIGRATIONS}
    public = [name for name, value in vars(old).items() if not name.startswith("_")
              and not (entry.get("package") and name not in old.__all__
                       and isinstance(value, ModuleType) and value.__name__ in old_modules)]
    assert sorted(public) == sorted(old.__all__)
    for name in entry["exports"]:
        value = getattr(canonical, name)
        if name in entry.get("module_exports", {}):
            binding = entry["module_exports"][name]
            assert any(item["old"] == binding["old"] and item["canonical"] == binding["canonical"]
                       for item in MIGRATIONS)
            assert getattr(old, name) is import_module(binding["old"])
            assert value is import_module(binding["canonical"])
            continue
        assert getattr(old, name) is value
        # Generic aliases retain stdlib metadata; only definitions move modules.
        if get_origin(value) is None and (inspect.isfunction(value) or inspect.isclass(value)):
            assert value.__module__ == entry["canonical"]
            # Protocol 0 GLOBAL references mirror pre-migration function/class pickles.
            assert pickle.loads(f"c{entry['old']}\n{name}\n.".encode("ascii")) is value
            new_pickle = pickle.dumps(value, protocol=0)
            assert entry["canonical"].encode("ascii") in new_pickle
            assert pickle.loads(new_pickle) is value


def test_generic_alias_identity_does_not_depend_on_inspect_isclass(monkeypatch):
    from inferrsi.apps.storage.archive import ResourceReader

    original = inspect.isclass
    monkeypatch.setattr(
        inspect, "isclass", lambda value: value is ResourceReader or original(value)
    )
    entry = next(entry for entry in MIGRATIONS if entry["old"] == "inferrsi.apps.archive")
    test_shim_is_an_explicit_export_of_the_same_objects(entry)


@pytest.mark.parametrize("child_first", [False, True])
def test_legacy_cannbot_package_keeps_its_project_module_in_either_import_order(child_first):
    script = """
import importlib, json, sys
parent = 'inferrsi.apps.cannbot'
if sys.argv[1] == 'True':
    importlib.import_module(parent + '.project')
old = importlib.import_module(parent)
child = importlib.import_module(parent + '.project')
canonical = importlib.import_module('inferrsi.apps.integrations.cannbot')
importlib.import_module(parent + '.read_worker')
assert old.project is child
assert child is not canonical.project
assert old.CannbotChannel is canonical.CannbotChannel
assert all(getattr(child, name) is getattr(canonical.project, name) for name in child.__all__)
print(json.dumps({'compatible': True}))
"""
    assert _fresh(script, str(child_first)) == {"compatible": True}


@pytest.mark.parametrize("system", ["cannbot"])
def test_project_launchers_reference_the_canonical_standalone_worker(system):
    project = import_module(f"inferrsi.apps.integrations.{system}.project")
    legacy = import_module(f"inferrsi.apps.{system}.project")
    worker = ROOT / "apps/integrations" / system / "read_worker.py"
    assert project._WORKER == worker
    assert Path(project.__file__).with_name("read_worker.py") == worker
    operation = "read" if system == "cannbot" else "call"
    assert getattr(legacy, operation) is getattr(project, operation)
    script = """
import ast, json, runpy, sys
from pathlib import Path
path = Path(sys.argv[1])
tree = ast.parse(path.read_text(encoding='utf-8'))
top = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
for node in top:
    assert not (isinstance(node, ast.ImportFrom) and node.level)
    names = [node.module] if isinstance(node, ast.ImportFrom) else [n.name for n in node.names]
    assert all(name.split('.')[0] in sys.stdlib_module_names for name in names)
namespace = runpy.run_path(str(path), run_name='not_main')
assert callable(namespace['read'])
assert not any(n.split('.')[0] in ('inferrsi', 'mindie_knowledge') for n in sys.modules)
print(json.dumps({'standalone': True}))
"""
    assert _fresh(script, str(worker)) == {"standalone": True}


def test_old_run_output_instance_pickle_loads_and_preserves_its_data():
    # Construct the legacy bytes using the original definition from the old module.
    source = """from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class RunOutput:
    output_id: str
    directory: Path | None
    result: dict
"""
    import sys
    from types import ModuleType
    from unittest.mock import patch

    old = ModuleType("inferrsi.apps.archive")
    with patch.dict(sys.modules, {old.__name__: old}):
        exec(source, old.__dict__)
        data = pickle.dumps(old.RunOutput("output-test", Path("outputs/test"), {"retained": True}))
    from inferrsi.apps.storage.archive import RunOutput

    restored = pickle.loads(data)
    assert type(restored) is RunOutput
    assert restored == RunOutput("output-test", Path("outputs/test"), {"retained": True})


def test_active_consumers_use_canonical_paths_and_are_registered():
    modules = support._module_index(ROOT)
    old_names = {entry["old"] for entry in MIGRATIONS}
    entries = {entry["canonical"]: entry for entry in MIGRATIONS}
    shims = {entry["old"].replace(".", "/") + (
        "/__init__.py" if entry.get("package") else ".py"
    ) for entry in MIGRATIONS}
    for entry in MIGRATIONS:
        assert entry["consumers"] and len(entry["consumers"]) == len(set(entry["consumers"]))
        assert all((REPO / path).is_file() for path in entry["consumers"])
    for base in (REPO / "src", REPO / "tests", REPO / "tools", REPO / "plugins"):
        for path in base.rglob("*.py"):
            if path.is_relative_to(REPO / "tests/fixtures/legacy"):
                continue
            relative = path.relative_to(REPO).as_posix()
            if relative.removeprefix("src/") in shims:
                continue
            package = ".".join(path.relative_to(base).parts[:-1])
            targets = support._direct_targets(
                ast.parse(path.read_text(encoding="utf-8")), package, modules
            )
            assert not targets & old_names, (relative, targets & old_names)
            for target in targets & entries.keys():
                assert relative in entries[target]["consumers"], (relative, target)


def _is_handoff(name):
    # Include retained shims as well as the canonical handoff implementations.
    return name in {
        "inferrsi.apps.api", "inferrsi.apps.bridge", "inferrsi.apps.context_provider",
        "inferrsi.apps.candidate_provider",
    } or name == "inferrsi.apps.handoff" or name.startswith("inferrsi.apps.handoff.")


def test_storage_has_no_direct_or_transitive_handoff_dependency():
    graph = support._scan(ROOT, frozenset())
    for name in graph.edges:
        if name == "inferrsi.apps.storage" or name.startswith("inferrsi.apps.storage."):
            _, violations = support._walk(name, graph.edges, _is_handoff)
            assert not violations, violations


@pytest.mark.parametrize("indirect", [False, True])
def test_storage_dependency_check_rejects_a_handoff_back_edge(tmp_path, indirect):
    files = {
        "apps/__init__.py": "",
        "apps/storage/__init__.py": "",
        "apps/handoff/__init__.py": "",
        "apps/handoff/bridge.py": "VALUE = 1\n",
        "apps/storage/archive.py": "from ..handoff import bridge\n",
    }
    if indirect:
        files["apps/storage/archive.py"] = "from inferrsi.contracts import helper\n"
        files["contracts/helper.py"] = "from inferrsi.apps.handoff import bridge\n"
    for relative, source in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    graph = support._scan(tmp_path, frozenset())
    _, violations = support._walk("inferrsi.apps.storage.archive", graph.edges, _is_handoff)
    assert any(target == "inferrsi.apps.handoff.bridge" for target, _ in violations)
    if indirect:
        assert any("inferrsi.contracts.helper ->" in chain for _, chain in violations)


def test_migrated_initializers_import_nothing_and_module_bodies_do_no_io():
    packages = ["inferrsi.apps.storage", "inferrsi.apps.handoff", "inferrsi.apps.workflows",
                "inferrsi.apps.integrations"]
    for package in packages:
        path = REPO / "src" / package.replace(".", "/") / "__init__.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert len(tree.body) == 1 and ast.get_docstring(tree)
    modules = packages + [
        entry[key] for entry in MIGRATIONS for key in ("old", "canonical")
    ]
    result = _fresh(IO_PROBE, json.dumps(modules), IO_CONTROL)
    seen = result["seen"]
    assert {"os.listdir", "open"} <= set(seen.pop("control"))
    assert seen == {name: [] for name in modules}
    assert all(result["defined"][package] == [] for package in packages)


def test_cold_storage_imports_do_not_load_handoff_or_probe_modules():
    script = """
import importlib, importlib.abc, json, sys, warnings
blocked = ('inferrsi.apps.handoff', 'inferrsi.apps.api', 'inferrsi.apps.bridge',
           'inferrsi.apps.context_provider', 'inferrsi.apps.candidate_provider',
           'inferrsi.infra', 'inferrsi.knowledge', 'inferrsi.benchmark',
           'inferrsi.harness.api', 'inferrsi.harness.run_store')
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if any(name == item or name.startswith(item + '.') for item in blocked):
            raise ImportError('unexpected import: ' + name)
sys.meta_path.insert(0, Block())
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    importlib.import_module('inferrsi.apps.storage')
    parent_only = sorted(name for name in sys.modules if name.startswith('inferrsi.apps'))
    for name in json.loads(sys.argv[1]):
        importlib.import_module(name)
print(json.dumps({'parent_only': parent_only, 'warnings': [str(w.message) for w in caught]}))
"""
    modules = [entry[key] for entry in MIGRATIONS if ".storage." in entry["canonical"]
               for key in ("old", "canonical")]
    result = _fresh(script, json.dumps(modules))
    assert result == {"parent_only": ["inferrsi.apps", "inferrsi.apps.storage"], "warnings": []}


def test_public_candidate_provider_is_the_one_canonical_class():
    from inferrsi.apps import api
    from inferrsi.apps.handoff.candidate_provider import CandidateProvider

    old = import_module("inferrsi.apps.candidate_provider")
    assert api.CandidateProvider is old.CandidateProvider is CandidateProvider
    assert CandidateProvider.__module__ == "inferrsi.apps.handoff.candidate_provider"
    assert api.EvaluationPort.__module__ == "inferrsi.apps.api"


def test_delivered_context_draft_loads_a_legacy_instance_pickle():
    from inferrsi.apps.handoff.context_provider import DeliveredContextDraft

    value = DeliveredContextDraft(b"context", "context/test/delivered.bin", "a" * 64,
                                  [], {}, [], [])
    data = pickle.dumps(value, protocol=0)
    canonical = b"cinferrsi.apps.handoff.context_provider\nDeliveredContextDraft\n"
    assert data.count(canonical) == 1
    legacy = data.replace(canonical, b"cinferrsi.apps.context_provider\nDeliveredContextDraft\n")
    restored = pickle.loads(legacy)
    assert type(restored) is DeliveredContextDraft and restored == value


@pytest.mark.parametrize("group", ["handoff", "workflows", "integrations"])
def test_cold_handoff_and_workflow_imports_do_not_read_data_probe_or_launch_services(group):
    script = """
import builtins, importlib, importlib.abc, io, json, socket, sqlite3, subprocess, sys, warnings
from unittest.mock import patch
blocked = ('inferrsi.apps.api', 'inferrsi.harness.api', 'inferrsi.harness.run_store',
           'inferrsi.harness.generation', 'torch', 'numpy', 'PIL', 'vllm')
if sys.argv[2] == 'handoff':
    blocked += ('inferrsi.infra', 'inferrsi.benchmark', 'inferrsi.model')
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if any(name == item or name.startswith(item + '.') for item in blocked):
            raise ImportError('unexpected import: ' + name)
sys.meta_path.insert(0, Block())
def deny(*args, **kwargs):
    raise AssertionError('unexpected data read, device probe, process or service')
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    importlib.import_module('inferrsi.apps.' + sys.argv[2])
    parent_only = sorted(name for name in sys.modules if name.startswith('inferrsi.apps'))
    with patch.object(builtins, 'open', deny), patch.object(io, 'open', deny), \\
         patch.object(subprocess, 'Popen', deny), patch.object(sqlite3, 'connect', deny), \\
         patch.object(socket, 'socket', deny):
        for name in json.loads(sys.argv[1]):
            importlib.import_module(name)
        try:
            io.open('control')
        except AssertionError:
            control = True
print(json.dumps({'parent_only': parent_only, 'warnings': [str(w.message) for w in caught],
                  'control': control}))
"""
    modules = [entry[key] for entry in MIGRATIONS if f".{group}." in entry["canonical"]
               for key in ("old", "canonical")]
    result = _fresh(script, json.dumps(modules), group)
    assert result == {"parent_only": ["inferrsi.apps", f"inferrsi.apps.{group}"],
                      "warnings": [], "control": True}
