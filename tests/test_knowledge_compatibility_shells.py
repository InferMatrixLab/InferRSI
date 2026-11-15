# K01: root Knowledge names are static re-exports of the moved implementations.

from __future__ import annotations

import ast
import hashlib
import importlib
import os
import subprocess
import sys

import pytest

from tests._gate_policy_support import REPO, ROOT, blocker_kinds, first_wave_report, load_manifest

MANIFEST = load_manifest()
LEAF = MANIFEST["technical_leaf"]
LEAF_NAMES = MANIFEST["catalog_two_routes"]["neutral_leaf_export"]["symbols"]
MOVED = [item for item in MANIFEST["compatibility_pairs"] if "exports" in item]


@pytest.mark.parametrize("item", MOVED, ids=lambda item: item["importer"])
def test_root_names_are_the_moved_objects(item):
    # K01-1: identity carries signatures, defaults, exception types and Path behavior.
    root = importlib.import_module(f"inferrsi.{item['importer']}")
    moved = importlib.import_module(item["target"])
    names = [*item["exports"]["public"], *item["exports"]["private_used"]]
    for name in names:
        assert getattr(root, name) is getattr(moved, name), name
    extra = LEAF_NAMES if item["importer"] == "catalog" else []
    # REPO_TYPES is listed on both catalog routes; __all__ names it once.
    assert len(root.__all__) == len(set(root.__all__))
    assert set(root.__all__) == {*names, *extra}


def test_catalog_routes_share_one_repo_types_tuple():
    from inferrsi import arguments, catalog
    from inferrsi.knowledge import catalog as knowledge_catalog
    from inferrsi.resources import repository_packs

    assert catalog.REPO_TYPES is repository_packs.REPO_TYPES is knowledge_catalog.REPO_TYPES
    # The CLI argument surface takes the tuple through root catalog: still one object.
    assert arguments.REPO_TYPES is repository_packs.REPO_TYPES
    assert catalog.repository_pack is repository_packs.repository_pack
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
    superseded = MANIFEST["revision_history"][-1]
    assert superseded["stage"] == "K02"
    assert superseded["changed_technical_leaf"] == {
        "module": moved["old_module"], "file": moved["old_file"],
    }
    assert MANIFEST["base_commit"] in superseded["superseded_by"]


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


def test_knowledge_closure_is_isolated_while_overall_stays_false():
    # K01-5: the Knowledge package exists and its closure is clean, but the
    # allowlist and harness -> model/infra remain. S01 removed the residual.
    # After #338, runtime resource loaders keep new_core_closure_isolated
    # false; that is not a Knowledge-closure regression.
    report = first_wave_report()
    assert report.violations == ()
    assert "absent: knowledge/" not in report.blockers
    assert {
        "allowlist",
        "harness reaches model/infra",
        "runtime resource loaders",
    } <= blocker_kinds(report)
    assert "residual" not in blocker_kinds(report)
    assert not report.new_core_closure_isolated
    assert not report.isolation_complete
