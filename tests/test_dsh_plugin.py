"""Check the native bundle and its isolated launcher without requiring DSH in CI."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile

import pytest

from tools.build_dsh_plugin import build_bundle
from tools.plugin_bundle import PROJECT, _io_path


@pytest.fixture(scope="module", autouse=True)
def require_node_in_ci():
    """CI must exercise the native form, bridge and real SSH transport checks."""
    if os.environ.get("CI") and shutil.which("node") is None:
        pytest.fail("Node.js is required for DSH form, bridge and SSH checks in CI")


def test_manual_bundle_runs_from_an_external_workspace(tmp_path):
    archive = tmp_path / "inferrsi-dsh.tgz"
    result = build_bundle(archive)
    assert result["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()

    installed = _io_path(tmp_path / "extracted")
    with tarfile.open(archive) as bundle:
        assert all(member.isfile() and member.name.startswith("package/")
                   for member in bundle.getmembers())
        bundle.extractall(installed)

    package = installed / "package"
    metadata = json.loads((package / "package.json").read_text(encoding="utf-8"))
    assert metadata["name"] == "inferrsi-dsh"
    assert (package / metadata["dsh"]["bundle"]["patch"]).is_file()
    assert (package / metadata["main"]).is_file()
    assert metadata["dsh"]["client"]["platform"] == "web"
    client = package / metadata["exports"]["./client"]
    assert client.is_file()
    if shutil.which("node"):
        subprocess.run([
            "node", str(PROJECT / "tests/check_dsh_form.cjs"),
            str(PROJECT / "plugins/inferrsi-dsh/form.cjs"), str(client),
        ], check=True, capture_output=True, text=True, timeout=30)
        subprocess.run([
            "node", str(PROJECT / "tests/check_dsh_bridge.cjs"),
            str(package / "remote-host.cjs"),
        ], check=True, capture_output=True, text=True, timeout=30)
    assert (package / "LICENSE").read_bytes() == (PROJECT / "LICENSE").read_bytes()
    skill = package / "assets/inferrsi"
    shared_skill = PROJECT / "plugins/inferrsi/skills/inferrsi"
    for relative in ("SKILL.md", "scripts/inferrsi.py"):
        assert (skill / relative).read_bytes() == (shared_skill / relative).read_bytes()
    guide = PROJECT / "docs/dashboard.md"
    assert (skill / "docs/dashboard.md").read_bytes() == guide.read_bytes()

    runtime = package / "runtime"
    manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == result["runtime_files"]
    for relative, digest in manifest["files"].items():
        installed_bytes = (runtime / relative).read_bytes()
        assert installed_bytes == _io_path(PROJECT / "src" / relative).read_bytes()
        assert hashlib.sha256(installed_bytes).hexdigest() == digest
    with zipfile.ZipFile(io.BytesIO((package / "remote-runtime.zip").read_bytes())) as remote:
        assert remote.read("inferrsi/data/dashboard/template.html") == (
            runtime / "inferrsi/data/dashboard/template.html"
        ).read_bytes()

    target = tmp_path / "external workspace"
    target.mkdir()
    launcher = [sys.executable, "-I", "-S", "-X", "utf8", str(skill / "scripts/inferrsi.py")]

    def invoke(*args):
        response = subprocess.run(
            [*launcher, *args], cwd=target, capture_output=True,
            text=True, encoding="utf-8", timeout=45,
        )
        assert response.returncode == 0, response.stderr
        return json.loads(response.stdout)

    info = invoke("--plugin-info")
    assert info["plugin_version"] == metadata["version"]
    assert info["runtime_version"] == manifest["runtime_version"]
    assert info["content_sha256"] == manifest["content_sha256"]
    item = invoke("collect", "Qwen", "--limit", "1", "--json")["items"][0]
    record = invoke("read", item["ref"], "--revision", item["revision"])
    assert record["revision"] == item["revision"]

    campaign = target / "campaign"
    campaign.mkdir()
    (campaign / "campaign.json").write_text(
        json.dumps({"campaign_id": "synthetic-dashboard", "synthetic": True}), encoding="utf-8",
    )
    dashboard = invoke("dashboard", "--input", str(campaign))
    html = campaign / "dashboard.html"
    assert dashboard["dashboard"] == str(html)
    assert "InferRSI · Optimization dashboard" in html.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        build_bundle(archive)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for native SSH checks")
def test_remote_ssh_connection_and_scoped_operations():
    subprocess.run(["node", str(PROJECT / "tests/check_dsh_remote.cjs")],
                   cwd=PROJECT, check=True, capture_output=True, text=True, timeout=60)
