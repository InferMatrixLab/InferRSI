"""Native WorkSwarm packaging, with common runtime journeys in test_codex_plugin."""

import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from tools.build_workswarm_plugin import PROJECT, build_plugin
from tools.check_release import check_plugin
from tools.plugin_bundle import _io_path


@pytest.mark.parametrize("invalid", [
    "package_type", "skills", "tool_file", "tool_class", "missing_tool",
    "tool_syntax", "tool_class_missing",
])
def test_release_validator_requires_native_entrypoints(tmp_path, invalid):
    metadata = json.loads((PROJECT / "plugins/workswarm/inferrsi/manifest.json").read_text(
        encoding="utf-8"))
    if invalid in {"package_type", "skills"}:
        metadata[invalid] = "invalid"
    elif invalid in {"tool_file", "tool_class"}:
        metadata["tools"][0][invalid.removeprefix("tool_")] = "invalid"
    path = tmp_path / "invalid-native.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("inferrsi/manifest.json", json.dumps(metadata))
        archive.writestr("inferrsi/runtime/manifest.json", "{}")
        if invalid != "missing_tool":
            source = "invalid =" if invalid == "tool_syntax" else "class AnotherTool: pass"
            archive.writestr("inferrsi/tools/runtime_info_tool.py", source)
    if invalid == "missing_tool":
        with pytest.raises(KeyError, match="runtime_info_tool"):
            check_plugin(path, "v0.2.0", "workswarm")
    elif invalid in {"tool_syntax", "tool_class_missing"}:
        with pytest.raises(ValueError, match="WorkSwarm locator"):
            check_plugin(path, "v0.2.0", "workswarm")
    else:
        with pytest.raises(ValueError, match="native skill and locator"):
            check_plugin(path, "v0.2.0", "workswarm")


def test_native_manifest_and_shared_launcher(tmp_path):
    result = build_plugin(tmp_path / "native package")
    plugin = _io_path(Path(result["plugin"]))
    metadata = json.loads((plugin / "manifest.json").read_text(encoding="utf-8"))
    assert metadata["id"] == plugin.name == "inferrsi"
    assert metadata["package_type"] == "plugin"
    assert metadata["source"] == "local"
    assert metadata["skills"] == [{"dir": "./skills/inferrsi", "mode": "all"}]
    assert metadata["default_init_input"] == metadata["quick_inputs"][0]
    assert len(metadata["tags"]) == len(metadata["quick_inputs"]) == 3
    assert "rails" not in metadata
    assert len(metadata["tools"]) == 1
    assert metadata["tools"][0]["class"] == "InferRSIRuntimeInfoTool"
    assert (plugin / metadata["tools"][0]["file"]).read_bytes() == (
        PROJECT / "plugins/workswarm/inferrsi/tools/runtime_info_tool.py"
    ).read_bytes()
    assert (plugin / "skills/inferrsi/scripts/inferrsi.py").read_bytes() == (
        PROJECT / "plugins/workswarm/inferrsi/skills/inferrsi/scripts/inferrsi.py"
    ).read_bytes()
    assert (plugin / "runtime/launcher.py").read_bytes() == (
        PROJECT / "plugins/inferrsi/skills/inferrsi/scripts/inferrsi.py"
    ).read_bytes()
    assert (plugin / "README.md").read_bytes() == (
        PROJECT / "docs/workswarm-plugin.md"
    ).read_bytes()
    with zipfile.ZipFile(result["archive"]) as archive:
        assert {Path(name).parts[0] for name in archive.namelist()} == {"inferrsi"}
        assert "inferrsi/manifest.json" in archive.namelist()
        assert "inferrsi/plugin.json" not in archive.namelist()
        assert not any("marketplace" in name for name in archive.namelist())
        # Reproduce the host's long staging prefix without requiring global long-path policy.
        assert max(map(len, archive.namelist())) + 170 < 260
        assert not any(name.startswith("inferrsi/runtime/inferrsi/")
                       for name in archive.namelist())
        for name in archive.namelist():
            assert archive.read(name) == (plugin / name.removeprefix("inferrsi/")).read_bytes()


def test_identical_inputs_produce_identical_archives(tmp_path):
    first = build_plugin(tmp_path / "first")
    second = build_plugin(tmp_path / "second")
    assert Path(first["archive"]).read_bytes() == Path(second["archive"]).read_bytes()


@pytest.mark.parametrize("existing", ["directory", "archive"])
def test_builder_preserves_existing_output(tmp_path, existing):
    output = tmp_path / "existing"
    sentinel = output / "user.txt" if existing == "directory" else output.with_suffix(".zip")
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"keep")
    with pytest.raises(ValueError, match="already exists"):
        build_plugin(output)
    assert sentinel.read_bytes() == b"keep"


@pytest.mark.parametrize("directory", ["src", "plugins", "docs", "tests", "tools"])
def test_builder_rejects_source_directory_output(tmp_path, directory):
    with pytest.raises(ValueError, match="outside the source"):
        build_plugin(tmp_path / directory / "generated", project=tmp_path)


def test_version_stamp_keeps_canonical_inputs_unchanged(tmp_path):
    project = tmp_path / "source"
    for name in ("plugins/workswarm/inferrsi/manifest.json", "docs/workswarm-plugin.md",
                 "plugins/workswarm/inferrsi/skills/inferrsi/scripts/inferrsi.py",
                 "plugins/workswarm/inferrsi/tools/runtime_info_tool.py",
                 "plugins/inferrsi/skills/inferrsi/scripts/inferrsi.py", "LICENSE"):
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / name, target)
    source = project / "src/inferrsi/__init__.py"
    source.parent.mkdir(parents=True)
    source.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    template = project / "plugins/workswarm/inferrsi/manifest.json"
    original = template.read_bytes()
    result = build_plugin(tmp_path / "versioned", project=project, release_version="1.2.3")
    with zipfile.ZipFile(result["archive"]) as archive:
        metadata = json.loads(archive.read("inferrsi/manifest.json"))
        manifest = json.loads(archive.read("inferrsi/runtime/manifest.json"))
        assert metadata["version"] == manifest["plugin_version"] == "1.2.3"
        assert manifest["runtime_version"] == "1.2.3"
        with zipfile.ZipFile(io.BytesIO(archive.read("inferrsi/runtime/payload.zip"))) as payload:
            assert payload.read("inferrsi/__init__.py") == source.read_bytes()
    assert template.read_bytes() == original
    output = tmp_path / "wrong-version"
    with pytest.raises(ValueError, match="match the built runtime"):
        build_plugin(output, project=project, release_version="1.2.4")
    assert not output.exists() and not output.with_suffix(".zip").exists()
