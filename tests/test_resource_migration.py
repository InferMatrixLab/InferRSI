"""K02 physical resource migration: the three loader classes resolve one resource set.

The corpus lives under ``src/inferrsi/knowledge/data`` and the repository pack
descriptions under ``src/inferrsi/harness/data``. Logical bundle keys and pinned
record paths keep their old spelling, so content bytes and Bundle revisions are
unchanged by the move.

An installed wheel outside the checkout is covered by
``tests/test_knowledge_fresh_install.py`` and ``tests/check_installed.py``; under
``pythonpath = ["src"]`` the importlib anchor here resolves to the same checkout
directory, so this module proves the resolved paths and the packaging contract
rather than a separate installation.
"""

import hashlib
from importlib.resources import files
from pathlib import Path

import pytest

from inferrsi.catalog import REPO_TYPES, repository_pack
from inferrsi.knowledge import _source_snapshot
from inferrsi.knowledge_operations import KnowledgeReader

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: pytest supplies tomli.
    import tomli as tomllib

PROJECT = Path(__file__).resolve().parents[1]
CHECKOUT = PROJECT / "src" / "inferrsi"
KNOWLEDGE_DATA = CHECKOUT / "knowledge" / "data"
HARNESS_DATA = CHECKOUT / "harness" / "data"
RESOURCE_ROOTS = (("knowledge", "data"), ("harness", "data"))


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checkout_inventory() -> dict[str, str]:
    found = {}
    for root in (KNOWLEDGE_DATA, HARNESS_DATA):
        for path in root.rglob("*"):
            # An installer byte-compiles packaged scripts; caches are not resources.
            if path.is_file() and "__pycache__" not in path.parts:
                found[path.relative_to(CHECKOUT).as_posix()] = _digest(path.read_bytes())
    return found


def _traversable_inventory() -> dict[str, str]:
    found = {}
    for parts in RESOURCE_ROOTS:
        pending = [(files("inferrsi").joinpath(*parts), "/".join(parts))]
        while pending:
            node, name = pending.pop()
            for child in node.iterdir():
                relative = f"{name}/{child.name}"
                if child.is_dir():
                    if child.name != "__pycache__":
                        pending.append((child, relative))
                else:
                    found[relative] = _digest(child.read_bytes())
    return found


@pytest.fixture(scope="module")
def checkout_inventory() -> dict[str, str]:
    return _checkout_inventory()


def test_old_resource_tier_is_gone_and_the_two_roots_hold_every_resource(checkout_inventory):
    assert not (CHECKOUT / "data").exists(), "the old sibling data/ tier must not remain"
    knowledge = [name for name in checkout_inventory if name.startswith("knowledge/data/")]
    harness = [name for name in checkout_inventory if name.startswith("harness/data/")]
    assert len(knowledge) + len(harness) == len(checkout_inventory)
    assert sorted(harness) == sorted(
        f"harness/data/repo_packs/{repo}/pack.json" for repo in REPO_TYPES
    )
    for group in ("skill_library", "knowledge_packs", "research_profiles", "repo_packs"):
        assert any(name.startswith(f"knowledge/data/{group}/") for name in knowledge), group


def test_importlib_and_checkout_loaders_resolve_the_same_files_and_bytes(checkout_inventory):
    assert _traversable_inventory() == checkout_inventory


def test_plugin_physical_root_carries_the_same_resource_set(tmp_path, checkout_inventory):
    from tools.plugin_bundle import _io_path, bundle_runtime

    runtime = tmp_path / "runtime"
    bundle_runtime(CHECKOUT, runtime, plugin_version="0.0.0", runtime_version="0.0.0")
    # The deepest canonical resources need an extended path on Windows, the same
    # way the real builder stages them.
    staged_root = _io_path(runtime) / "inferrsi"
    staged = {}
    for path in staged_root.rglob("*"):
        relative = path.relative_to(staged_root).as_posix()
        if (path.is_file() and "__pycache__" not in path.parts
                and relative.startswith(("knowledge/data/", "harness/data/"))):
            staged[relative] = _digest(path.read_bytes())
    assert staged == checkout_inventory


def test_package_data_globs_cover_every_resource_including_subdirectories(checkout_inventory):
    metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set()
    for package, patterns in metadata["tool"]["setuptools"]["package-data"].items():
        root = PROJECT / "src" / Path(*package.split("."))
        for pattern in patterns:
            for path in root.glob(pattern):
                if path.is_file():
                    declared.add(path.relative_to(CHECKOUT).as_posix())
    missing = set(checkout_inventory) - declared
    assert not missing, f"resources a wheel would omit: {sorted(missing)[:5]}"


def test_pack_descriptions_read_from_the_harness_root(checkout_inventory):
    for repo in REPO_TYPES:
        assert repository_pack(repo)["id"] == repo
        assert f"harness/data/repo_packs/{repo}/pack.json" in checkout_inventory
    with pytest.raises(ValueError, match="Unknown repository type"):
        repository_pack("not-a-repository")


def test_bundle_keys_and_pinned_provenance_survive_the_physical_move():
    bundle = KnowledgeReader().read("inferrsi.ascend.skills.ascend_operator_profiling")
    library = [key for key in bundle.content if key != "record.json"]
    assert library and all(key.startswith("data/skill_library/") for key in library)
    assert "data/skill_library" in bundle.dependencies
    # After the explicit re-pin, LIBRARY agrees with today's checkout path.
    assert _source_snapshot.LIBRARY == "src/inferrsi/knowledge/data/skill_library"
    snapshot = KNOWLEDGE_DATA / "repo_packs" / "inferrsi" / "knowledge" / _source_snapshot.MANIFEST
    assert f'"{_source_snapshot.REGISTRY}"' in snapshot.read_text(encoding="utf-8")
