"""Clean-install contracts: package-only commands without PyYAML and the real-CLI checkout chain."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.knowledge_operations import KnowledgeReader

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SOURCE = "calibrate-serving-simulation"


def _cli_env(blocked_yaml: Path | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if blocked_yaml is not None:
        env["PYTHONPATH"] = str(blocked_yaml) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(args: list[str], env: dict, *, cwd: Path = REPO) -> subprocess.CompletedProcess:
    # Real CLI entry point, not an in-process main() call.
    return subprocess.run(
        [sys.executable, "-m", "inferrsi", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
    )


@pytest.fixture
def without_yaml(tmp_path):
    # Shadow PyYAML with a failing module: exactly the base install without
    # the skills extra, without touching the test environment itself.
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "yaml.py").write_text(
        "raise ImportError('PyYAML intentionally unavailable for this test')\n",
        encoding="utf-8",
    )
    return blocked


def test_package_only_commands_work_without_pyyaml(without_yaml):
    env = _cli_env(without_yaml)
    listed = _run(["collect", "--limit", "1", "--json"], env)
    assert listed.returncode == 0, listed.stderr
    items = json.loads(listed.stdout)["items"]
    assert items and items[0]["authority"] == "package"
    result = _run(["read", items[0]["id"]], env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["id"] == items[0]["id"]


def test_skill_root_without_pyyaml_fails_with_install_hint(without_yaml):
    result = _run(
        ["collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS)],
        _cli_env(without_yaml),
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert ".[skills]" in result.stderr and "PyYAML" in result.stderr


def test_install_hint_is_actionable_outside_the_repository(without_yaml, tmp_path):
    # The hint must not depend on the caller's working directory.
    result = _run(
        ["collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS)],
        _cli_env(without_yaml),
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "<inferrsi-checkout>.[skills]" in result.stderr


def test_checkout_chain_collect_read_resource_through_real_cli(tmp_path):
    env = _cli_env()
    collected = _run(
        ["collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS), "--json"], env
    )
    assert collected.returncode == 0, collected.stderr
    item = json.loads(collected.stdout)["items"][0]
    revision, entrypoint = item["revision"], item["entrypoint"]

    read = _run(
        ["read", SOURCE, "--revision", revision, "--skill-root", str(SKILLS), "--material"], env
    )
    assert read.returncode == 0, read.stderr
    assert json.loads(read.stdout)["revision"] == revision

    output = tmp_path / "entry.md"
    resource = _run(
        [
            "resource",
            SOURCE,
            entrypoint,
            "--revision",
            revision,
            "--skill-root",
            str(SKILLS),
            "--output",
            str(output),
        ],
        env,
    )
    assert resource.returncode == 0, resource.stderr
    expected = KnowledgeReader(skill_root=SKILLS).read(SOURCE).content[entrypoint]
    assert output.read_bytes() == expected


def test_corrupted_store_database_fails_without_traceback(tmp_path):
    workspace = tmp_path / "broken-store"
    workspace.mkdir()
    (workspace / "knowledge.sqlite3").write_bytes(b"this is not a database")
    result = _run(["read", "some-id", "--store", str(workspace)], _cli_env())
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
