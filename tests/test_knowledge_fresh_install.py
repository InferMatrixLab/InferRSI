"""Fresh-venv install smoke: base install package-only, skills extra unlocks the checkout chain.

Opt-in because it builds a real venv and installs from this source tree
(minutes of I/O, network access for the build-isolation backend, and an
install backend). Run with:

    RUN_FRESH_VENV=1 pytest tests/test_knowledge_fresh_install.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SOURCE = "calibrate-serving-simulation"

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_FRESH_VENV") != "1",
    reason="opt-in fresh-venv smoke; set RUN_FRESH_VENV=1 to build a venv and install this tree",
)


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _pip(venv_python: Path, *args: str) -> None:
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "--quiet", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


def _cli(venv_python: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [str(venv_python), "-m", "inferrsi", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO,
        env=env,
    )


def test_base_install_package_only_then_skills_extra_chain(tmp_path):
    venv = tmp_path / "fresh"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)], capture_output=True, text=True, encoding="utf-8"
    )
    assert created.returncode == 0, created.stderr
    python = _venv_python(venv)

    _pip(python, "install", str(REPO))  # base only: no PyYAML, no pytest/ruff

    package_only = _cli(python, "collect", "--limit", "2", "--json")
    assert package_only.returncode == 0, package_only.stderr
    assert json.loads(package_only.stdout)["items"]

    blocked = _cli(python, "collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS))
    assert blocked.returncode == 2
    assert "PyYAML" in blocked.stderr and ".[skills]" in blocked.stderr
    assert "Traceback" not in blocked.stderr

    _pip(python, "install", f"{REPO}[skills]")

    collected = _cli(
        python, "collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS), "--json"
    )
    assert collected.returncode == 0, collected.stderr
    item = json.loads(collected.stdout)["items"][0]
    revision, entrypoint = item["revision"], item["entrypoint"]

    read = _cli(
        python, "read", SOURCE, "--revision", revision, "--skill-root", str(SKILLS), "--material"
    )
    assert read.returncode == 0, read.stderr
    assert json.loads(read.stdout)["revision"] == revision

    output = tmp_path / "entry.md"
    resource = _cli(
        python,
        "resource",
        SOURCE,
        entrypoint,
        "--revision",
        revision,
        "--skill-root",
        str(SKILLS),
        "--output",
        str(output),
    )
    assert resource.returncode == 0, resource.stderr
    expected = json.loads(read.stdout)["content"].encode("utf-8")
    assert output.read_bytes() == expected
