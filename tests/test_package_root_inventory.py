"""Exact inventory of the files directly under ``src/inferrsi/`` (#451 C1).

The flat package root is being retired. This guard pins the root to the exact file
set left after C1 and rejects any other root file. Each later removal PR (C2, R1,
A1/A2, M1) shrinks ``ROOT_FILES`` in the same change, until only ``__init__.py`` and
``__main__.py`` remain. It does not assert that final state early.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = "src/inferrsi"
# The 27 tracked root files before C1, minus the four that C1 moved into contracts/.
RETIRED_BY_C1 = frozenset({"_json_v1.py", "claim.py", "contracts.py", "runspec.py"})
ROOT_FILES = frozenset(
    {
        "__init__.py",
        "__main__.py",
        "_mindie_read_worker.py",
        "_repo_pack_data.py",
        "_skill_selection.py",
        "_source_snapshot.py",
        "arguments.py",
        "benchmark_operations.py",
        "catalog.py",
        "cli.py",
        "evaluation.py",
        "evidence_paths.py",
        "execution.py",
        "inspection.py",
        "knowledge_operations.py",
        "knowledge_store.py",
        "mindie_context.py",
        "mindie_mcp.py",
        "mindie_project.py",
        "reporting.py",
        "research.py",
        "skill_catalog.py",
        "summary_chart.py",
    }
)
# setuptools-scm writes this file at build time. It is gitignored wheel metadata and is
# never a tracked root file.
GENERATED = "_version.py"


def inventory_errors(found: set[str], expected: frozenset[str] = ROOT_FILES) -> list[str]:
    errors = [
        f"unexpected root file {PACKAGE}/{name}: a new module belongs in a subpackage"
        for name in sorted(found - expected)
    ]
    errors += [
        f"missing root file {PACKAGE}/{name}: shrink ROOT_FILES in the PR that removes it"
        for name in sorted(expected - found)
    ]
    return errors


def _listed(repo: Path, *options: str) -> set[str]:
    output = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", *options, "--", f":(glob){PACKAGE}/*"],
        check=True, capture_output=True,
    ).stdout
    return {name.rsplit("/", 1)[1] for name in output.decode("utf-8").split("\0") if name}


def root_files(repo: Path) -> set[str]:
    """Root files that the next commit of ``repo`` tracks.

    These are the tracked files still on disk plus the untracked files Git does not
    ignore. In a clean checkout that is exactly the tracked set. A new root file is
    therefore reported before and after it is staged, and the ignored generated
    ``_version.py`` never counts.
    """
    present = _listed(repo, "--cached", "--others", "--exclude-standard")
    return present - _listed(repo, "--deleted")


def test_inventory_is_the_exact_post_c1_set() -> None:
    assert len(ROOT_FILES) == 23
    assert not ROOT_FILES & RETIRED_BY_C1
    assert GENERATED not in ROOT_FILES
    assert {"__init__.py", "__main__.py"} <= ROOT_FILES


def test_on_disk_root_matches_the_inventory() -> None:
    on_disk = {path.name for path in (REPO / PACKAGE).iterdir() if path.is_file()}
    assert inventory_errors(on_disk - {GENERATED}) == []


def test_tracked_root_matches_the_inventory() -> None:
    if not (REPO / ".git").exists():
        pytest.skip("Git metadata is required for the tracked-file inventory")
    assert inventory_errors(root_files(REPO)) == []
    # The generated version file is ignored, so a build cannot add it to the inventory.
    ignored = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "-q", f"{PACKAGE}/{GENERATED}"], check=False
    )
    assert ignored.returncode == 0


@pytest.mark.parametrize("name", ["helper.py", "py.typed", GENERATED, *sorted(RETIRED_BY_C1)])
def test_an_added_root_file_is_rejected(name: str) -> None:
    assert inventory_errors(set(ROOT_FILES) | {name}) == [
        f"unexpected root file {PACKAGE}/{name}: a new module belongs in a subpackage"
    ]


def test_a_removed_root_file_must_shrink_the_inventory() -> None:
    assert inventory_errors(set(ROOT_FILES) - {"cli.py"}) == [
        f"missing root file {PACKAGE}/cli.py: shrink ROOT_FILES in the PR that removes it"
    ]
    # A later removal PR passes once it shrinks the expected set with the files.
    smaller = ROOT_FILES - {"_repo_pack_data.py", "evidence_paths.py"}
    assert inventory_errors(set(smaller), smaller) == []


def test_git_view_reports_root_changes_before_and_after_staging(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    def unexpected(name: str) -> str:
        return f"unexpected root file {PACKAGE}/{name}: a new module belongs in a subpackage"

    git("init", "-q")
    (tmp_path / ".gitignore").write_bytes((REPO / ".gitignore").read_bytes())
    root = tmp_path / PACKAGE
    (root / "contracts").mkdir(parents=True)
    for name in ROOT_FILES:
        (root / name).write_text("", encoding="utf-8")
    # A subpackage file is not a root file, and the ignored build output never counts.
    (root / "contracts" / "extra.py").write_text("", encoding="utf-8")
    (root / GENERATED).write_text("", encoding="utf-8")
    assert root_files(tmp_path) == ROOT_FILES
    git("add", ".")
    assert root_files(tmp_path) == ROOT_FILES

    (root / "helper.py").write_text("", encoding="utf-8")
    assert inventory_errors(root_files(tmp_path)) == [unexpected("helper.py")]
    git("add", ".")
    assert inventory_errors(root_files(tmp_path)) == [unexpected("helper.py")]
    (root / "helper.py").unlink()
    assert inventory_errors(root_files(tmp_path)) == []

    # Tracking the generated file by force is a root addition like any other.
    git("add", "--force", f"{PACKAGE}/{GENERATED}")
    assert inventory_errors(root_files(tmp_path)) == [unexpected(GENERATED)]
    git("rm", "--cached", "-q", f"{PACKAGE}/{GENERATED}")
    (root / "runspec.py").write_text("", encoding="utf-8")
    assert inventory_errors(root_files(tmp_path)) == [unexpected("runspec.py")]
    (root / "runspec.py").unlink()
    (root / "cli.py").unlink()
    assert inventory_errors(root_files(tmp_path)) == [
        f"missing root file {PACKAGE}/cli.py: shrink ROOT_FILES in the PR that removes it"
    ]
