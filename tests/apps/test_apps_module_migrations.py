"""Check retired Apps paths, their consumers and package dependencies."""

import ast
import io
import json
import pickle
from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest

from inferrsi.apps.legacy.records import load_record
from tests.contracts.test_contracts_package import IO_CONTROL, IO_PROBE, _fresh
from tests.repository import _gate_policy_support as support

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "src/inferrsi"
MIGRATIONS = json.loads((REPO / "docs/apps-module-migrations.json").read_text(encoding="utf-8"))


def test_apps_root_contains_only_the_public_entries_and_owned_packages():
    root = ROOT / "apps"
    entries = {p.name for p in root.iterdir() if p.name != "__pycache__"}
    packages = {
        "cli", "delivery", "handoff", "host", "integrations", "legacy", "storage",
        "views", "workflows",
    }
    assert entries == packages | {"__init__.py", "api.py"}
    assert all((root / name / "__init__.py").is_file() for name in packages)
    assert (root / "__init__.py").is_file() and (root / "api.py").is_file()


@pytest.mark.parametrize("entry", MIGRATIONS, ids=lambda entry: entry["old"])
def test_retired_path_is_absent_and_its_public_exports_have_replacements(entry):
    assert entry["status"] == "retired" and entry["first_removal_version"] == "0.3.4"
    with pytest.raises(ModuleNotFoundError) as absent:
        import_module(entry["old"])
    assert absent.value.name == entry["old"] or entry["old"].startswith(absent.value.name + ".")
    module = import_module(entry["canonical"])
    for name in entry["exports"]:
        assert hasattr(module, name), (entry["canonical"], name)


@pytest.mark.parametrize("system", ["cannbot", "mindie"])
def test_project_launchers_reference_the_canonical_standalone_worker(system):
    project = import_module(f"inferrsi.apps.integrations.{system}.project")
    worker = ROOT / "apps/integrations" / system / "read_worker.py"
    assert project._WORKER == worker
    assert Path(project.__file__).with_name("read_worker.py") == worker
    operation = "read" if system == "cannbot" else "call"
    assert callable(getattr(project, operation))
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
    from unittest.mock import patch

    old = ModuleType("inferrsi.apps.archive")
    with patch.dict(sys.modules, {old.__name__: old}):
        exec(source, old.__dict__)
        data = pickle.dumps(old.RunOutput("output-test", Path("outputs/test"), {"retained": True}))
    from inferrsi.apps.storage.archive import RunOutput

    restored = load_record(io.BytesIO(data))
    assert pickle.loads(pickle.dumps(restored)) == restored
    assert type(restored) is RunOutput
    assert restored == RunOutput("output-test", Path("outputs/test"), {"retained": True})


def test_active_consumers_use_canonical_paths_and_are_registered():
    modules = support._module_index(ROOT)
    old_names = {entry["old"] for entry in MIGRATIONS}
    entries = {entry["canonical"]: entry for entry in MIGRATIONS}
    # Include absent names when resolving "from package import retired_module".
    for name in old_names:
        modules[name] = ROOT / (name.replace(".", "/") + ".py")
    for entry in MIGRATIONS:
        assert entry["consumers"] and len(entry["consumers"]) == len(set(entry["consumers"]))
        assert all((REPO / path).is_file() for path in entry["consumers"])
    for directory in ("src", "tests", "tools", "plugins", "examples"):
        base = REPO / directory
        for path in base.rglob("*.py"):
            if path.is_relative_to(REPO / "tests/fixtures/legacy"):
                continue
            relative = path.relative_to(REPO).as_posix()
            package = ".".join(path.relative_to(base).parts[:-1])
            targets = support._direct_targets(
                ast.parse(path.read_text(encoding="utf-8")), package, modules
            )
            assert not targets & old_names, (relative, targets & old_names)
            for target in targets & entries.keys():
                assert relative in entries[target]["consumers"], (relative, target)


def _is_handoff(name):
    return name in {"inferrsi.apps.api", "inferrsi.apps.handoff"} or name.startswith(
        "inferrsi.apps.handoff."
    )


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
                "inferrsi.apps.integrations", "inferrsi.apps.integrations.mindie"]
    for package in packages:
        path = REPO / "src" / package.replace(".", "/") / "__init__.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert len(tree.body) == 1 and ast.get_docstring(tree)
    modules = packages + [entry["canonical"] for entry in MIGRATIONS]
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
    modules = [entry["canonical"] for entry in MIGRATIONS if ".storage." in entry["canonical"]]
    result = _fresh(script, json.dumps(modules))
    assert result == {"parent_only": ["inferrsi.apps", "inferrsi.apps.storage"], "warnings": []}


def test_public_candidate_provider_is_the_one_canonical_class():
    from inferrsi.apps import api
    from inferrsi.apps.handoff.candidate_provider import CandidateProvider

    assert api.CandidateProvider is CandidateProvider
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
    restored = load_record(io.BytesIO(legacy))
    assert pickle.loads(pickle.dumps(restored)) == restored
    assert type(restored) is DeliveredContextDraft and restored == value


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_record_reader_accepts_retained_data_across_pickle_protocols(protocol):
    from inferrsi.apps.storage.archive import RunOutput

    value = RunOutput("answer", Path("outputs/test"), {"utf8": b"\xc3\xa9"})
    assert load_record(io.BytesIO(pickle.dumps(value, protocol))) == value


def test_record_reader_rejects_other_pickled_objects():
    with pytest.raises(pickle.UnpicklingError, match="unexpected|unsupported"):
        load_record(io.BytesIO(pickle.dumps(complex(1, 2))))


@pytest.mark.parametrize("group", ["handoff", "workflows", "integrations"])
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
    modules = [entry["canonical"] for entry in MIGRATIONS if f".{group}." in entry["canonical"]]
    result = _fresh(script, json.dumps(modules), group)
    assert result == {"parent_only": ["inferrsi.apps", f"inferrsi.apps.{group}"],
                      "warnings": [], "control": True}
