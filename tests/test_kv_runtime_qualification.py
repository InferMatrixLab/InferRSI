"""Metadata/runtime probes only: no submitted artifact is run by these unit tests."""

import importlib.metadata
import json
import time
from pathlib import Path

import pytest

from tools import kv_runtime_qualification as runtime


def fixture(tmp_path):
    mount = tmp_path / "runtime"
    mount.mkdir()
    (mount / "stdlib.py").write_text("# trusted standard runtime\n")
    sensitive = tmp_path / "private/skill_library/SKILL.md"
    sensitive.parent.mkdir(parents=True)
    sensitive.write_text("Known sensitive knowledge bytes. " * 10)
    return mount, sensitive


def test_runtime_inventory_keeps_only_digest_counts_and_no_absolute_paths(tmp_path):
    mount, sensitive = fixture(tmp_path)
    result, escapes = runtime.inventory(
        [(mount, Path("/runtime"))], [sensitive], time.monotonic() + 5
    )
    assert result["verdict"] == "PASS" and result["nodes"] == 2 and escapes == []
    assert str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize("variant", ["named_package", "renamed_copy", "symlink_sensitive"])
def test_runtime_inventory_rejects_sensitive_data_inside_mounted_tree(tmp_path, variant):
    mount, sensitive = fixture(tmp_path)
    if variant == "named_package":
        (mount / "inferrsi").mkdir()
    elif variant == "renamed_copy":
        (mount / "unremarkable.txt").write_bytes(sensitive.read_bytes())
    else:
        (mount / "alias").symlink_to(sensitive)
    result, _ = runtime.inventory([(mount, Path("/runtime"))], [sensitive], time.monotonic() + 5)
    assert result["verdict"] == "FAIL"


def test_escaped_symlink_requires_same_profile_probe_not_assumed_safe(tmp_path, monkeypatch):
    mount, sensitive = fixture(tmp_path)
    unrelated = tmp_path / "external.txt"
    unrelated.write_text("outside\n")
    (mount / "escape").symlink_to(unrelated)
    monkeypatch.setattr(runtime, "sensitive_files", lambda *a: [sensitive])
    monkeypatch.setattr(runtime, "runtime_mounts", lambda *a: [(mount, Path("/runtime"))])
    forbidden = []

    def probe(output, deadline, paths):
        forbidden.extend(paths)
        raise runtime.kv.SandboxUnavailable("unavailable")

    monkeypatch.setattr(runtime.kv, "probe_isolation", probe)
    result = runtime.qualify(
        tmp_path / "out",
        time.monotonic() + 5,
        root=tmp_path,
        independent=tmp_path,
        fixtures=tmp_path,
        knowledge_root=tmp_path,
    )
    assert "/runtime/escape" in forbidden
    assert str(sensitive) in forbidden
    assert result["verdict"] == "INCONCLUSIVE"
    assert len([p for p in forbidden if p.endswith("-canary.txt")]) == 2


def test_bind_source_symlink_inventories_actual_mounted_contents(tmp_path):
    mount, sensitive = fixture(tmp_path)
    alias = tmp_path / "bind-source"
    alias.symlink_to(mount, target_is_directory=True)
    (mount / "renamed.txt").write_bytes(sensitive.read_bytes())
    result, escapes = runtime.inventory(
        [(alias, Path("/runtime"))], [sensitive], time.monotonic() + 5
    )
    assert result["verdict"] == "FAIL" and result["nodes"] == 3
    assert escapes == []


def test_complete_renamed_large_hidden_corpus_is_rejected(tmp_path):
    from tools import qualify_kv_reclamation as task

    mount, _ = fixture(tmp_path)
    sensitive = task.INDEPENDENT / "fixtures.json"
    assert sensitive.stat().st_size > 65536
    (mount / "large-data.bin").write_bytes(sensitive.read_bytes())
    result, _ = runtime.inventory([(mount, Path("/runtime"))], [sensitive], time.monotonic() + 5)
    assert result["verdict"] == "FAIL"


def test_hash_byte_limit_fails_closed(tmp_path, monkeypatch):
    mount, sensitive = fixture(tmp_path)
    monkeypatch.setattr(runtime, "MAX_HASH_BYTES", 1)
    with pytest.raises(ValueError, match="hash byte limit"):
        runtime.inventory([(mount, Path("/runtime"))], [sensitive], time.monotonic() + 5)


def test_failed_inventory_does_not_probe_or_claim_success(tmp_path, monkeypatch):
    mount, sensitive = fixture(tmp_path)
    (mount / "inferrsi").mkdir()
    monkeypatch.setattr(runtime, "sensitive_files", lambda *a: [sensitive])
    monkeypatch.setattr(runtime, "runtime_mounts", lambda *a: [(mount, Path("/runtime"))])
    monkeypatch.setattr(runtime.kv, "probe_isolation", lambda *a: pytest.fail("inventory rejected"))
    result = runtime.qualify(
        tmp_path / "out",
        time.monotonic() + 5,
        root=tmp_path,
        independent=tmp_path,
        fixtures=tmp_path,
        knowledge_root=tmp_path,
    )
    assert result["verdict"] == "FAIL"


def test_unreadable_enumeration_is_inconclusive(tmp_path, monkeypatch):
    mount, sensitive = fixture(tmp_path)
    monkeypatch.setattr(runtime, "sensitive_files", lambda *a: [sensitive])
    monkeypatch.setattr(runtime, "runtime_mounts", lambda *a: [(mount, Path("/runtime"))])

    def denied(*a):
        raise PermissionError("private-path-canary")

    monkeypatch.setattr(runtime.os, "scandir", denied)
    result = runtime.qualify(
        tmp_path / "out",
        time.monotonic() + 5,
        root=tmp_path,
        independent=tmp_path,
        fixtures=tmp_path,
        knowledge_root=tmp_path,
    )
    assert result["verdict"] == "INCONCLUSIVE"
    assert "private-path-canary" not in json.dumps(result)


def test_actual_package_paths_and_oracle_are_regular_forbidden_files():
    from tools import qualify_kv_reclamation as task

    files = runtime.sensitive_files(
        task.ROOT,
        task.INDEPENDENT,
        task.FIXTURES,
        task.ROOT / "src/inferrsi/data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes",
        time.monotonic() + 10,
    )
    assert task.INDEPENDENT / "oracle.py" in files
    assert task.INDEPENDENT / "fixtures.json" in files
    assert task.FIXTURES / "reference.py" in files
    assert all(p.is_file() for p in files)
    assert any("skill_library" in p.parts for p in files)


def test_missing_required_sensitive_anchor_is_not_silently_dropped(tmp_path):
    with pytest.raises(ValueError, match="anchor missing"):
        runtime.sensitive_files(tmp_path, tmp_path, tmp_path, tmp_path, time.monotonic() + 5)


def test_inventory_deadline_and_node_limit_fail_closed(tmp_path, monkeypatch):
    mount, sensitive = fixture(tmp_path)
    with pytest.raises(ValueError, match="inventory limit"):
        runtime.inventory([(mount, Path("/runtime"))], [sensitive], time.monotonic() - 1)
    monkeypatch.setattr(runtime, "MAX_NODES", 1)
    with pytest.raises(ValueError, match="inventory limit"):
        runtime.inventory([(mount, Path("/runtime"))], [sensitive], time.monotonic() + 5)


def package(directory):
    directory.mkdir(parents=True)
    (directory / "__init__.py").write_text("# synthetic package\n")
    (directory / "data").mkdir()
    (directory / "data/private.json").write_text('{"synthetic_sensitive_copy": true}\n')
    return directory


def installed_distribution(metadata, *, record=None, source_list=None, direct_url=None):
    metadata.mkdir(parents=True)
    (metadata / ("PKG-INFO" if metadata.suffix == ".egg-info" else "METADATA")).write_text(
        "Metadata-Version: 2.1\nName: inferrsi\nVersion: 0.1.0\n"
    )
    for name, value in (("RECORD", record), ("SOURCES.txt", source_list),
                        ("direct_url.json", direct_url)):
        if value is not None:
            (metadata / name).write_text(value)
    return importlib.metadata.PathDistribution(metadata)


def installed_files(distribution, monkeypatch):
    from tools import qualify_kv_reclamation as task

    monkeypatch.setattr(runtime.importlib.metadata, "distributions", lambda: [distribution])
    return runtime.sensitive_files(
        task.ROOT, task.INDEPENDENT, task.FIXTURES,
        task.ROOT / "src/inferrsi/data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes",
        time.monotonic() + 10,
    )


def test_source_egg_info_inventories_actual_tree_not_source_archive_paths(tmp_path, monkeypatch):
    actual = package(tmp_path / "project/src/inferrsi")
    distribution = installed_distribution(
        tmp_path / "project/src/inferrsi.egg-info",
        source_list="src/inferrsi/__init__.py\nsrc/inferrsi/data/private.json\n",
    )
    # This is the real PathDistribution mismatch seen on Python 3.10/3.11 CI.
    assert not distribution.locate_file("src/inferrsi/__init__.py").exists()
    files = installed_files(distribution, monkeypatch)
    assert actual / "__init__.py" in files and actual / "data/private.json" in files


def test_installed_wheel_copy_includes_all_actual_package_nodes(tmp_path, monkeypatch):
    actual = package(tmp_path / "site/inferrsi")
    distribution = installed_distribution(
        tmp_path / "site/inferrsi-0.1.0.dist-info", record="inferrsi/__init__.py,,\n"
    )
    files = installed_files(distribution, monkeypatch)
    assert actual / "__init__.py" in files and actual / "data/private.json" in files


@pytest.mark.parametrize("variant", ["missing", "symlink", "absolute", "traversal"])
def test_raw_record_does_not_filter_missing_or_unsafe_installed_nodes(
    tmp_path, monkeypatch, variant
):
    actual = package(tmp_path / "site/inferrsi")
    entry = "inferrsi/missing.py"
    if variant == "symlink":
        (actual / "alias.py").symlink_to(actual / "__init__.py")
        entry = "inferrsi/alias.py"
    elif variant == "absolute":
        entry = str(actual / "missing.py")
    elif variant == "traversal":
        entry = "inferrsi/../missing.py"
    distribution = installed_distribution(
        tmp_path / "site/inferrsi-0.1.0.dist-info", record=f"inferrsi/__init__.py,,\n{entry},,\n"
    )

    class FilteredFilesDistribution:
        # Newer importlib.metadata filters missing paths from .files; never use
        # that lossy view to decide completeness of the authoritative RECORD.
        files = []
        metadata = distribution.metadata
        read_text = distribution.read_text
        locate_file = distribution.locate_file

    with pytest.raises(ValueError, match="package (inventory incomplete|RECORD)"):
        installed_files(FilteredFilesDistribution(), monkeypatch)


@pytest.mark.parametrize("layout", ["src", "flat"])
def test_editable_record_maps_independent_source_copy(tmp_path, monkeypatch, layout):
    source = tmp_path / "project"
    actual = package(source / ("src/inferrsi" if layout == "src" else "inferrsi"))
    distribution = installed_distribution(
        tmp_path / "site/inferrsi-0.1.0.dist-info",
        record="__editable__.inferrsi.pth,,\n",
        direct_url=json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}}),
    )
    files = installed_files(distribution, monkeypatch)
    assert actual / "__init__.py" in files and actual / "data/private.json" in files


@pytest.mark.parametrize("variant", ["missing", "ambiguous", "symlink", "remote"])
def test_unknown_editable_layout_never_silently_drops_installed_copy(
    tmp_path, monkeypatch, variant
):
    source = tmp_path / "project"
    source.mkdir()
    if variant in {"ambiguous", "remote"}:
        package(source / "src/inferrsi")
    if variant == "ambiguous":
        package(source / "inferrsi")
    if variant == "symlink":
        actual = package(tmp_path / "other/inferrsi")
        (source / "inferrsi").symlink_to(actual, target_is_directory=True)
    url = "https://example.invalid/source" if variant == "remote" else source.as_uri()
    distribution = installed_distribution(
        tmp_path / "site/inferrsi-0.1.0.dist-info", record="__editable__.inferrsi.pth,,\n",
        direct_url=json.dumps({"url": url, "dir_info": {"editable": True}}),
    )
    with pytest.raises(ValueError):
        installed_files(distribution, monkeypatch)


def test_missing_installed_record_is_not_treated_as_source_egg_info(tmp_path, monkeypatch):
    package(tmp_path / "site/inferrsi")
    distribution = installed_distribution(tmp_path / "site/inferrsi-0.1.0.dist-info")
    with pytest.raises(ValueError, match="inventory metadata"):
        installed_files(distribution, monkeypatch)
