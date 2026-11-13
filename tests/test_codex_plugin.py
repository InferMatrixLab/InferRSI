"""Exercise a distributed plugin outside a checkout, without site packages."""

import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from tools.build_codex_plugin import build_plugin
from tools.build_workswarm_plugin import build_plugin as build_workswarm_plugin
from tools.check_release import check_plugin
from tools.plugin_bundle import PROJECT, _io_path, _version

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: pytest supplies tomli.
    import tomli as tomllib


@pytest.fixture(scope="module", params=["codex", "workswarm"])
def distribution(tmp_path_factory, request):
    root = tmp_path_factory.mktemp(request.param + "-plugin") / "distribution"
    builder = build_plugin if request.param == "codex" else build_workswarm_plugin
    result = builder(root)
    extracted = _io_path(root.parent / "extracted")
    with zipfile.ZipFile(result["archive"]) as archive:
        archive.extractall(extracted)
    return extracted / "inferrsi"


def invoke(distribution, cwd, *args):
    launcher = distribution / "skills/inferrsi/scripts/inferrsi.py"
    return subprocess.run(
        [sys.executable, "-I", "-S", "-X", "utf8", str(launcher), *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=45,
        env=dict(os.environ, LOCALAPPDATA=str(distribution.parent / "runtime-cache")),
    )


def runtime_bytes(plugin):
    runtime = plugin / "runtime"
    if (runtime / "payload.zip").is_file():
        with zipfile.ZipFile(runtime / "payload.zip") as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    return {path.relative_to(runtime).as_posix(): path.read_bytes()
            for path in (runtime / "inferrsi").rglob("*") if path.is_file()}


def test_bundle_preserves_canonical_bytes_and_license(distribution):
    plugin = distribution
    runtime = plugin / "runtime"
    manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
    bundled = runtime_bytes(plugin)
    for name, digest in manifest["files"].items():
        actual = bundled[name]
        assert hashlib.sha256(actual).hexdigest() == digest
        assert actual == _io_path(PROJECT / "src" / name).read_bytes()
    assert (plugin / "LICENSE").read_bytes() == (PROJECT / "LICENSE").read_bytes()
    assert not list(plugin.rglob("*.pyc"))


def test_bundle_contains_all_declared_package_data(distribution):
    # The canonical packaging contract is the oracle, independent of both the
    # builder's file filter and the manifest of files it happened to emit.
    metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = metadata["tool"]["setuptools"]["package-data"]
    source = _io_path(PROJECT / "src/inferrsi")
    expected = {
        path.relative_to(source).as_posix()
        for package, patterns in packages.items()
        for pattern in patterns
        for path in _io_path(PROJECT / "src" / Path(*package.split("."))).glob(pattern)
        if path.is_file()
    }
    assert "data/skill_library/repositories/splash/THIRD_PARTY_NOTICES" in expected
    installed = {
        name.removeprefix("inferrsi/")
        for name in runtime_bytes(distribution)
        if name.startswith(("inferrsi/data/", "inferrsi/benchmark/tasks/")) or (
            name.startswith("inferrsi/observability/") and name.endswith(".html")
        )
    }
    assert expected == installed
    manifest = json.loads((distribution / "runtime/manifest.json").read_text(encoding="utf-8"))
    assert {f"inferrsi/{name}" for name in expected} <= manifest["files"].keys()


def test_isolated_runtime_can_export_dashboard(distribution, tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.lock.json").write_text("{}", encoding="utf-8")

    result = invoke(distribution, tmp_path, "dashboard", "--input", str(run))

    assert result.returncode == 0, result.stderr
    assert "InferRSI · Optimization dashboard" in (run / "dashboard.html").read_text(
        encoding="utf-8"
    )


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


@pytest.mark.parametrize(("action", "resource"), [
    ("reference", "../../../hardware/host/host-memory-management/SKILL.md"),
    ("resource", "metadata.json"),
])
def test_returned_skill_paths_survive_process_exit_and_later_invocations(
    distribution, tmp_path, action, resource,
):
    pytest.importorskip("yaml")
    launcher = distribution / "skills/inferrsi/scripts/inferrsi.py"
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(launcher), "skills", action,
         "pytorch", resource], cwd=tmp_path, capture_output=True, text=True,
        encoding="utf-8", timeout=45,
        env=dict(os.environ, LOCALAPPDATA=str(distribution.parent / "runtime-cache")),
    )
    assert result.returncode == 0, result.stderr
    path = Path(json.loads(result.stdout)["path"])
    assert path.is_file()
    original = path.read_bytes()
    assert invoke(distribution, tmp_path, "--plugin-info").returncode == 0
    assert path.read_bytes() == original


def test_missing_runtime_has_repair_guidance(tmp_path):
    source = PROJECT / "plugins/inferrsi"
    incomplete = tmp_path / "incomplete"
    shutil.copytree(source, incomplete)
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


def test_archive_contains_only_one_standalone_plugin(tmp_path):
    output = tmp_path / "offline-package"
    result = build_plugin(output)
    assert result["plugin"] == str(output)
    with zipfile.ZipFile(result["archive"]) as archive:
        names = archive.namelist()
        assert {Path(name).parts[0] for name in names} == {"inferrsi"}
        assert "inferrsi/plugin.json" in names
        readme = archive.read("inferrsi/README.md")
        assert readme == (PROJECT / "docs/codex-plugin.md").read_bytes()
        for target in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", readme.decode("utf-8")):
            link = urlsplit(target)
            if not link.scheme and not link.netloc and link.path:
                path = posixpath.normpath(posixpath.join("inferrsi", unquote(link.path)))
                assert path in names, f"Broken link in plugin README: {target}"
        assert not any("marketplace" in name or ".agents" in name for name in names)
        metadata = json.loads(archive.read("inferrsi/plugin.json"))
        assert metadata["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        assert len(metadata["extensions"]["com.openai"]["interface"]["shortDescription"]) <= 30
    info = invoke(output, tmp_path, "--plugin-info")
    assert info.returncode == 0, info.stderr
    manifest = json.loads((output / "runtime/manifest.json").read_text(encoding="utf-8"))
    assert json.loads(info.stdout)["content_sha256"] == manifest["content_sha256"]


@pytest.fixture(scope="module", params=["codex", "workswarm"])
def release_distribution(tmp_path_factory, request):
    host = request.param
    root = tmp_path_factory.mktemp(host + "-release")
    project = root / "source"
    directories = ["src/inferrsi", "plugins/inferrsi"]
    if host == "workswarm":
        directories.append("plugins/workswarm/inferrsi")
    for directory in directories:
        shutil.copytree(_io_path(PROJECT / directory), _io_path(project / directory),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (project / "docs").mkdir()
    readme = f"docs/{host}-plugin.md"
    shutil.copyfile(PROJECT / readme, project / readme)
    shutil.copyfile(PROJECT / "LICENSE", project / "LICENSE")
    (project / "src/inferrsi/_version.py").write_text(
        '__version__ = version = "0.2.0"\n', encoding="utf-8",
    )
    metadata = ("plugins/inferrsi/plugin.json" if host == "codex"
                else "plugins/workswarm/inferrsi/manifest.json")
    template = (project / metadata).read_bytes()
    builder = build_plugin if host == "codex" else build_workswarm_plugin
    result = builder(root / f"inferrsi-{host}-plugin-v0.2.0", project=project,
                     release_version="0.2.0")
    result.update(host=host, metadata=metadata)
    return project, template, result


def test_release_archive_is_installable_and_all_versions_match(release_distribution):
    project, template, result = release_distribution
    host = result["host"]
    check_plugin(Path(result["archive"]), "v0.2.0", host)
    assert (project / result["metadata"]).read_bytes() == template
    readme = f"docs/{host}-plugin.md"
    source_readme = (project / readme).read_bytes()
    assert source_readme == (PROJECT / readme).read_bytes()
    expected_readme = source_readme
    if host == "codex":
        video_base = b"https://raw.githubusercontent.com/InferMatrixLab/InferRSI/"
        video_path = b"/docs/assets/inferrsi-codex-install-en.mp4"
        main_video = video_base + b"main" + video_path
        assert main_video in source_readme
        expected_readme = source_readme.replace(
            main_video, video_base + b"refs/tags/v0.2.0" + video_path,
        )
    with zipfile.ZipFile(result["archive"]) as archive:
        name = "inferrsi/" + Path(result["metadata"]).name
        assert json.loads(archive.read(name))["version"] == "0.2.0"
        assert archive.read("inferrsi/README.md") == expected_readme
    with pytest.raises(ValueError, match="agree exactly"):
        check_plugin(Path(result["archive"]), "v0.2.1", host)


def test_release_archive_rejects_changed_runtime_bytes(release_distribution, tmp_path):
    original = release_distribution[2]["archive"]
    changed = tmp_path / "changed.zip"
    with zipfile.ZipFile(original) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    payload_name = "inferrsi/runtime/payload.zip"
    if payload_name in contents:
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(contents[payload_name])) as payload:
            with zipfile.ZipFile(buffer, "w") as destination:
                for name in payload.namelist():
                    data = payload.read(name) + (b"\n" if name == "inferrsi/__init__.py" else b"")
                    destination.writestr(name, data)
        contents[payload_name] = buffer.getvalue()
        manifest_name = "inferrsi/runtime/manifest.json"
        manifest = json.loads(contents[manifest_name])
        manifest["payload_sha256"] = hashlib.sha256(contents[payload_name]).hexdigest()
        contents[manifest_name] = json.dumps(manifest).encode()
    else:
        contents["inferrsi/runtime/inferrsi/__init__.py"] += b"\n"
    with zipfile.ZipFile(changed, "w") as destination:
        for name, data in contents.items():
            destination.writestr(name, data)
    with pytest.raises(ValueError, match="checksum mismatch"):
        check_plugin(changed, "v0.2.0", release_distribution[2]["host"])


@pytest.mark.parametrize("replacement", [
    "inferrsi//", "inferrsi/./", "Inferrsi/", "inferrsi./",
])
def test_release_archive_rejects_extraction_aliases(tmp_path, replacement):
    changed = tmp_path / "aliased.zip"
    name = "inferrsi/runtime/inferrsi/__init__.py"
    alias = name.replace("inferrsi/", replacement, 1)
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
        archive.writestr("inferrsi/runtime/inferrsi/__init__.py", b"pass")
        archive.writestr("inferrsi/Runtime/hashlib.py", b"must not execute")
    with pytest.raises(ValueError, match="Unsafe"):
        check_plugin(changed, "v0.2.0")


def test_release_archive_rejects_unverified_runtime_modules(release_distribution, tmp_path):
    original = release_distribution[2]["archive"]
    changed = tmp_path / "shadow.zip"
    shutil.copyfile(original, changed)
    with zipfile.ZipFile(changed, "a") as archive:
        archive.writestr("inferrsi/runtime/hashlib.py", b"")
    with pytest.raises(ValueError, match="outside the bundled runtime"):
        check_plugin(changed, "v0.2.0", release_distribution[2]["host"])


@pytest.mark.parametrize("extra", [
    "inferrsi/.agents/plugins/marketplace.json", "marketplace/plugins/inferrsi/plugin.json",
])
def test_release_archive_rejects_marketplace_wrappers(release_distribution, tmp_path, extra):
    changed = tmp_path / "marketplace.zip"
    shutil.copyfile(release_distribution[2]["archive"], changed)
    with zipfile.ZipFile(changed, "a") as archive:
        archive.writestr(extra, "{}")
    with pytest.raises(ValueError, match="standalone|marketplace"):
        check_plugin(changed, "v0.2.0", release_distribution[2]["host"])


def test_release_builder_rejects_mismatched_version_before_writing(release_distribution, tmp_path):
    project = release_distribution[0]
    output = tmp_path / "wrong-version"
    builder = (build_plugin if release_distribution[2]["host"] == "codex"
               else build_workswarm_plugin)
    with pytest.raises(ValueError, match="match the built runtime"):
        builder(output, project=project, release_version="0.2.1")
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
