"""The neutral repository-pack facade (#451 C2).

``inferrsi.resources.repository_packs`` replaces root ``_repo_pack_data.py``. It holds
the one ``REPO_TYPES`` tuple and the ``pack.json`` reader, imports no ``inferrsi``
module, and sits under an import-free initializer. The retired root path has no alias.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import importlib.util
import json
import os
import pickle
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

import inferrsi.resources as resources
from inferrsi.apps.cli import arguments
from inferrsi.apps.host import inspection
from inferrsi.knowledge import catalog as knowledge_catalog
from inferrsi.resources import repository_packs
from tests.test_contracts_package import IO_CONTROL, IO_PROBE

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = SRC / "inferrsi"
PACKS = ROOT / "harness" / "data" / "repo_packs"
EIGHT = (
    "vllm", "vllm_omni", "vllm_musa", "afd_plugin", "vllm_rlt", "strata",
    "sglang", "sglang_omni",
)
RETIRED = "inferrsi._repo_pack_data"
FACADE_CLOSURE = {"inferrsi", "inferrsi.resources", "inferrsi.resources.repository_packs"}
# The facade needs none of these. #412 R1 retired root catalog, so the CLI parser that
# now reads the tuple directly stands in its place.
CORES = ("inferrsi.harness", "inferrsi.knowledge", "inferrsi.apps",
         "inferrsi.benchmark", "inferrsi.contracts")
# Every other inferrsi import is refused, so the facade works only if it needs none.
BLOCKED = """
import importlib.abc, json, sys
ALLOWED = {"inferrsi", "inferrsi._version", "inferrsi.resources",
           "inferrsi.resources.repository_packs"}
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "inferrsi" and name not in ALLOWED:
            raise ImportError("blocked inferrsi import: " + name)
        return None
sys.meta_path.insert(0, Block())
def loaded():
    return sorted(name for name in sys.modules if name.split(".")[0] == "inferrsi")
import inferrsi.resources
parent_only = loaded()
parent_public = sorted(name for name in vars(inferrsi.resources) if not name.startswith("_"))
from inferrsi.resources import repository_packs
packs = {name: repository_packs.repository_pack(name) for name in repository_packs.REPO_TYPES}
after_reads = loaded()
refused = {}
for name in json.loads(sys.argv[1]):
    try:
        __import__(name)
    except ImportError as error:
        refused[name] = str(error)
print(json.dumps({
    "parent_only": parent_only, "parent_public": parent_public, "loaded": after_reads,
    "types": list(repository_packs.REPO_TYPES), "packs": packs, "refused": refused,
}))
"""
# The resource reader is loaded before the hook, so the events are the read itself.
READ = """
import importlib.readers, json, os, sys
from inferrsi.resources import repository_packs
IO_EVENTS = ("os.", "shutil.", "pathlib.", "tempfile.", "glob.", "subprocess.", "socket.")
seen = []
active = []
def hook(event, args):
    if active and (event == "open" or event.startswith(IO_EVENTS)):
        path = args[0] if args else None
        path = os.fsdecode(path) if isinstance(path, (str, bytes, os.PathLike)) else None
        mode = args[1] if event == "open" and len(args) > 1 else None
        seen.append([event, path, mode if isinstance(mode, str) else None])
sys.addaudithook(hook)
def loaded():
    return sorted(name for name in sys.modules if name.split(".")[0] == "inferrsi")
before = loaded()
active.append(True)
pack = repository_packs.repository_pack(sys.argv[1])
active.clear()
print(json.dumps({"seen": seen, "before": before, "after": loaded(), "pack": pack}))
"""


def _fresh(script: str, *args: str) -> dict:
    environment = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [sys.executable, "-c", script, *args], capture_output=True, text=True,
        encoding="utf-8", env=environment, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _without_version(names) -> set[str]:
    return set(names) - {"inferrsi._version"}


def test_one_repo_types_object_reaches_every_consumer() -> None:
    canonical = repository_packs.REPO_TYPES
    assert canonical == EIGHT and type(canonical) is tuple and len(canonical) == 8
    assert knowledge_catalog.REPO_TYPES is canonical
    # #412 R1: root catalog is retired, so the parser binds the tuple from the facade
    # itself. It is the same object, read directly and never copied.
    assert arguments.REPO_TYPES is canonical
    assert importlib.util.find_spec("inferrsi.catalog") is None
    # #408 A1: the parser is in Apps and reads the tuple through the Knowledge catalog.
    assert arguments.__name__ == "inferrsi.apps.cli.arguments"
    assert importlib.util.find_spec("inferrsi.arguments") is None
    assert not (ROOT / "arguments.py").exists()
    source = (ROOT / "apps" / "cli" / "arguments.py").read_text(encoding="utf-8")
    assert source.splitlines().count(
        "from ...knowledge.catalog import BACKENDS, KNOWLEDGE_REPOS, KNOWLEDGE_SCOPES, REPO_TYPES"
    ) == 1
    assert "repository_packs" not in source
    assert "repository_pack(" not in source and not hasattr(arguments, "repository_pack")
    assert inspection.repository_pack is repository_packs.repository_pack
    assert not hasattr(knowledge_catalog, "repository_pack")
    assert knowledge_catalog.KNOWLEDGE_SCOPES["contribution"] == (
        *canonical, "vllm_ascend", "inferrsi"
    )
    # The active argument surface offers that same object as its choices.
    parser = argparse.ArgumentParser()
    arguments._common(parser)
    action = next(item for item in parser._actions if item.dest == "repo_type")
    assert action.choices is canonical


def test_only_the_facade_defines_the_tuple_and_the_reader() -> None:
    tuples, readers = [], []
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(item, ast.Name) and item.id == "REPO_TYPES" for item in targets):
                    tuples.append(relative)
            elif isinstance(node, ast.FunctionDef) and node.name == "repository_pack":
                readers.append(relative)
    assert tuples == ["resources/repository_packs.py"]
    assert readers == ["resources/repository_packs.py"]


@pytest.mark.parametrize("repo_type", EIGHT)
def test_each_pack_parses_to_its_packaged_bytes(repo_type: str) -> None:
    data = (PACKS / repo_type / "pack.json").read_bytes()
    anchored = files("inferrsi").joinpath("harness", "data", "repo_packs", repo_type, "pack.json")
    assert hashlib.sha256(anchored.read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()
    pack = repository_packs.repository_pack(repo_type)
    assert pack == json.loads(data.decode("utf-8"))
    assert type(pack) is dict and pack["id"] == repo_type
    # Each call parses again; callers never share one mutable dict.
    assert repository_packs.repository_pack(repo_type) is not pack
    # The one permanent importer outside Knowledge reads the same bytes.
    assert inspection.repository_pack(repo_type) == pack


def test_the_eight_packs_are_the_whole_harness_resource_root() -> None:
    found = sorted(
        path.relative_to(PACKS).as_posix() for path in PACKS.rglob("*") if path.is_file()
    )
    assert found == sorted(f"{name}/pack.json" for name in EIGHT)


@pytest.mark.parametrize(
    "repo_type", ["not-a-repository", "xdit", "", "VLLM", "../vllm", "vllm/", None, 7]
)
def test_unknown_repository_type_fails_before_any_resource_access(repo_type, monkeypatch) -> None:
    def no_access(*args, **kwargs):
        raise AssertionError("an unknown repository type must not reach the resource")

    monkeypatch.setattr(repository_packs, "files", no_access)
    with pytest.raises(ValueError) as caught:
        repository_packs.repository_pack(repo_type)
    assert str(caught.value) == f"Unknown repository type: {repo_type}"


def test_facade_and_parent_load_under_a_hook_that_blocks_every_other_inferrsi_import() -> None:
    result = _fresh(BLOCKED, json.dumps(CORES))
    # The initializer alone loads nothing and binds no public name.
    assert _without_version(result["parent_only"]) == {"inferrsi", "inferrsi.resources"}
    assert result["parent_public"] == []
    # All eight packs were read with only the facade and its parent loaded.
    assert _without_version(result["loaded"]) == FACADE_CLOSURE
    assert tuple(result["types"]) == EIGHT
    for name in EIGHT:
        expected = json.loads((PACKS / name / "pack.json").read_bytes().decode("utf-8"))
        assert result["packs"][name] == expected, name
    # Positive control: the hook is live and refuses every core, Harness included.
    assert result["refused"] == {name: f"blocked inferrsi import: {name}" for name in CORES}


def test_module_bodies_do_no_io_on_import() -> None:
    modules = ("inferrsi.resources", "inferrsi.resources.repository_packs",
               "inferrsi.apps.storage.evidence_layout")
    result = _fresh(IO_PROBE, json.dumps(modules), IO_CONTROL)
    seen, defined = result["seen"], result["defined"]
    assert {"os.listdir", "open"} <= set(seen.pop("control"))
    assert seen == {name: [] for name in modules}
    assert defined["inferrsi.resources"] == []
    assert {"REPO_TYPES", "repository_pack"} <= set(defined["inferrsi.resources.repository_packs"])
    assert "ensure_evidence_layout" in defined["inferrsi.apps.storage.evidence_layout"]
    assert sorted(name for name in vars(resources) if not name.startswith("_")) == [
        "repository_packs"
    ]


@pytest.mark.parametrize("repo_type", EIGHT)
def test_a_read_opens_only_the_requested_pack_and_loads_no_module(repo_type: str) -> None:
    result = _fresh(READ, repo_type)
    package = os.path.normcase(str(ROOT))
    expected = os.path.normcase(str(PACKS / repo_type / "pack.json"))
    # Inside the package tree the read is one open of the requested file: no listing,
    # no second pack, no write.
    inside = [
        (event, os.path.normcase(os.path.abspath(path)), mode)
        for event, path, mode in result["seen"]
        if path is not None and os.path.normcase(os.path.abspath(path)).startswith(package)
    ]
    assert inside == [("open", expected, "r")]
    assert result["before"] == result["after"]
    assert _without_version(result["after"]) == FACADE_CLOSURE
    assert result["pack"]["id"] == repo_type


def test_retired_root_module_has_no_alias() -> None:
    assert not (ROOT / "_repo_pack_data.py").exists()
    assert importlib.util.find_spec(RETIRED) is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(RETIRED)
    assert RETIRED not in sys.modules
    assert not hasattr(sys.modules["inferrsi"], "_repo_pack_data")
    # A pickle that names the reader by the retired module path no longer loads.
    with pytest.raises(ModuleNotFoundError):
        pickle.loads(f"c{RETIRED}\nrepository_pack\n.".encode("ascii"))
    reader = repository_packs.repository_pack
    assert reader.__module__ == "inferrsi.resources.repository_packs"
    assert b"inferrsi.resources.repository_packs" in pickle.dumps(reader, protocol=0)
    assert pickle.loads(pickle.dumps(reader)) is reader
    # The tuple pickles by value, so stored REPO_TYPES values are unaffected by the move.
    assert b"inferrsi" not in pickle.dumps(repository_packs.REPO_TYPES, protocol=0)
