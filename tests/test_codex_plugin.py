"""Exercise a distributed plugin outside a checkout, without site packages."""

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tools.build_codex_plugin import PROJECT, _io_path, _version, build_plugin
from tools.check_release import check_plugin

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: pytest supplies tomli.
    import tomli as tomllib


@pytest.fixture(scope="module")
def distribution(tmp_path_factory):
    root = tmp_path_factory.mktemp("codex-plugin") / "marketplace"
    result = build_plugin(root)
    extracted = _io_path(root.parent / "extracted")
    with zipfile.ZipFile(result["archive"]) as archive:
        archive.extractall(extracted)
    return extracted / root.name


def invoke(distribution, cwd, *args):
    launcher = distribution / "plugins/inferrsi/skills/inferrsi/scripts/inferrsi.py"
    return subprocess.run(
        [sys.executable, "-I", "-S", "-X", "utf8", str(launcher), *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=45,
    )


def test_bundle_preserves_canonical_bytes_and_license(distribution):
    plugin = distribution / "plugins/inferrsi"
    runtime = plugin / "runtime"
    manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        actual = (runtime / name).read_bytes()
        assert hashlib.sha256(actual).hexdigest() == digest
        assert actual == _io_path(PROJECT / "src" / name).read_bytes()
    assert (plugin / "LICENSE").read_bytes() == (PROJECT / "LICENSE").read_bytes()
    assert (distribution / "LICENSE").read_bytes() == (PROJECT / "LICENSE").read_bytes()
    assert not list(plugin.rglob("*.pyc"))


def test_bundle_contains_all_declared_package_data(distribution):
    # The canonical packaging contract is the oracle, independent of both the
    # builder's file filter and the manifest of files it happened to emit.
    metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = metadata["tool"]["setuptools"]["package-data"]["inferrsi"]
    source = _io_path(PROJECT / "src/inferrsi")
    expected = {
        path.relative_to(source).as_posix()
        for pattern in patterns for path in source.glob(pattern) if path.is_file()
    }
    assert "data/skill_library/repositories/splash/THIRD_PARTY_NOTICES" in expected
    runtime = distribution / "plugins/inferrsi/runtime"
    installed = {
        path.relative_to(runtime / "inferrsi").as_posix()
        for path in (runtime / "inferrsi/data").rglob("*") if path.is_file()
    }
    assert expected == installed
    manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
    assert {f"inferrsi/{name}" for name in expected} <= manifest["files"].keys()


def test_isolated_runtime_and_exact_knowledge_reads(distribution, tmp_path):
    # Neither editable installs, PYTHONPATH nor the target's Python module may
    # supply the core. This also exercises resource reads from an extracted ZIP.
    (tmp_path / "inferrsi.py").write_text("raise RuntimeError('wrong import')", encoding="utf-8")
    info = invoke(distribution, tmp_path, "--plugin-info")
    assert info.returncode == 0, info.stderr
    assert json.loads(info.stdout)["runtime"] == "bundled"
    assert not json.loads(info.stdout)["optional_skills_dependency"]
    collected = invoke(distribution, tmp_path, "collect", "Qwen", "--limit", "1", "--json")
    assert collected.returncode == 0, collected.stderr
    item = json.loads(collected.stdout)["items"][0]
    read = invoke(
        distribution, tmp_path, "read", item["ref"],
        "--revision", item["revision"], "--material",
    )
    assert read.returncode == 0, read.stderr
    assert json.loads(read.stdout)["revision"] == item["revision"]
    stale = invoke(
        distribution, tmp_path, "read", item["ref"], "--revision", "sha256:" + "0" * 64,
    )
    assert stale.returncode == 2
    assert "unavailable" in stale.stderr


def test_entry_workflow_selects_packaged_skill_projections(distribution, tmp_path):
    result = invoke(
        distribution, tmp_path, "collect", "--relevance",
        "vLLM-Omni inference engine memory bottleneck", "--limit", "3", "--json",
    )
    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["items"]
    assert all(item["authority"] == "package" for item in envelope["items"])
    assert all(item["kind"] == "knowledge" for item in envelope["items"])


def test_missing_runtime_has_repair_guidance(tmp_path):
    source = PROJECT / "plugins/inferrsi"
    incomplete = tmp_path / "incomplete"
    shutil.copytree(source, incomplete / "plugins/inferrsi")
    result = invoke(incomplete, tmp_path, "--plugin-info")
    assert result.returncode == 2
    assert "built distribution" in result.stderr


@pytest.mark.parametrize("args", [
    ("skills", "list", "--json"),
    ("collect", "--skill-root", "."),
    ("read", "example", "--skill-root=."),
])
def test_optional_dependency_guidance_does_not_require_a_checkout(distribution, tmp_path, args):
    result = invoke(distribution, tmp_path, *args)
    assert result.returncode == 2
    assert "PyYAML" in result.stderr
    assert "<inferrsi-checkout>" not in result.stderr
    help_result = invoke(distribution, tmp_path, "skills", "list", "--help")
    assert help_result.returncode == 0


def test_builder_refuses_to_replace_existing_files(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "user.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        build_plugin(output)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_named_marketplace_installs_the_same_bundled_runtime(tmp_path):
    output = tmp_path / "remote-preview"
    result = build_plugin(output, marketplace_name="inferrsi-preview")
    catalog = json.loads((output / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    assert result["marketplace_name"] == catalog["name"] == "inferrsi-preview"
    plugin = output / catalog["plugins"][0]["source"]["path"]
    info = invoke(output, tmp_path, "--plugin-info")
    assert info.returncode == 0, info.stderr
    manifest = json.loads((plugin / "runtime/manifest.json").read_text(encoding="utf-8"))
    assert json.loads(info.stdout)["content_sha256"] == manifest["content_sha256"]


@pytest.fixture(scope="module")
def release_distribution(tmp_path_factory):
    root = tmp_path_factory.mktemp("codex-release")
    project = root / "source"
    for directory in ("src/inferrsi", "plugins/inferrsi"):
        shutil.copytree(_io_path(PROJECT / directory), _io_path(project / directory),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (project / "docs").mkdir()
    shutil.copyfile(PROJECT / "docs/codex-plugin.md", project / "docs/codex-plugin.md")
    shutil.copyfile(PROJECT / "LICENSE", project / "LICENSE")
    (project / "src/inferrsi/_version.py").write_text(
        '__version__ = version = "0.2.0"\n', encoding="utf-8",
    )
    template = (project / "plugins/inferrsi/plugin.json").read_bytes()
    result = build_plugin(root / "inferrsi-codex-plugin-v0.2.0", project=project,
                          release_version="0.2.0")
    return project, template, result


def test_release_archive_is_installable_and_all_versions_match(release_distribution):
    project, template, result = release_distribution
    check_plugin(Path(result["archive"]), "v0.2.0")
    assert (project / "plugins/inferrsi/plugin.json").read_bytes() == template
    with zipfile.ZipFile(result["archive"]) as archive:
        name = "inferrsi-codex-plugin-v0.2.0/plugins/inferrsi/plugin.json"
        assert json.loads(archive.read(name))["version"] == "0.2.0"
    with pytest.raises(ValueError, match="agree exactly"):
        check_plugin(Path(result["archive"]), "v0.2.1")


def test_release_archive_rejects_changed_runtime_bytes(release_distribution, tmp_path):
    original = release_distribution[2]["archive"]
    changed = tmp_path / "changed.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(changed, "w") as destination:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename.endswith("runtime/inferrsi/__init__.py"):
                data += b"\n"
            destination.writestr(member, data)
    with pytest.raises(ValueError, match="checksum mismatch"):
        check_plugin(changed, "v0.2.0")


@pytest.mark.parametrize("replacement", [
    "plugins//inferrsi/", "plugins/./inferrsi/", "plugins/Inferrsi/", "plugins./inferrsi/",
])
def test_release_archive_rejects_extraction_aliases(tmp_path, replacement):
    changed = tmp_path / "aliased.zip"
    name = "inferrsi-codex-plugin-v0.2.0/plugins/inferrsi/runtime/inferrsi/__init__.py"
    alias = name.replace("plugins/inferrsi/", replacement)
    with zipfile.ZipFile(changed, "w") as archive:
        archive.writestr(name, b"pass")
        archive.writestr(alias, b"raise RuntimeError('must not execute unverified alias')")
    with pytest.raises(ValueError, match="Unsafe"):
        check_plugin(changed, "v0.2.0")


@pytest.mark.parametrize("name", [".", "../file", "/absolute", "root/CON.txt", "root/file. "])
def test_release_archive_rejects_unsafe_names_before_metadata(tmp_path, name):
    changed = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(changed, "w") as archive:
        archive.writestr(name, b"")
    with pytest.raises(ValueError, match="Unsafe"):
        check_plugin(changed, "v0.2.0")


def test_release_archive_rejects_new_modules_under_case_aliased_directories(tmp_path):
    changed = tmp_path / "directory-alias.zip"
    with zipfile.ZipFile(changed, "w") as archive:
        archive.writestr("root/plugins/inferrsi/runtime/inferrsi/__init__.py", b"pass")
        archive.writestr("root/Plugins/inferrsi/runtime/hashlib.py", b"must not execute")
    with pytest.raises(ValueError, match="Unsafe"):
        check_plugin(changed, "v0.2.0")


def test_release_archive_rejects_unverified_runtime_modules(release_distribution, tmp_path):
    original = release_distribution[2]["archive"]
    changed = tmp_path / "shadow.zip"
    shutil.copyfile(original, changed)
    with zipfile.ZipFile(changed, "a") as archive:
        archive.writestr("inferrsi-codex-plugin-v0.2.0/plugins/inferrsi/runtime/hashlib.py", b"")
    with pytest.raises(ValueError, match="outside the bundled runtime"):
        check_plugin(changed, "v0.2.0")


def test_release_builder_rejects_mismatched_version_before_writing(release_distribution, tmp_path):
    project = release_distribution[0]
    output = tmp_path / "wrong-version"
    with pytest.raises(ValueError, match="match the built runtime"):
        build_plugin(output, project=project, release_version="0.2.1")
    assert not output.exists() and not output.with_suffix(".zip").exists()


def test_unbuilt_version_fallback_does_not_import_an_installed_runtime(tmp_path):
    source = tmp_path / "__init__.py"
    source.write_text('try:\n    from ._version import __version__\n'
                      'except ImportError:\n    __version__ = "0+unknown"\n', encoding="utf-8")
    assert _version(source) == "0+unknown"


@pytest.mark.parametrize(("quality", "exit_code", "verdict"), [
    ("pass", 0, "PASS"), ("fail", 1, "FAIL"), ("missing", 2, "INCONCLUSIVE"),
])
def test_comparison_preview_execution_status_and_report(
    distribution, tmp_path, quality, exit_code, verdict,
):
    repo = tmp_path / "target with spaces"
    repo.mkdir()
    shutil.copyfile(PROJECT / "tests/fixtures/synthetic_benchmark.py", repo / "bench.py")
    (repo / "quality.py").write_text(
        "import sys\nsys.exit(" + ("1" if quality == "fail" else "0") + ")\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=InferRSI test",
        "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "-q", "-s", "-m", "synthetic fixture",
    ], check=True, capture_output=True)
    python = Path(sys.executable).as_posix()
    output = tmp_path / "evidence"
    args = [
        "--repo", str(repo), "--backend", "cpu", "--scenario", "plugin.synthetic",
        "--baseline-command", f'"{python}" bench.py --value 100 --output {{result}}',
        "--candidate-command", f'"{python}" bench.py --value 80 --output {{result}}',
        "--repetitions", "1", "--max-minutes", "1", "--output-dir", str(output),
    ]
    if quality != "missing":
        args += ["--validation-command", f'"{python}" quality.py']
    preview = invoke(distribution, repo, "plan", *args)
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["execution"] == "not started"
    assert not output.exists()
    run = invoke(distribution, repo, "run", *args)
    assert run.returncode == exit_code, run.stderr
    result = json.loads(run.stdout)
    assert result["status"]["verdict"] == verdict
    recorded = ["--run-id", result["run_id"], "--output-dir", str(output)]
    status = invoke(distribution, repo, "status", *recorded)
    assert json.loads(status.stdout)["verdict"] == verdict
    report_path = Path(result["report"])
    report_path.unlink()
    report = invoke(distribution, repo, "report", *recorded)
    assert report.returncode == 0, report.stderr
    assert Path(json.loads(report.stdout)["report"]).is_file()
