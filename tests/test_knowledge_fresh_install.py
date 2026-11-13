"""Fresh-venv install smoke: base install package-only, skills extra unlocks the checkout chain.

Opt-in because it builds a real venv and installs from this source tree
(minutes of I/O, network access for the build-isolation backend, and an
install backend). Run with:

    RUN_FRESH_VENV=1 pytest tests/test_knowledge_fresh_install.py
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "src" / "inferrsi" / "knowledge" / "data" / "skill_library"
SOURCE = "calibrate-serving-simulation"

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_FRESH_VENV") != "1",
    reason="opt-in fresh-venv smoke; set RUN_FRESH_VENV=1 to build a venv and install this tree",
)


def _short_workspace() -> Path:
    # The packaged skill library nests deeply (#44/#46); the default pytest tmp
    # base can push an installed file path past Windows' 260-char limit. A short
    # drive-root base keeps it well under MAX_PATH on Windows and Linux alike.
    base = Path(os.path.abspath(os.sep)) / "tmp"
    base.mkdir(exist_ok=True)
    workspace = base / f"inferrsi-fresh-{os.getpid()}"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    return workspace


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _pip(venv_python: Path, *args: str) -> None:
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "--quiet", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, SETUPTOOLS_SCM_PRETEND_VERSION="0.0.0"),
    )
    assert result.returncode == 0, result.stderr


def _short_source_copy(workspace: Path) -> Path:
    """Copy the build inputs under a short base.

    The K02 resource roots add a directory level to already deep canonical
    resource names. A wheel build under a long checkout path can exceed Windows'
    260-character limit inside its own build tree, so the inputs are staged under
    the short workspace before the build. The copy carries no Git metadata, so
    the build reads an explicit pretend version.
    """
    source = workspace / "source"
    source.mkdir()
    shutil.copytree(REPO / "src", source / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    for name in ("pyproject.toml", "README.md", "LICENSE", "MANIFEST.in"):
        shutil.copyfile(REPO / name, source / name)
    return source


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


def test_base_install_package_only_then_skills_extra_chain():
    workspace = _short_workspace()
    try:
        venv = workspace / "venv"
        created = subprocess.run(
            [sys.executable, "-m", "venv", str(venv)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert created.returncode == 0, created.stderr
        python = _venv_python(venv)
        build_input = _short_source_copy(workspace)

        _pip(python, "install", str(build_input))  # base only: no PyYAML, no pytest/ruff

        package_only = _cli(python, "collect", "--limit", "2", "--json")
        assert package_only.returncode == 0, package_only.stderr
        assert json.loads(package_only.stdout)["items"]

        blocked = _cli(
            python, "collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS)
        )
        assert blocked.returncode == 2
        assert "PyYAML" in blocked.stderr and "<inferrsi-checkout>[skills]" in blocked.stderr
        assert "Traceback" not in blocked.stderr

        _pip(python, "install", f"{build_input}[skills]")

        collected = _cli(
            python, "collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS), "--json"
        )
        assert collected.returncode == 0, collected.stderr
        item = json.loads(collected.stdout)["items"][0]
        revision, entrypoint = item["revision"], item["entrypoint"]

        read = _cli(
            python,
            "read",
            SOURCE,
            "--revision",
            revision,
            "--skill-root",
            str(SKILLS),
            "--material",
        )
        assert read.returncode == 0, read.stderr
        assert json.loads(read.stdout)["revision"] == revision

        output = workspace / "entry.md"
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
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


INVENTORY_SCRIPT = """
import hashlib, json, sys
from importlib.resources import files

import inferrsi

assert "src" != __import__("pathlib").Path(inferrsi.__file__).resolve().parents[1].name


def walk(parts):
    found = {}
    pending = [(files("inferrsi").joinpath(*parts), "/".join(parts))]
    while pending:
        node, name = pending.pop()
        for child in node.iterdir():
            relative = name + "/" + child.name
            if child.is_dir():
                if child.name != "__pycache__":
                    pending.append((child, relative))
            else:
                found[relative] = hashlib.sha256(child.read_bytes()).hexdigest()
    return found


inventory = {**walk(("knowledge", "data")), **walk(("harness", "data"))}
json.dump({"package": inferrsi.__file__, "inventory": inventory}, sys.stdout)
"""


def _short_source_copy(workspace: Path) -> Path:
    """Copy the build inputs under a short base.

    The K02 resource roots add a directory level to already deep canonical
    resource names. A wheel build under a long checkout path can exceed Windows'
    260-character limit inside its own build tree, so the inputs are staged under
    the short workspace before the build.
    """
    source = workspace / "source"
    source.mkdir()
    shutil.copytree(REPO / "src", source / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("pyproject.toml", "README.md", "LICENSE", "MANIFEST.in"):
        shutil.copyfile(REPO / name, source / name)
    return source


def test_installed_wheel_outside_the_checkout_holds_every_resource_byte_for_byte():
    """K02-3: a real install resolves the same resource list and bytes as the checkout."""
    source_tree = REPO / "src" / "inferrsi"
    expected = {}
    for root in (source_tree / "knowledge" / "data", source_tree / "harness" / "data"):
        for path in root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                expected[path.relative_to(source_tree).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    assert expected, "the checkout resource roots are empty"

    workspace = _short_workspace()
    try:
        venv = workspace / "venv"
        created = subprocess.run(
            [sys.executable, "-m", "venv", str(venv)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert created.returncode == 0, created.stderr
        python = _venv_python(venv)

        build_input = _short_source_copy(workspace)
        _pip(python, "install", str(build_input))

        script = workspace / "inventory.py"
        script.write_text(INVENTORY_SCRIPT, encoding="utf-8")
        # Run outside the checkout with isolated imports: the installed package
        # is the only source of these resources.
        result = subprocess.run(
            [str(python), "-I", str(script)],
            capture_output=True, text=True, encoding="utf-8", cwd=workspace,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        package = Path(payload["package"]).resolve()
        assert not package.is_relative_to(REPO)
        assert package.is_relative_to(venv)
        assert payload["inventory"] == expected
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
