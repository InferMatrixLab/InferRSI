"""Exact inventory of the files directly under ``src/inferrsi/`` (#451 C1, C2; #412 R1).

The flat package root is being retired. This guard pins the root to the exact file
set left after R1 and rejects any other root file. Each later removal PR (A1/A2, M1)
shrinks ``ROOT_FILES`` in the same change, until only ``__init__.py`` and
``__main__.py`` remain. It does not assert that final state early.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = "src/inferrsi"
# The 27 tracked root files before C1, minus the four that C1 moved into contracts/,
# the two that C2 moved into resources/, contracts/ and apps/, and the eleven that R1
# retired: seven Knowledge shells, three old-run forwarders and the root inspection
# binding, whose implementations are in knowledge/ and apps/.
RETIRED_BY_C1 = frozenset({"_json_v1.py", "claim.py", "contracts.py", "runspec.py"})
RETIRED_BY_C2 = frozenset({"_repo_pack_data.py", "evidence_paths.py"})
RETIRED_BY_R1 = frozenset(
    {
        "_skill_selection.py",
        "_source_snapshot.py",
        "catalog.py",
        "knowledge_operations.py",
        "knowledge_store.py",
        "research.py",
        "skill_catalog.py",
        "evaluation.py",
        "execution.py",
        "reporting.py",
        "inspection.py",
    }
)
RETIRED = RETIRED_BY_C1 | RETIRED_BY_C2 | RETIRED_BY_R1
ROOT_FILES = frozenset(
    {
        "__init__.py",
        "__main__.py",
        "_mindie_read_worker.py",
        "arguments.py",
        "benchmark_operations.py",
        "cli.py",
        "mindie_context.py",
        "mindie_mcp.py",
        "mindie_project.py",
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


def test_inventory_is_the_exact_post_r1_set() -> None:
    assert len(ROOT_FILES) == 10
    assert len(RETIRED_BY_C1) == 4 and len(RETIRED_BY_C2) == 2 and len(RETIRED_BY_R1) == 11
    assert not ROOT_FILES & RETIRED
    assert len(RETIRED) == 17
    # 27 before C1, 23 after C1, 21 after C2, 10 after R1.
    assert len(ROOT_FILES | RETIRED) == 27
    assert len(ROOT_FILES | RETIRED_BY_C2 | RETIRED_BY_R1) == 23
    assert len(ROOT_FILES | RETIRED_BY_R1) == 21
    assert GENERATED not in ROOT_FILES
    assert {"__init__.py", "__main__.py"} <= ROOT_FILES
    # The final two-file root waits for the A1/A2 and M1 moves; it is not asserted here.
    assert ROOT_FILES - {"__init__.py", "__main__.py"} == {
        "_mindie_read_worker.py", "arguments.py", "benchmark_operations.py", "cli.py",
        "mindie_context.py", "mindie_mcp.py", "mindie_project.py", "summary_chart.py",
    }
    # C2 moved its two files; it left nothing behind under either old name.
    assert (REPO / PACKAGE / "resources" / "repository_packs.py").is_file()
    assert (REPO / PACKAGE / "contracts" / "evidence.py").is_file()
    assert (REPO / PACKAGE / "apps" / "evidence_layout.py").is_file()
    # R1 deleted its eleven files. Each implementation is at its canonical path.
    for name in RETIRED_BY_R1 - {"evaluation.py", "execution.py", "reporting.py",
                                 "inspection.py"}:
        assert (REPO / PACKAGE / "knowledge" / name).is_file(), name
    for name in ("legacy/evaluation.py", "legacy/run.py", "legacy/reporting.py",
                 "inspection.py"):
        assert (REPO / PACKAGE / "apps" / name).is_file(), name
    for name in RETIRED:
        assert not (REPO / PACKAGE / name).exists(), name
        # No package directory stands in for a retired module either.
        assert not (REPO / PACKAGE / name.removesuffix(".py") / "__init__.py").exists() or (
            name == "contracts.py"
        ), name


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


@pytest.mark.parametrize("name", ["helper.py", "py.typed", GENERATED, *sorted(RETIRED)])
def test_an_added_root_file_is_rejected(name: str) -> None:
    assert inventory_errors(set(ROOT_FILES) | {name}) == [
        f"unexpected root file {PACKAGE}/{name}: a new module belongs in a subpackage"
    ]


def test_a_removed_root_file_must_shrink_the_inventory() -> None:
    assert inventory_errors(set(ROOT_FILES) - {"cli.py"}) == [
        f"missing root file {PACKAGE}/cli.py: shrink ROOT_FILES in the PR that removes it"
    ]
    # A later removal PR passes once it shrinks the expected set with the files.
    smaller = ROOT_FILES - {"cli.py", "arguments.py"}
    assert inventory_errors(set(smaller), smaller) == []
    # C2 itself: the 23-file set it started from no longer matched its 21-file root.
    after_c2 = ROOT_FILES | RETIRED_BY_R1
    before_c2 = after_c2 | RETIRED_BY_C2
    assert inventory_errors(set(after_c2), before_c2) == [
        f"missing root file {PACKAGE}/{name}: shrink ROOT_FILES in the PR that removes it"
        for name in sorted(RETIRED_BY_C2)
    ]
    # R1 itself: the 21-file set it started from no longer matches the 10-file root.
    assert inventory_errors(set(ROOT_FILES), after_c2) == [
        f"missing root file {PACKAGE}/{name}: shrink ROOT_FILES in the PR that removes it"
        for name in sorted(RETIRED_BY_R1)
    ]
    # Keeping any old file beside its moved implementation is rejected, one by one
    # and all together.
    assert inventory_errors(set(after_c2)) == [
        f"unexpected root file {PACKAGE}/{name}: a new module belongs in a subpackage"
        for name in sorted(RETIRED_BY_R1)
    ]
    assert inventory_errors(set(ROOT_FILES) | RETIRED_BY_C2) == [
        f"unexpected root file {PACKAGE}/{name}: a new module belongs in a subpackage"
        for name in sorted(RETIRED_BY_C2)
    ]
    # Deleting only ten of the eleven, or one file too many, is not the R1 root.
    for name in sorted(RETIRED_BY_R1):
        assert inventory_errors(set(ROOT_FILES) | {name}) == [
            f"unexpected root file {PACKAGE}/{name}: a new module belongs in a subpackage"
        ]
    for name in sorted(ROOT_FILES):
        assert inventory_errors(set(ROOT_FILES) - {name}) == [
            f"missing root file {PACKAGE}/{name}: shrink ROOT_FILES in the PR that removes it"
        ]


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
