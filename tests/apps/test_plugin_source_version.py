"""Source-built plugins report an explicit non-release version.

Release builds stamp ``--release-version`` and are covered in test_codex_plugin
and test_workswarm_plugin. These tests pin what a build without it reports.
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools import build_dsh_plugin
from tools.build_codex_plugin import build_plugin as build_codex_plugin
from tools.build_workswarm_plugin import build_plugin as build_workswarm_plugin
from tools.plugin_bundle import PROJECT, _io_path

SOURCE_VERSION = "0.0.0+source"
GENERATED_VERSION = "0.2.0"
TEMPLATES = {
    "codex": "plugins/inferrsi/plugin.json",
    "workswarm": "plugins/workswarm/inferrsi/manifest.json",
    "dsh": "plugins/inferrsi-dsh/package.json",
}
METADATA_FILES = {"codex": "plugin.json", "workswarm": "manifest.json", "dsh": "package.json"}
RELEASE_BUILDERS = {"codex": build_codex_plugin, "workswarm": build_workswarm_plugin}


def make_checkout(root, generated_version):
    """Copy only what the three builders read; optionally add the SCM-generated version."""
    project = root / "source"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for directory in ("src/inferrsi", "plugins"):
        shutil.copytree(_io_path(PROJECT / directory), _io_path(project / directory),
                        ignore=ignore)
    for relative in (
        "docs/dashboard.md",
        "docs/guides/plugins/codex-plugin.md",
        "docs/guides/plugins/workswarm-plugin.md",
        "docs/guides/plugins/dsh-plugin.md",
    ):
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / relative, target)
    shutil.copyfile(PROJECT / "LICENSE", project / "LICENSE")
    generated = _io_path(project / "src/inferrsi/_version.py")
    # A developer's editable install may have left a generated file in the source tree.
    generated.unlink(missing_ok=True)
    if generated_version is not None:
        generated.write_text(f'__version__ = version = "{generated_version}"\n',
                             encoding="utf-8")
    return project, generated_version or "0+unknown"


@pytest.fixture(scope="module")
def unbuilt(tmp_path_factory):
    return make_checkout(tmp_path_factory.mktemp("unbuilt"), None)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return make_checkout(tmp_path_factory.mktemp("built"), GENERATED_VERSION)


@pytest.fixture(params=["unbuilt", "built"])
def checkout(request):
    return request.getfixturevalue(request.param)


def build_package(host, project, tmp_path, monkeypatch, release_version=None):
    """Build one host from ``project`` and return its metadata, manifest and --plugin-info."""
    if host == "dsh":
        monkeypatch.setattr(build_dsh_plugin, "PROJECT", project)
        result = build_dsh_plugin.build_bundle(tmp_path / "inferrsi-dsh.tgz")
        extracted = _io_path(tmp_path / "extracted")
        with tarfile.open(result["archive"]) as bundle:
            bundle.extractall(extracted)
        package = extracted / "package"
        launcher = package / "assets/inferrsi/scripts/inferrsi.py"
    else:
        result = RELEASE_BUILDERS[host](tmp_path / "plugin", project=project,
                                        release_version=release_version)
        package = _io_path(Path(result["plugin"]))
        launcher = package / "skills/inferrsi/scripts/inferrsi.py"
    run = subprocess.run(
        [sys.executable, "-I", "-S", "-X", "utf8", str(launcher), "--plugin-info"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=45,
        env=dict(os.environ, LOCALAPPDATA=str(tmp_path / "runtime-cache")),
    )
    assert run.returncode == 0, run.stderr
    return {
        "metadata": json.loads((package / METADATA_FILES[host]).read_text(encoding="utf-8")),
        "manifest": json.loads((package / "runtime/manifest.json").read_text(encoding="utf-8")),
        "info": json.loads(run.stdout),
    }


@pytest.mark.parametrize("host", TEMPLATES)
def test_templates_carry_the_source_marker(host):
    template = json.loads((PROJECT / TEMPLATES[host]).read_text(encoding="utf-8"))
    assert template["version"] == SOURCE_VERSION


@pytest.mark.parametrize("host", TEMPLATES)
def test_source_build_reports_the_marker_beside_the_bundled_runtime(
    host, checkout, tmp_path, monkeypatch,
):
    project, runtime_version = checkout
    package = build_package(host, project, tmp_path, monkeypatch)
    # The plugin is not a release; the runtime keeps its own, possibly different, version.
    assert package["metadata"]["version"] == SOURCE_VERSION
    assert package["manifest"]["plugin_version"] == SOURCE_VERSION
    assert package["manifest"]["runtime_version"] == runtime_version
    assert package["info"]["plugin_version"] == SOURCE_VERSION
    assert package["info"]["runtime_version"] == runtime_version


@pytest.mark.parametrize("host", RELEASE_BUILDERS)
def test_release_build_keeps_stamping_the_matching_runtime_version(
    host, built, tmp_path, monkeypatch,
):
    project, runtime_version = built
    package = build_package(host, project, tmp_path, monkeypatch,
                            release_version=runtime_version)
    assert package["metadata"]["version"] == runtime_version
    assert package["manifest"]["plugin_version"] == runtime_version
    assert package["manifest"]["runtime_version"] == runtime_version
    assert package["info"]["plugin_version"] == runtime_version
    assert package["info"]["runtime_version"] == runtime_version


@pytest.mark.parametrize("host", RELEASE_BUILDERS)
def test_release_build_rejects_a_version_other_than_the_runtime(host, checkout, tmp_path):
    project, _ = checkout
    output = tmp_path / "mismatch"
    with pytest.raises(ValueError, match="match the built runtime"):
        RELEASE_BUILDERS[host](output, project=project, release_version="9.9.9")
    assert not output.exists() and not output.with_suffix(".zip").exists()
