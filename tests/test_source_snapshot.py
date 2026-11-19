import copy
import hashlib
import inspect
import json
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

from inferrsi.knowledge import _source_snapshot as snapshot
from inferrsi.knowledge.catalog import INPUTS, recommendations, search_knowledge, skill_views
from tools import build_skill_index as index_builder
from tools.build_skill_index import DESTINATION

PROJECT = Path(__file__).resolve().parents[1]
GENERATED = PROJECT / DESTINATION
REVISION = "a" * 40
# These fixtures hold their corpus at the recorded location, where the physical
# root and the pinned prefix are the same. After the K02 re-pin the repository
# agrees on src/inferrsi/knowledge/data/skill_library as well.
LIBRARY = index_builder.PINNED_LIBRARY


def test_public_projection_implementation_is_a_protected_knowledge_path():
    policy = json.loads((PROJECT / ".github/knowledge-model-policy.json").read_bytes())
    for builder in (skill_views, recommendations):
        path = Path(inspect.getfile(builder)).resolve().relative_to(PROJECT).as_posix()
        assert any(fnmatchcase(path, pattern) for pattern in policy["protected_paths"]), path


def test_compiled_inputs_expand_to_public_records():
    root = GENERATED.parent
    inputs = json.loads((GENERATED / INPUTS).read_bytes())
    records = list(skill_views(root))
    manifest = json.loads((GENERATED / snapshot.MANIFEST).read_bytes())
    assert {p.name for p in GENERATED.iterdir()} == {INPUTS, snapshot.MANIFEST}
    assert len(records) == len(inputs) == 81
    public = search_knowledge(repo="inferrsi", limit=100)
    assert {r["id"] for r in records} == {r["id"] for r in public}
    for record in records:
        assert set(inputs[record["title"]]) == {"files", "header"}
        assert record["schema_version"] == 1
        assert record["sources"][0]["commit"] == manifest["source_revision"]
        assert record["source_files"][snapshot.REGISTRY] == manifest["registry"]["sha256"]
        assert list(record["source_files"]) == record["sources"][0]["paths"]


def test_historical_schema_two_round_trip_preserves_public_field_order():
    public = search_knowledge(repo="inferrsi", limit=1)[0]
    manifest = json.loads((GENERATED / snapshot.MANIFEST).read_bytes())
    stored = snapshot.compact(public)
    assert stored["schema_version"] == snapshot.STORED_SCHEMA == 2
    assert "sources" not in stored and snapshot.REGISTRY not in stored["source_files"]
    assert json.dumps(snapshot.resolve(stored, manifest)) == json.dumps(public)
    stored["source_files"].pop(snapshot.source_entry(public["skill_documents"]["original"]))
    with pytest.raises(ValueError, match="lacks its entry hash"):
        snapshot.resolve(stored, manifest)


@pytest.mark.parametrize("mutation", [
    "extra", "missing_registry", "short_revision", "wrong_repository", "wrong_path",
    "bad_digest", "boolean_version", "list",
])
def test_invalid_snapshot_never_resolves(mutation):
    manifest = json.loads((GENERATED / snapshot.MANIFEST).read_text(encoding="utf-8"))
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
        snapshot._snapshot(bad)


@pytest.mark.parametrize(
    "mutation",
    ["missing_owner", "extra_owner", "missing_entry", "bad_header", "bad_hash", "escape"],
)
def test_invalid_compiled_owner_is_rejected(tmp_path, monkeypatch, mutation):
    root = _seed(tmp_path, monkeypatch) / LIBRARY
    inputs = root / "_compiled" / INPUTS
    data = json.loads(inputs.read_bytes())
    if mutation == "missing_owner":
        del data["alpha"]
    elif mutation == "extra_owner":
        data["other"] = data["alpha"]
    elif mutation == "missing_entry":
        del data["alpha"]["files"]["SKILL.md"]
    elif mutation == "bad_hash":
        data["alpha"]["files"]["SKILL.md"] = "invalid"
    elif mutation == "escape":
        data["alpha"]["files"]["../outside"] = "f" * 64
    else:
        data["alpha"]["header"]["name"] = "other"
    inputs.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        list(skill_views(root))


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
    monkeypatch.setattr(index_builder, "LIBRARY", LIBRARY)
    assert index_builder.main(["--source-revision", revision]) == 0
    assert index_builder.main(["--source-revision", revision, "--check"]) == 0
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "Regenerate projections")


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
        f"{generated}/{snapshot.MANIFEST}", f"{generated}/{INPUTS}",
    ])
    def bravo(ref):
        return json.loads(_git(root, "show", f"{ref}:{generated}/{INPUTS}"))["bravo"]
    assert bravo(base) == bravo("HEAD")
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
            expected = {f"{generated}/{snapshot.MANIFEST}", f"{generated}/{INPUTS}"}
            assert conflicted and conflicted <= expected
            _git(root, "checkout", "--ours", "--", *sorted(conflicted))
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "--no-edit")
        _generate(root, monkeypatch)
    for owner in ("alpha", "bravo"):
        body = (root / LIBRARY / "methods" / owner / "SKILL.md").read_text(encoding="utf-8")
        assert f"{owner} contribution" in body
        stored = json.loads((root / generated / INPUTS).read_bytes())[owner]
        assert stored["files"]["SKILL.md"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    def charlie(ref):
        return json.loads(_git(root, "show", f"{ref}:{generated}/{INPUTS}"))["charlie"]
    assert charlie(seeded) == charlie("HEAD")


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
    manifest.write_bytes(original.replace("\n", "\r\n").encode("utf-8"))
    assert index_builder.main(["--source-revision", revision, "--check"]) == 1
    manifest.write_text(original.replace(revision, "b" * 40), encoding="utf-8")
    assert index_builder.main(["--source-revision", revision, "--check"]) == 1
    manifest.unlink()
    assert index_builder.main(["--source-revision", revision, "--check"]) == 1
    manifest.write_text(original, encoding="utf-8", newline="\n")
    record = root / DESTINATION / INPUTS
    stored = json.loads(record.read_text(encoding="utf-8"))
    stored["sources"] = []
    record.write_text(json.dumps(stored), encoding="utf-8")
    assert index_builder.main(["--source-revision", revision, "--check"]) == 1
