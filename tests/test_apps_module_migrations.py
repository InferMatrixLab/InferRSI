"""Compatibility and dependency checks for the implemented #490 slices."""

import ast
import inspect
import json
import pickle
from importlib import import_module
from pathlib import Path
from typing import get_origin

import pytest

from tests import _gate_policy_support as support
from tests.test_contracts_package import IO_CONTROL, IO_PROBE, _fresh

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "src/inferrsi"
MIGRATIONS = json.loads((REPO / "docs/apps-module-migrations.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", MIGRATIONS, ids=lambda entry: entry["old"])
def test_shim_is_an_explicit_export_of_the_same_objects(entry):
    path = REPO / "src" / (entry["old"].replace(".", "/") + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if entry.get("script_entry"):
        docstring, imported, declared, guard = tree.body
        assert ast.dump(guard) == ast.dump(ast.parse(
            f'if __name__ == "__main__":\n    {entry["script_entry"]}()\n'
        ).body[0])
    else:
        docstring, imported, declared = tree.body
    assert isinstance(docstring, ast.Expr) and isinstance(docstring.value, ast.Constant)
    assert isinstance(imported, ast.ImportFrom)
    if entry.get("script_entry"):
        # This former file entry must also work without a package context.
        assert imported.level == 0 and imported.module == entry["canonical"]
    else:
        assert imported.level == 1
        assert "inferrsi.apps." + imported.module == entry["canonical"]
    assert sorted((name.name, name.asname) for name in imported.names) == sorted(
        (name, None) for name in entry["exports"]
    )
    assert isinstance(declared, ast.Assign)
    assert [target.id for target in declared.targets] == ["__all__"]
    assert ast.literal_eval(declared.value) == entry["exports"]
    old, canonical = import_module(entry["old"]), import_module(entry["canonical"])
    assert old.__all__ == entry["exports"]
    assert sorted(name for name in vars(old) if not name.startswith("_")) == sorted(old.__all__)
    for name in entry["exports"]:
        value = getattr(canonical, name)
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
    shims = {name.replace(".", "/") + ".py" for name in old_names}
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
    packages = ["inferrsi.apps.storage", "inferrsi.apps.handoff", "inferrsi.apps.workflows"]
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
           'inferrsi.apps.host', 'inferrsi.knowledge', 'inferrsi.benchmark',
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


@pytest.mark.parametrize("group", ["handoff", "workflows"])
def test_cold_handoff_and_workflow_imports_do_not_read_data_probe_or_launch_services(group):
    script = """
import builtins, importlib, importlib.abc, io, json, socket, sqlite3, subprocess, sys, warnings
from unittest.mock import patch
blocked = ('inferrsi.apps.api', 'inferrsi.harness.api', 'inferrsi.harness.run_store',
           'inferrsi.harness.generation', 'torch', 'numpy', 'PIL', 'vllm')
if sys.argv[2] == 'handoff':
    blocked += ('inferrsi.apps.host', 'inferrsi.benchmark', 'inferrsi.apps.integrations')
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
