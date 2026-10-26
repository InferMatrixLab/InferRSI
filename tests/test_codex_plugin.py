"""Exercise a distributed plugin outside a checkout, without site packages."""

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tools.build_codex_plugin import PROJECT, _io_path, build_plugin


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
