"""Integrity, persistence and concurrent first use of the compact host runtime."""

import hashlib
import importlib.util
import io
import json
import stat
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

BOOTSTRAP = Path(__file__).resolve().parents[1] / (
    "plugins/workswarm/inferrsi/skills/inferrsi/scripts/inferrsi.py")
spec = importlib.util.spec_from_file_location("workswarm_bootstrap", BOOTSTRAP)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def manifest_for(content):
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
    identity = "\n".join(f"{name}\0{digest}" for name, digest in sorted(hashes.items()))
    return {"files": hashes, "content_sha256": hashlib.sha256(identity.encode()).hexdigest()}


def archive_for(content):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in content.items():
            entry = zipfile.ZipInfo()
            entry.filename = name  # Preserve malicious backslashes on Windows, too.
            archive.writestr(entry, data)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


@pytest.mark.parametrize("names", [
    ["../escape.py"], ["inferrsi/../escape.py"], ["inferrsi//module.py"],
    ["inferrsi\\module.py"], ["inferrsi/CON.txt"], ["inferrsi/module.py."],
    ["inferrsi/A.py", "inferrsi/a.py"], ["inferrsi/Data/a.md", "inferrsi/data/b.md"],
])
def test_payload_rejects_unsafe_paths(names):
    content = {name: b"must not execute" for name in names}
    with archive_for(content) as archive, pytest.raises(ValueError, match="Unsafe|must cover"):
        bootstrap.verified_files(archive, manifest_for(content))


def test_payload_rejects_changed_bytes_and_unlisted_modules():
    content = {"inferrsi/__init__.py": b"original"}
    for changed in ({"inferrsi/__init__.py": b"changed"},
                    {**content, "inferrsi/shadow.py": b"unlisted"}):
        with archive_for(changed) as archive, pytest.raises(ValueError):
            bootstrap.verified_files(archive, manifest_for(content))


def test_payload_rejects_links():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        entry = zipfile.ZipInfo("inferrsi/link.py")
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, b"target")
    with zipfile.ZipFile(buffer) as archive, pytest.raises(ValueError, match="Unsafe"):
        bootstrap.verified_files(archive, manifest_for({"inferrsi/link.py": b"target"}))


@pytest.fixture
def cached_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    content = {"inferrsi/__init__.py": b"# canonical bytes",
               "inferrsi/data/reference.md": b"persistent resource"}
    manifest = json.dumps(manifest_for(content)).encode()
    return lambda: bootstrap.cache_runtime(manifest, b"# shared launcher", content)


def test_cache_is_persistent_and_concurrent_first_use_is_atomic(cached_runtime):
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: cached_runtime(), range(2)))
    assert first == second == cached_runtime()
    root = first.parents[3]
    assert (root / "runtime/inferrsi/data/reference.md").read_bytes() == b"persistent resource"
    assert not list(root.parent.glob(".staging-*"))


@pytest.mark.parametrize("tamper", ["changed", "missing", "extra"])
def test_cache_rejects_modified_missing_or_extra_files(cached_runtime, tamper):
    root = cached_runtime().parents[3]
    target = root / "runtime/inferrsi/__init__.py"
    if tamper == "changed":
        target.write_bytes(b"must not execute")
    elif tamper == "missing":
        target.unlink()
    else:
        (root / "runtime/shadow.py").write_bytes(b"must not import")
    with pytest.raises(ValueError, match="cache verification failed"):
        cached_runtime()


def test_cache_rejects_linked_parent_before_writing(cached_runtime, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / "InferRSI").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks is unavailable")
    with pytest.raises(ValueError, match="links or reparse points"):
        cached_runtime()
    assert list(outside.iterdir()) == []


def test_cache_rejects_relative_base_without_writing(cached_runtime, monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", "relative-cache")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="base must be absolute"):
        cached_runtime()
    assert not (tmp_path / "relative-cache").exists()
