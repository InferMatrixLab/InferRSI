"""Fresh-venv install smoke: the base install reads checkout skills and task files.

PyYAML is a core dependency, so the base install (no extras) reads checkout skills and
validates and previews the shared task fixture outside the checkout. The ``skills``
extra stays installable as a compatibility alias.

Opt-in because it builds a real venv and installs from this source tree
(minutes of I/O, network access for the build-isolation backend, and an
install backend). Run with:

    RUN_FRESH_VENV=1 pytest tests/knowledge/test_knowledge_fresh_install.py

The installed-package and release CI jobs enforce the same checkout-versus-wheel
byte inventory through tests/repository/check_installed.py when INFERRSI_CHECKOUT_RESOURCES
points at the checkout (no second venv). This module remains the opt-in full
fresh-venv path for local or extra isolation.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
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


def test_base_install_reads_checkout_skills_and_task_files_and_keeps_skills_alias():
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

        _pip(python, "install", str(build_input))  # base: core PyYAML, no extras or pytest/ruff

        package_only = _cli(python, "collect", "--limit", "2", "--json")
        assert package_only.returncode == 0, package_only.stderr
        assert json.loads(package_only.stdout)["items"]

        base_collect = _cli(
            python, "collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS), "--json"
        )
        assert base_collect.returncode == 0, base_collect.stderr
        assert json.loads(base_collect.stdout)["items"]

        # The shared complete task fixture, read from the base install outside the checkout.
        task_file = workspace / "task" / "complete.yaml"
        task_file.parent.mkdir()
        shutil.copyfile(REPO / "tests" / "fixtures" / "task-input" / "complete.yaml", task_file)
        outside = workspace / "outside"
        outside.mkdir()
        for action in ("validate", "preview"):
            checked = subprocess.run(
                [str(python), "-I", "-m", "inferrsi", "task", action, str(task_file), "--json"],
                capture_output=True, text=True, encoding="utf-8", cwd=outside,
            )
            assert checked.returncode == 0, checked.stderr
            assert json.loads(checked.stdout)["valid"] is True
        preview = json.loads(checked.stdout)
        assert preview["complete"] and preview["task"]["environment"]["backend"] == "cuda"
        assert preview["task"]["environment"]["repetitions"] == 5
        assert preview["task"]["acceptance"]["min_improvement_pct"] == 2.5
        assert list(outside.iterdir()) == []

        _pip(python, "install", f"{build_input}[skills]")  # compatibility alias still installs

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


inventory = {**walk(("knowledge", "data")), **walk(("resources", "repo_packs"))}
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


def _check_installed_doctor(python, package, workspace):
    # Keep the disposable target separate from both the checkout and the installed wheel.
    target = workspace / "target"
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    subprocess.run(
        ["git", "-C", str(target), "-c", "user.name=Fixture", "-c", "user.email=test@invalid",
         "-c", "commit.gpgSign=false", "commit", "-q", "--allow-empty", "-m", "fixture"],
        check=True,
    )

    def doctor(*args):
        return subprocess.run(
            [str(python), "-I", "-X", "utf8", "-m", "inferrsi", "doctor", *args],
            cwd=target, capture_output=True, text=True, encoding="utf-8",
        )

    def basic():
        result = doctor()
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["repository"]["available"] and report["target_python"]["environment"]
        assert report["device"]["status"] == "available" and "repository_pack" not in report

    descriptors = package.parent / "resources" / "repo_packs"
    assert not (package.parent / "harness" / "data" / "repo_packs").exists()
    paths = sorted(descriptors.glob("*.json"))

    def selected(path):
        result = doctor("--repo-type", path.stem)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["repository_pack"] == json.loads(path.read_bytes())

    basic()
    for path in paths:
        selected(path)

    # Remove the former implicit default specifically, from this test's isolated install.
    missing = descriptors / "vllm_omni.json"
    missing.unlink()
    basic()
    for path in paths:
        if path != missing:
            selected(path)
    failure = doctor("--repo-type", missing.stem)
    assert failure.returncode == 2 and missing.name in failure.stderr
    assert not failure.stdout and "Traceback" not in failure.stderr


def test_installed_wheel_outside_the_checkout_holds_every_resource_byte_for_byte():
    """K02-3: a real install resolves the same resource list and bytes as the checkout."""
    source_tree = REPO / "src" / "inferrsi"
    expected = {}
    for root in (source_tree / "knowledge" / "data", source_tree / "resources" / "repo_packs"):
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

        find_command = [str(python), "-I", "-X", "utf8", "-m", "inferrsi", "find", "graph mode",
                        "--no-external", "--limit", "1", "--json"]
        run_options = {"capture_output": True, "text": True, "encoding": "utf-8", "cwd": workspace}
        plain = subprocess.run(find_command, **run_options)
        assert plain.returncode == 0, plain.stderr
        default = json.loads(plain.stdout)
        assert default["items"][0]["id"] == "ascend-graph-mode"
        assert "searchspace_filter" not in default

        find_command += ["--searchspace-coordinate", "SSD", "Diagnose"]
        bare = subprocess.run(find_command, **run_options)
        assert bare.returncode == 2 and "explicit --skill-root" in bare.stderr

        selected = subprocess.run(find_command + ["--skill-root", str(SKILLS)], **run_options)
        assert selected.returncode == 0, selected.stderr
        filtered = json.loads(selected.stdout)
        assert filtered["items"][0]["id"] == "ascend-graph-mode"
        assert "--skill-root" in filtered["items"][0]["ref"]
        assert filtered["searchspace_filter"]["stage"] == "Diagnose"

        _check_installed_doctor(python, package, workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
