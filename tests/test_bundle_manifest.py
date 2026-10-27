import hashlib
import json
from collections import Counter

import pytest

from inferrsi import knowledge_operations
from inferrsi.knowledge_operations import Bundle, RevisionConflict


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


@pytest.fixture
def bundle():
    content = {
        "support/z.txt": b"last reference",
        "SKILL.md": "Core procedure: café".encode(),
        "support/a.txt": b"first reference",
    }
    members = {path: _hash(data) for path, data in content.items() if path.startswith("support/")}
    return Bundle(
        {
            "id": "fixture",
            "kind": "skill",
            "sources": [{"type": "unknown"}],
            "applicability": {},
            "state": "candidate",
            "limitations": [],
            "attribution": "fixture",
            "entrypoint": "SKILL.md",
            "required_resources": ["SKILL.md", "support/a.txt"],
        },
        content,
        {
            "support/a.txt": "sha256:" + _hash(content["support/a.txt"]),
            "support": "sha256:" + _hash(_json(members)),
        },
    )


def test_manifest_and_revision_preserve_complete_digest_formula(bundle):
    expected = {
        "metadata": bundle.metadata,
        "resources": {path: _hash(data) for path, data in sorted(bundle.content.items())},
        "dependencies": dict(sorted(bundle.dependencies.items())),
    }
    manifest = bundle.manifest()
    assert manifest == expected
    assert list(manifest["resources"]) == sorted(bundle.content)
    assert bundle.revision == "sha256:" + _hash(_json(expected))
    assert bundle.view(material=True) == {
        **bundle.metadata,
        "revision": bundle.revision,
        "resources": expected["resources"],
        "dependencies": expected["dependencies"],
        "content": bundle.content["SKILL.md"].decode(),
    }


def test_manifest_hashes_each_resource_once_per_call(bundle, monkeypatch):
    calls = Counter()

    def counted(data):
        calls[data] += 1
        return _hash(data)

    monkeypatch.setattr(knowledge_operations, "_hash", counted)
    for count in (1, 2):
        bundle.manifest()
        assert all(calls[data] == count for data in bundle.content.values())
        assert sum(calls.values()) == count * (len(bundle.content) + 1)


def test_manifest_rechecks_changed_bytes_and_metadata(bundle):
    original = bundle.revision
    bundle.content["SKILL.md"] = b"Changed core procedure"
    changed = bundle.revision
    assert changed != original
    assert bundle.manifest()["resources"]["SKILL.md"] == _hash(bundle.content["SKILL.md"])
    bundle.metadata["state"] = "changed"
    assert bundle.revision != changed


@pytest.mark.parametrize("path", ["support/a.txt", "support/z.txt"])
def test_manifest_rechecks_replaced_dependency_bytes(bundle, path):
    bundle.manifest()
    bundle.content[path] = b"Changed reference"
    with pytest.raises(RevisionConflict, match="Dependency bytes disagree"):
        bundle.manifest()


@pytest.mark.parametrize(
    ("path", "message"),
    [("SKILL.md", "Missing entrypoint"), ("support/a.txt", "Missing required resource")],
)
def test_manifest_rechecks_deleted_resources(bundle, path, message):
    bundle.manifest()
    del bundle.content[path]
    with pytest.raises(ValueError, match=message):
        bundle.manifest()


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a\\b", "C:/outside", "a/../b"])
def test_manifest_rechecks_new_unsafe_content_paths(bundle, path):
    bundle.manifest()
    bundle.content[path] = b"Unsafe resource"
    with pytest.raises(ValueError, match="Unsafe bundle path"):
        bundle.manifest()


@pytest.mark.parametrize(
    ("required", "error", "message"),
    [
        ("missing.txt", ValueError, "Missing required resource"),
        ("../outside", ValueError, "Unsafe bundle path"),
        (1, TypeError, None),
        (["SKILL.md"], TypeError, None),
    ],
)
def test_manifest_rechecks_changed_required_resources(bundle, required, error, message):
    bundle.manifest()
    bundle.metadata["required_resources"].append(required)
    with pytest.raises(error, match=message):
        bundle.manifest()


@pytest.mark.parametrize(
    ("path", "revision", "error", "message"),
    [
        ("support/a.txt", "sha256:" + "0" * 64, RevisionConflict, "bytes disagree"),
        ("support/a.txt", "unresolved", ValueError, "resolved content revision"),
        ("absent", "sha256:" + "0" * 64, ValueError, "Missing dependency"),
        ("../outside", "sha256:" + "0" * 64, ValueError, "Unsafe bundle path"),
    ],
)
def test_manifest_rechecks_changed_dependencies(bundle, path, revision, error, message):
    bundle.manifest()
    bundle.dependencies[path] = revision
    with pytest.raises(error, match=message):
        bundle.manifest()
