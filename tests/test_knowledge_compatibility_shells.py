# K01 moved the Knowledge implementations and left static root shells. #412 R1 deleted
# those seven shells: the root names no longer import, the moved modules keep every
# recorded name, and the data leaf keeps its locks and its one permanent importer.

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import os
import pickle
import subprocess
import sys

import pytest

from tests import _gate_policy_support as support
from tests._gate_policy_support import (
    LEAF_IMPORTERS,
    REPO,
    RETIRED_ROOT_MODULES,
    ROOT,
    exact_pairs,
    first_wave_report,
    load_manifest,
)

MANIFEST = load_manifest()
LEAF = MANIFEST["technical_leaf"]
# The nine pairs and the two root catalog routes as they stood before R1 retired them.
HISTORY = MANIFEST["revision_history"]
RETIRED = next(item for item in HISTORY if "retired_compatibility_pairs" in item)
# #408 A1 appended the R1 record, which holds the temporary parser entry it removed.
R1_RECORD = HISTORY[-1]
LEAF_NAMES = RETIRED["retired_catalog_two_routes"]["neutral_leaf_export"]["symbols"]
MOVED = [item for item in RETIRED["retired_compatibility_pairs"] if "exports" in item]


@pytest.mark.parametrize("item", MOVED, ids=lambda item: item["importer"])
def test_retired_root_name_fails_and_the_moved_module_keeps_every_name(item):
    retired = f"inferrsi.{item['importer']}"
    assert retired in RETIRED_ROOT_MODULES
    assert not (ROOT / f"{item['importer']}.py").exists()
    assert importlib.util.find_spec(retired) is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(retired)
    assert retired not in sys.modules
    assert not hasattr(sys.modules["inferrsi"], item["importer"])
    # K01-1 carried identity through the shell. The same names are now read where
    # they are defined, so nothing the shell exported was lost with it.
    moved = importlib.import_module(item["target"])
    names = [*item["exports"]["public"], *item["exports"]["private_used"]]
    assert len(names) == len(set(names))
    for name in names:
        assert hasattr(moved, name), name
    # A pickle that names a class or function by the retired root path no longer loads.
    with pytest.raises(ModuleNotFoundError):
        pickle.loads(f"c{retired}\n{names[0]}\n.".encode("ascii"))


def test_retired_record_is_the_seven_shells_and_the_manifest_stages_nothing():
    assert MANIFEST["compatibility_pairs"] == []
    assert exact_pairs(MANIFEST) == frozenset()
    assert "catalog_two_routes" not in MANIFEST
    assert RETIRED["stage"] == "C2"
    assert R1_RECORD["stage"] == "R1" and HISTORY[-2] is RETIRED
    assert R1_RECORD["base_commit"] in RETIRED["superseded_by"]
    # Every record names the base commit of the revision that superseded it.
    bases = [item["base_commit"] for item in HISTORY[1:]] + [MANIFEST["base_commit"]]
    for item, following in zip(HISTORY, bases):
        assert following in item["superseded_by"], item["stage"]
    assert len(RETIRED["retired_compatibility_pairs"]) == 9
    assert len(MOVED) == 7
    assert {f"inferrsi.{item['importer']}" for item in MOVED} < RETIRED_ROOT_MODULES
    # Every retired shell record still carries the old root file hash it was audited at.
    for item in MOVED:
        assert item["file"] == f"src/inferrsi/{item['importer']}.py"
        assert len(item["file_sha256"]) == 64
        assert not (REPO / item["file"]).exists()


def test_one_repo_types_tuple_reaches_knowledge_and_the_parser_directly():
    from inferrsi.apps.cli import arguments
    from inferrsi.knowledge import catalog as knowledge_catalog
    from inferrsi.resources import repository_packs

    assert knowledge_catalog.REPO_TYPES is repository_packs.REPO_TYPES
    # #408 A1: the Apps parser reads the tuple through the Knowledge catalog, which
    # binds it from the leaf: still one object on every route, never a copy.
    assert arguments.REPO_TYPES is repository_packs.REPO_TYPES
    assert LEAF_NAMES == ["REPO_TYPES", "repository_pack"]
    assert not hasattr(arguments, "repository_pack")
    assert not hasattr(knowledge_catalog, "repository_pack")
    assert knowledge_catalog.KNOWLEDGE_SCOPES["contribution"] == (
        *repository_packs.REPO_TYPES, "vllm_ascend", "inferrsi"
    )


def test_data_leaf_holds_the_recorded_fragment_and_locked_hash():
    assert LEAF["module"] == "inferrsi.resources.repository_packs"
    assert LEAF["file"] == "src/inferrsi/resources/repository_packs.py"
    data = (REPO / LEAF["file"]).read_bytes()
    assert data == (ROOT / "resources" / "repository_packs.py").read_bytes()
    assert hashlib.sha256(data).hexdigest() == LEAF["file_sha256"]
    # The body in the file today, and the P0b provenance text it came from.
    current = LEAF["current_fragment"]
    assert current["source"] + "\n" in data.decode("utf-8")
    assert hashlib.sha256((current["source"] + "\n").encode("utf-8")).hexdigest() == (
        current["fragment_sha256"]
    )
    revision = LEAF["resource_path_revision"]
    original = LEAF["original_fragment"]["source"]
    assert original.replace(revision["old_line"], revision["new_line"]) == current["source"]
    assert revision["new_file_sha256"] == LEAF["file_sha256"]


def test_c2_relock_moves_the_leaf_without_changing_a_byte():
    # #451 C2: the K02 hash, the recorded old-source hash and the relocated file agree,
    # so the move changed the path and nothing in the file.
    moved = LEAF["module_path_revision"]
    assert (moved["old_module"], moved["new_module"]) == (
        "inferrsi._repo_pack_data", LEAF["module"],
    )
    assert (moved["old_file"], moved["new_file"]) == (
        "src/inferrsi/_repo_pack_data.py", LEAF["file"],
    )
    assert moved["old_file_sha256"] == LEAF["resource_path_revision"]["new_file_sha256"]
    assert moved["old_file_sha256"] == moved["new_file_sha256"] == LEAF["file_sha256"]
    assert not (REPO / moved["old_file"]).exists()
    assert hashlib.sha256((REPO / moved["new_file"]).read_bytes()).hexdigest() == (
        moved["new_file_sha256"]
    )
    # The review requirement is recorded, never an approval.
    assert "requires formal architecture review" in moved["review"]
    assert "does not self-approve" in moved["review"]
    # R1 appended the C2 record after the K02 one and rewrote neither.
    k02, c2 = HISTORY[2:4]
    assert (k02["stage"], c2["stage"]) == ("K02", "C2")
    assert k02["changed_technical_leaf"] == {
        "module": moved["old_module"], "file": moved["old_file"],
    }
    assert c2["base_commit"] in k02["superseded_by"]
    assert R1_RECORD["base_commit"] in c2["superseded_by"]
    assert R1_RECORD["base_commit"] != c2["base_commit"]


def _leaf_imports(tree: ast.Module) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "the leaf has no relative import"
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_relocated_leaf_shape_matches_the_relocked_manifest_exactly():
    tree = ast.parse((REPO / LEAF["file"]).read_text(encoding="utf-8"))
    # allowed_imports is the exact import set of the relocated file, not a superset.
    assert _leaf_imports(tree) == {
        "json", "importlib.resources.files", "typing.Any", "__future__.annotations",
    }
    assert LEAF["allowed_imports"] == [
        "json", "importlib.resources", "typing.Any", "from __future__ import annotations",
    ]
    # Top level: the future import, the three stdlib imports, then the two symbols.
    kinds = [type(node).__name__ for node in tree.body]
    assert kinds == ["ImportFrom", "Import", "ImportFrom", "ImportFrom", "Assign", "FunctionDef"]
    assert tree.body[4].targets[0].id == "REPO_TYPES"
    assert tree.body[5].name == "repository_pack"
    assert LEAF["two_symbols"] == ["REPO_TYPES", "repository_pack"]
    assert "three listed stdlib imports" in LEAF["top_level_shape"]
    # The anchor is the root package joined with the physical Harness path.
    anchor = 'files("inferrsi").joinpath("harness", "data", "repo_packs", repo_type, "pack.json")'
    assert anchor in LEAF["current_fragment"]["source"]
    # The parent initializer is a docstring and nothing else.
    initializer = REPO / LEAF["module_path_revision"]["parent_initializer"]
    assert initializer == ROOT / "resources" / "__init__.py"
    body = ast.parse(initializer.read_text(encoding="utf-8")).body
    assert len(body) == 1 and isinstance(body[0], ast.Expr)
    assert isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)
    assert sorted(path.name for path in initializer.parent.iterdir() if path.is_file()) == [
        "__init__.py", "repository_packs.py",
    ]


def test_infra_inspection_imports_the_leaf_by_the_recorded_line():
    rewrite = MANIFEST["infra_inspection_rewrite"]
    lines = (REPO / rewrite["module"]).read_text(encoding="utf-8").splitlines()
    assert lines[9] == rewrite["canonical_import"]
    assert rewrite["canonical_import"] == "from ..resources.repository_packs import repository_pack"
    assert not [line for line in lines if "_repo_pack_data" in line or "catalog" in line]


def _declared(section: str) -> dict[str, frozenset[str]]:
    return {
        item["importer"]: frozenset(item["names"]) for item in LEAF[section]["importers"]
    }


def test_manifest_restates_the_exact_gate_importer_rules():
    # #412 R1: the permanent rule is one importer and one name, outside the allowlist.
    permanent = LEAF["permanent_importers"]
    temporary = R1_RECORD["retired_temporary_importers"]
    assert _declared("permanent_importers") == LEAF_IMPORTERS == {
        "inferrsi.infra.inspection": frozenset({"repository_pack"}),
    }
    # #408 A1 removed the temporary parser entry from the manifest and from the gate.
    # The removed record is kept unchanged in the history, and nothing replaced it.
    assert "temporary_importers" not in LEAF
    assert not hasattr(support, "TEMPORARY_LEAF_IMPORTERS")
    assert [(item["importer"], item["names"]) for item in temporary["importers"]] == [
        ("inferrsi.arguments", ["REPO_TYPES"])
    ]
    assert not (REPO / temporary["importers"][0]["file"]).exists()
    assert MANIFEST["compatibility_pairs"] == []
    assert permanent["importers"][0]["import_line"] == (
        MANIFEST["infra_inspection_rewrite"]["canonical_import"]
    )
    # The review requirement is recorded for both, never an approval.
    for section in (permanent, temporary):
        assert (section["stage"], section["issue"]) == ("R1", "#412")
        assert "requires formal architecture review" in section["review"]
        assert "does not self-approve" in section["review"]
    # The parser entry is temporary: A1 removes it, and it blocks until then.
    assert temporary["due"] == "A1 (#408)"
    assert "temporary leaf importers" in temporary["blocker"]
    assert "not an allowance for Apps modules in general" in temporary["rule"]
    assert "temporary leaf importers" not in support.blocker_kinds(first_wave_report())


@pytest.mark.parametrize("section", ["permanent_importers"])
def test_each_declared_importer_binds_the_leaf_by_its_one_recorded_line(section):
    for item in LEAF[section]["importers"]:
        source = (REPO / item["file"]).read_text(encoding="utf-8")
        assert source.splitlines().count(item["import_line"]) == 1, item["importer"]
        tree = ast.parse(source)
        package = item["importer"].rpartition(".")[0]
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found += [alias.name for alias in node.names if "resources" in alias.name]
            elif isinstance(node, ast.ImportFrom) and "resources" in (node.module or ""):
                parts = package.split(".")
                keep = parts[: len(parts) - node.level + 1] if node.level else []
                base = ".".join([*keep, node.module])
                if not base.startswith("inferrsi."):
                    continue
                assert node in tree.body, "the leaf import is at module level"
                found += [(base, alias.name, alias.asname) for alias in node.names]
        # That line is the file's only import of anything under inferrsi.resources.
        assert found == [(LEAF["module"], name, None) for name in item["names"]]


def _fresh(script: str) -> None:
    environment = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_package_init_and_infra_inspection_load_no_knowledge_body():
    _fresh(
        "import sys\n"
        "import inferrsi.knowledge\n"
        "assert not [m for m in sys.modules if m.startswith('inferrsi.knowledge.')]\n"
        "import inferrsi.infra.inspection\n"
        "assert 'inferrsi.catalog' not in sys.modules\n"
        "assert not [m for m in sys.modules if m.startswith('inferrsi.knowledge.')]\n"
        "assert 'inferrsi.resources.repository_packs' in sys.modules\n"
        "assert 'inferrsi._repo_pack_data' not in sys.modules\n"
        # Reading a Harness-owned pack never loads Harness.
        "from inferrsi.infra.inspection import repository_pack\n"
        "assert repository_pack('vllm')['id'] == 'vllm'\n"
        "assert not [m for m in sys.modules if m.startswith('inferrsi.harness')]\n"
    )


def test_knowledge_closure_is_clean_while_overall_stays_false():
    # K01-5: the Knowledge package exists and its closure is clean. R1 cleared the
    # allowlist and the old-run forwarders, A1 the parser entry and R2 the twelve
    # harness -> infra hits from six modules. The five runtime resource loaders (R3)
    # remain, and they keep new_core_closure_isolated false.
    report = first_wave_report()
    assert report.violations == ()
    assert report.blockers == ("runtime resource loaders: 5",)
    assert report.harness_model_infra == ()
    assert not report.new_core_closure_isolated
    assert not report.isolation_complete
