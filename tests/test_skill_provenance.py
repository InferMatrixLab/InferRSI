"""Contribution-cost and integrity controls; no knowledge efficacy is measured."""

import copy
import hashlib
import json
import shutil
import subprocess

import pytest

from inferrsi import catalog
from inferrsi._skill_provenance import MANIFEST, REGISTRY, resolve_record, validate_snapshot
from tools.build_skill_index import DESTINATION, LIBRARY, build_index, render_index, source_inputs


def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Provenance test fixture",
         "-c", "user.email=fixture@example.invalid", *args],
        check=check, capture_output=True, text=True,
    )


def commit(root, message):
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", message)
    return git(root, "rev-parse", "HEAD").stdout.strip()


def write_index(root, revision):
    outputs = build_index(root, revision)
    for relative, text in outputs.items():
        path = root / DESTINATION / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return outputs


def source(root, name):
    return root / LIBRARY / "methods" / name / "SKILL.md"


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "core.autocrlf", "false")
    registry = {"schema_version": 1, "skills": {}}
    for name in ("alpha", "bravo", "charlie"):
        path = source(tmp_path, name)
        path.parent.mkdir(parents=True)
        path.write_text(f"---\nname: {name}\ndescription: Fixture {name}\n---\nOriginal body\n")
        registry["skills"][name] = {"path": f"methods/{name}", "backend": "common"}
    (tmp_path / REGISTRY).write_text(json.dumps(registry))
    pin = commit(tmp_path, "Synthetic canonical owners")
    outputs = write_index(tmp_path, pin)
    commit(tmp_path, "Synthetic baseline projections")
    return tmp_path, outputs


def test_one_owner_edit_changes_only_owner_projection_and_manifest(repository):
    root, before = repository
    source(root, "alpha").write_text(source(root, "alpha").read_text() + "New alpha evidence\n")
    pin = commit(root, "Synthetic alpha change")
    after = write_index(root, pin)
    assert {path for path in before if before[path] != after[path]} == {
        "common/skills/alpha.json", MANIFEST,
    }
    assert build_index(root, pin) == after
    commit(root, "Synthetic alpha projection")
    assert build_index(root, pin) == after
    assert git(root, "status", "--porcelain").stdout == ""


def test_registering_an_owner_does_not_rewrite_other_owners(repository):
    root, before = repository
    path = source(root, "delta")
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: delta\ndescription: New fixture\n---\nNew body\n")
    registry = json.loads((root / REGISTRY).read_text())
    registry["skills"]["delta"] = {"path": "methods/delta", "backend": "common"}
    (root / REGISTRY).write_text(json.dumps(registry))
    after = write_index(root, commit(root, "Synthetic owner registration"))
    assert {path for path in before if before[path] != after[path]} == {MANIFEST, "README.md"}
    assert set(after) - set(before) == {"common/skills/delta.json"}


@pytest.mark.parametrize("order", [("alpha", "bravo"), ("bravo", "alpha")])
def test_parallel_squash_integration_preserves_both_owners(repository, order):
    root, before = repository
    baseline = git(root, "rev-parse", "HEAD").stdout.strip()
    for name in ("alpha", "bravo"):
        git(root, "checkout", "--quiet", "-b", name, baseline)
        source(root, name).write_text(source(root, name).read_text() + f"New {name} evidence\n")
        pin = commit(root, f"Synthetic {name} source")
        write_index(root, pin)
        commit(root, f"Synthetic {name} projection")
    git(root, "checkout", "--quiet", "-b", "integration", baseline)
    for index, name in enumerate(order):
        merged = git(root, "merge", "--squash", name, check=False)
        conflicts = git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
        if index:
            assert merged.returncode == 1
            assert conflicts == [(DESTINATION / MANIFEST).as_posix()]
            # Only the mechanically generated shared snapshot conflicts. Retain
            # its prior value until combined canonical sources are committed.
            git(root, "checkout", "--ours", "--", (DESTINATION / MANIFEST).as_posix())
        else:
            assert merged.returncode == 0
        combined = commit(root, f"Synthetic squash of {name}")
        # Model the protected-main workflow: repair on a separate branch, then
        # squash that projection-only PR. Its pin already belongs to main, so
        # the second squash cannot make the source snapshot unreachable.
        git(root, "checkout", "--quiet", "-b", f"repair-{name}")
        outputs = write_index(root, combined)
        commit(root, "Regenerate combined snapshot on repair branch")
        git(root, "checkout", "--quiet", "integration")
        git(root, "merge", "--squash", f"repair-{name}")
        commit(root, "Synthetic squash of projection-only repair PR")
        assert build_index(root, combined) == outputs
        assert outputs["common/skills/charlie.json"] == before["common/skills/charlie.json"]
    for name in order:
        assert f"New {name} evidence" in source(root, name).read_text()
        raw = json.loads(outputs[f"common/skills/{name}.json"])
        assert raw["source_files"][source(root, name).relative_to(root).as_posix()] == (
            hashlib.sha256(source(root, name).read_bytes()).hexdigest()
        )
    snapshot = json.loads(outputs[MANIFEST])
    assert snapshot["source_revision"] == combined
    assert git(root, "merge-base", "--is-ancestor", combined, "HEAD").returncode == 0
    # A fresh checkout, without either contributor branch, reproduces artifacts.
    clone = root.parent / (root.name + "-clean")
    git(root, "clone", "--quiet", "--no-local", "--single-branch", "--branch", "integration",
        str(root), str(clone))
    assert build_index(clone, combined) == outputs
    shallow = root.parent / (root.name + "-shallow")
    git(root, "clone", "--quiet", "--depth=1", "--single-branch", "--branch", "integration",
        root.as_uri(), str(shallow))
    assert git(shallow, "cat-file", "-e", combined, check=False).returncode != 0
    hashes = {path: hashlib.sha256((shallow / path).read_bytes()).hexdigest()
              for path in source_inputs(shallow / LIBRARY)}
    assert render_index(shallow / LIBRARY, combined, hashes) == outputs


def test_same_owner_source_conflicts_remain_explicit(repository):
    root, _ = repository
    baseline = git(root, "rev-parse", "HEAD").stdout.strip()
    for name in ("first", "second"):
        git(root, "checkout", "--quiet", "-b", name, baseline)
        source(root, "alpha").write_text(
            source(root, "alpha").read_text().replace("Original body", name)
        )
        write_index(root, commit(root, f"Synthetic {name} source"))
        commit(root, f"Synthetic {name} projection")
    git(root, "checkout", "--quiet", "first")
    merged = git(root, "merge", "--squash", "second", check=False)
    assert merged.returncode == 1
    assert source(root, "alpha").relative_to(root).as_posix() in git(
        root, "diff", "--name-only", "--diff-filter=U"
    ).stdout.splitlines()
    with pytest.raises(ValueError, match="inputs differ"):
        build_index(root, "HEAD")


def package_fixture(root, outputs):
    package = root / "package"
    shutil.copytree(root / "src/inferrsi/data", package / "data")
    return package, package / "data/repo_packs/inferrsi/knowledge"


def test_raw_v2_resolves_exact_legacy_public_shape_and_v1_still_reads(repository, monkeypatch):
    root, outputs = repository
    package, projection = package_fixture(root, outputs)
    monkeypatch.setattr(catalog, "files", lambda _: package)
    records = catalog.knowledge_records()
    assert len(records) == 3
    snapshot = json.loads(outputs[MANIFEST])
    for record in records:
        raw_path = projection / "common/skills" / (record["title"] + ".json")
        raw = json.loads(raw_path.read_text())
        assert record == resolve_record(raw, snapshot)
        assert record["schema_version"] == 1
        assert record["sources"][0]["commit"] == snapshot["source_revision"]
        assert record["source_files"][REGISTRY] == snapshot["registry"]["sha256"]
        assert "snapshot" not in record["sources"][0]
        # Rollback/legacy package support does not require the new manifest.
        raw_path.write_text(json.dumps(record))
    (projection / MANIFEST).unlink()
    assert catalog.knowledge_records() == records


@pytest.mark.parametrize("mutation", [
    "missing", "bad-json", "schema", "bool-schema", "float-schema", "repository", "revision",
    "registry-path", "registry-hash", "source-ref", "source-path", "source-hash", "source-schema",
    "source-float-schema", "unexpected-json",
])
def test_malformed_or_missing_manifest_and_records_fail_closed(repository, monkeypatch, mutation):
    root, outputs = repository
    package, projection = package_fixture(root, outputs)
    monkeypatch.setattr(catalog, "files", lambda _: package)
    manifest = projection / MANIFEST
    snapshot = json.loads(manifest.read_text())
    raw_path = projection / "common/skills/alpha.json"
    raw = json.loads(raw_path.read_text())
    if mutation == "missing":
        manifest.unlink()
    elif mutation == "bad-json":
        manifest.write_text("{")
    elif mutation == "schema":
        snapshot["schema_version"] = 99
    elif mutation == "bool-schema":
        snapshot["schema_version"] = True
    elif mutation == "float-schema":
        snapshot["schema_version"] = 1.0
    elif mutation == "repository":
        snapshot["repository"] = "https://example.invalid/untrusted"
    elif mutation == "revision":
        snapshot["source_revision"] = "HEAD"
    elif mutation == "registry-path":
        snapshot["registry"]["path"] = "../other.json"
    elif mutation == "registry-hash":
        snapshot["registry"]["sha256"] = "unknown"
    elif mutation == "source-ref":
        raw["sources"][0]["snapshot"] = "https://example.invalid/snapshot.json"
    elif mutation == "source-path":
        raw["sources"][0]["path"] = "src/inferrsi/data/skill_library/../other.md"
    elif mutation == "source-hash":
        raw["sources"][0]["content_sha256"] = "0" * 64
    elif mutation == "source-schema":
        raw["schema_version"] = 99
    elif mutation == "source-float-schema":
        raw["schema_version"] = 2.0
    else:
        (projection / "extra.json").write_text("{}")
    if mutation not in ("missing", "bad-json"):
        manifest.write_text(json.dumps(snapshot))
    raw_path.write_text(json.dumps(raw))
    with pytest.raises((ValueError, KeyError)):
        catalog.knowledge_records()


@pytest.mark.parametrize("target,key,value", [
    (MANIFEST, "source_revision", "0" * 40),
    (MANIFEST, "registry", {}),
    ("common/skills/alpha.json", "schema_version", 99),
    ("common/skills/alpha.json", "sources", []),
])
def test_duplicate_provenance_fields_fail_even_when_last_value_is_valid(
    repository, monkeypatch, target, key, value,
):
    root, outputs = repository
    package, projection = package_fixture(root, outputs)
    monkeypatch.setattr(catalog, "files", lambda _: package)
    path = projection / target
    text = path.read_text()
    path.write_text("{" + json.dumps(key) + ": " + json.dumps(value) + "," + text[1:])
    with pytest.raises(ValueError, match="Duplicate"):
        catalog.knowledge_records()


def test_valid_looking_tampered_provenance_is_detected_by_git_check(repository):
    root, outputs = repository
    manifest = root / DESTINATION / MANIFEST
    snapshot = json.loads(outputs[MANIFEST])
    pin = snapshot["source_revision"]
    for change in ({"source_revision": "0" * 40}, {"registry": {
        "path": REGISTRY, "sha256": "0" * 64,
    }}):
        tampered = {**copy.deepcopy(snapshot), **change}
        validate_snapshot(tampered)  # Shape validation is not historical proof.
        manifest.write_text(json.dumps(tampered))
        assert build_index(root, pin)[MANIFEST] != manifest.read_text()
    with pytest.raises(subprocess.CalledProcessError):
        build_index(root, "0" * 40)


@pytest.mark.parametrize("change", ["body", "delete", "resource", "registry"])
def test_source_drift_is_never_attributed_to_the_old_snapshot(repository, change):
    root, outputs = repository
    pin = json.loads(outputs[MANIFEST])["source_revision"]
    if change == "body":
        source(root, "alpha").write_text(source(root, "alpha").read_text() + "Tampered\n")
    elif change == "delete":
        source(root, "alpha").unlink()
    elif change == "resource":
        (source(root, "alpha").parent / "new.txt").write_text("new resource")
    else:
        registry = json.loads((root / REGISTRY).read_text())
        registry["skills"]["alpha"]["backend"] = "cuda"
        (root / REGISTRY).write_text(json.dumps(registry))
    with pytest.raises((ValueError, FileNotFoundError)):
        build_index(root, pin)
