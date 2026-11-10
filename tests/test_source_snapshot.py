import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from inferrsi import _source_snapshot as snapshot
from inferrsi.catalog import search_knowledge
from tools import build_skill_index as index_builder
from tools.build_skill_index import DESTINATION, LIBRARY

PROJECT = Path(__file__).resolve().parents[1]
GENERATED = PROJECT / DESTINATION
REVISION = "a" * 40


def record_files():
    return sorted(p for p in GENERATED.glob("*/skills/*.json"))


def test_packaged_records_store_schema_two_and_resolve_to_schema_one():
    manifest = json.loads((GENERATED / snapshot.MANIFEST).read_text(encoding="utf-8"))
    records = {r["id"]: r for r in search_knowledge(repo="inferrsi", limit=100)}
    assert len(record_files()) == len(records) == 80
    for path in record_files():
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["schema_version"] == 2 and "sources" not in stored
        assert snapshot.REGISTRY not in stored["source_files"]
        public = records[stored["id"]]
        assert public == snapshot.resolve(stored, manifest)
        assert public["schema_version"] == 1
        assert public["sources"][0]["commit"] == manifest["source_revision"]
        assert public["source_files"][snapshot.REGISTRY] == manifest["registry"]["sha256"]
        assert set(public["source_files"]) == set(public["sources"][0]["paths"])
        assert list(public)[list(public).index("origin") + 1] == "sources"


def test_compact_round_trip_preserves_every_public_field_and_order():
    public = search_knowledge(repo="inferrsi", limit=1)[0]
    manifest = json.loads((GENERATED / snapshot.MANIFEST).read_text(encoding="utf-8"))
    stored = snapshot.compact(public)
    assert json.dumps(snapshot.resolve(stored, manifest)) == json.dumps(public)


@pytest.mark.parametrize("mutation", [
    "extra", "missing_registry", "short_revision", "wrong_repository", "wrong_path",
    "bad_digest", "boolean_version", "list",
])
def test_invalid_snapshot_never_resolves(mutation):
    manifest = json.loads((GENERATED / snapshot.MANIFEST).read_text(encoding="utf-8"))
    stored = json.loads(record_files()[0].read_text(encoding="utf-8"))
    bad = copy.deepcopy(manifest)
    if mutation == "extra":
        bad["unexpected"] = True
    elif mutation == "missing_registry":
        del bad["registry"]
    elif mutation == "short_revision":
        bad["source_revision"] = bad["source_revision"][:8]
    elif mutation == "wrong_repository":
        bad["repository"] = "https://github.com/example/other"
    elif mutation == "wrong_path":
        bad["registry"]["path"] = "skill-index.json"
    elif mutation == "bad_digest":
        bad["registry"]["sha256"] = "XYZ"
    elif mutation == "boolean_version":
        bad["schema_version"] = True
    else:
        bad = []
    with pytest.raises(ValueError):
        snapshot.resolve(stored, bad)


@pytest.mark.parametrize(
    "mutation", ["v1", "sources", "registry_hash", "missing_entry", "no_origin"])
def test_invalid_stored_record_never_resolves(mutation):
    manifest = json.loads((GENERATED / snapshot.MANIFEST).read_text(encoding="utf-8"))
    stored = json.loads(record_files()[0].read_text(encoding="utf-8"))
    if mutation == "v1":
        stored["schema_version"] = 1
    elif mutation == "sources":
        stored["sources"] = []
    elif mutation == "registry_hash":
        stored["source_files"][snapshot.REGISTRY] = "0" * 64
    elif mutation == "missing_entry":
        stored["source_files"].pop("src/inferrsi/" + stored["skill_documents"]["original"])
    else:
        del stored["origin"]
    with pytest.raises(ValueError):
        snapshot.resolve(stored, manifest)


# Fixture identity and settings; hosted runners have no global Git identity.
GIT = ["git", "-c", "user.name=Snapshot fixture", "-c", "user.email=fixture@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


def _git(root, *args):
    return subprocess.run(
        [*GIT, *args], cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _library(root, owners):
    library = root / LIBRARY
    registry = {"schema_version": 1, "skills": {
        name: {"path": f"methods/{name}", "backend": "common"} for name in owners}}
    library.mkdir(parents=True, exist_ok=True)
    (library / "skill-index.json").write_text(json.dumps(registry), encoding="utf-8")
    for name in owners:
        (library / "methods" / name).mkdir(parents=True, exist_ok=True)
        _write_skill(root, name, "Original body")


def _write_skill(root, name, body):
    path = root / LIBRARY / "methods" / name / "SKILL.md"
    path.write_text(f"---\nname: {name}\ndescription: Fixture {name}\n---\n{body}\n",
                    encoding="utf-8", newline="\n")


def _generate(root, monkeypatch):
    revision = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(index_builder, "PROJECT", root)
    assert index_builder.main(["--source-revision", revision]) == 0
    assert index_builder.main(["--source-revision", revision, "--check"]) == 0
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "Regenerate projections")


def _changed(root, base):
    return set(_git(root, "diff", "--name-only", base, "HEAD").splitlines())


def _seed(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _library(root, ["alpha", "bravo", "charlie"])
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "Seed library")
    _generate(root, monkeypatch)
    return root


def _contribute(root, monkeypatch, branch, owner, body):
    _git(root, "switch", "-q", "-c", branch, "main")
    _write_skill(root, owner, body)
    _git(root, "commit", "-q", "-am", f"Edit {owner}")
    _generate(root, monkeypatch)
    _git(root, "switch", "-q", "main")


def test_single_owner_edit_rewrites_only_its_record_and_the_snapshot(tmp_path, monkeypatch):
    root = _seed(tmp_path, monkeypatch)
    base = _git(root, "rev-parse", "HEAD")
    _write_skill(root, "alpha", "Changed body")
    _git(root, "commit", "-q", "-am", "Edit alpha")
    edit = _git(root, "rev-parse", "HEAD")
    _generate(root, monkeypatch)
    generated = DESTINATION.as_posix()
    assert _git(root, "diff", "--name-only", edit, "HEAD").splitlines() == sorted([
        f"{generated}/{snapshot.MANIFEST}", f"{generated}/common/skills/alpha.json",
    ])
    assert f"{generated}/common/skills/bravo.json" not in _changed(root, base)
    # Regeneration from the same source is byte-identical.
    assert index_builder.main(["--source-revision", edit, "--check"]) == 0


@pytest.mark.parametrize("order", [("alpha", "bravo"), ("bravo", "alpha")])
def test_parallel_owner_edits_integrate_in_either_order(tmp_path, monkeypatch, order):
    root = _seed(tmp_path, monkeypatch)
    seeded = _git(root, "rev-parse", "HEAD")
    for owner in ("alpha", "bravo"):
        _contribute(root, monkeypatch, f"edit-{owner}", owner, f"{owner} contribution")
    generated = DESTINATION.as_posix()
    for owner in order:
        merge = subprocess.run([*GIT, "merge", "--no-ff", "-q", "--no-edit", f"edit-{owner}"],
                               cwd=root, capture_output=True, text=True)
        if merge.returncode:
            # Only the shared snapshot may collide (the fixture has no coverage view);
            # take either side, then regenerate it from the merged source.
            conflicted = set(_git(root, "diff", "--name-only", "--diff-filter=U").splitlines())
            assert conflicted == {f"{generated}/{snapshot.MANIFEST}"}
            _git(root, "checkout", "--ours", "--", f"{generated}/{snapshot.MANIFEST}")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "--no-edit")
        _generate(root, monkeypatch)
    for owner in ("alpha", "bravo"):
        body = (root / LIBRARY / "methods" / owner / "SKILL.md").read_text(encoding="utf-8")
        assert f"{owner} contribution" in body
        stored = json.loads((root / generated / f"common/skills/{owner}.json").read_text(
            encoding="utf-8"))
        entry = f"{LIBRARY.as_posix()}/methods/{owner}/SKILL.md"
        assert stored["source_files"][entry] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    # The untouched owner's stored record never changes.
    charlie = f"{generated}/common/skills/charlie.json"
    assert _git(root, "rev-parse", f"{seeded}:{charlie}") == _git(
        root, "rev-parse", f"HEAD:{charlie}")


def test_same_owner_divergent_edits_remain_an_explicit_conflict(tmp_path, monkeypatch):
    root = _seed(tmp_path, monkeypatch)
    _contribute(root, monkeypatch, "first", "alpha", "First version")
    _contribute(root, monkeypatch, "second", "alpha", "Second version")
    _git(root, "merge", "-q", "--no-edit", "first")
    merge = subprocess.run([*GIT, "merge", "--no-edit", "second"], cwd=root,
                           capture_output=True, text=True)
    assert merge.returncode != 0 and "CONFLICT" in merge.stdout
    conflicted = set(_git(root, "diff", "--name-only", "--diff-filter=U").splitlines())
    assert f"{LIBRARY.as_posix()}/methods/alpha/SKILL.md" in conflicted


def test_check_detects_tampered_or_missing_snapshot(tmp_path, monkeypatch):
    root = _seed(tmp_path, monkeypatch)
    revision = _git(root, "rev-parse", "HEAD~1")
    manifest = root / DESTINATION / snapshot.MANIFEST
    original = manifest.read_text(encoding="utf-8")
    manifest.write_text(original.replace(revision, "b" * 40), encoding="utf-8")
    assert index_builder.main(["--source-revision", revision, "--check"]) == 1
    manifest.unlink()
    assert index_builder.main(["--source-revision", revision, "--check"]) == 1
    manifest.write_text(original, encoding="utf-8")
    record = root / DESTINATION / "common/skills/alpha.json"
    stored = json.loads(record.read_text(encoding="utf-8"))
    stored["sources"] = []
    record.write_text(json.dumps(stored), encoding="utf-8")
    assert index_builder.main(["--source-revision", revision, "--check"]) == 1
