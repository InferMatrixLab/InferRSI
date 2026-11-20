import json
import subprocess
import sys

import pytest

from tools import compare_find_layouts as replay


@pytest.mark.parametrize("dirty", ["index", "tracked", "untracked", "replacement"])
def test_second_dirty_arm_stops_before_any_search(tmp_path, monkeypatch, dirty):
    try:
        replay.check_git_version()
    except replay.GitVersionError as error:
        pytest.skip(str(error))
    base = tmp_path / "base"
    candidate = tmp_path / "candidate"
    base.mkdir()

    def git(root, *args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    git(base, "init", "-q")
    (base / "source").write_text("original")
    git(base, "add", "source")
    git(
        base,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    sha = git(base, "rev-parse", "HEAD")
    git(base, "worktree", "add", "--quiet", "--detach", str(candidate), sha)
    replay.validate_worktree(candidate, sha)
    (candidate / ("scratch" if dirty == "untracked" else "source")).write_text("modified")
    if dirty == "index":
        git(candidate, "add", "source")
    if dirty == "replacement":
        git(
            candidate,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qam",
            "different tree",
        )
        replacement = git(candidate, "rev-parse", "HEAD")
        git(candidate, "reset", "--soft", sha)
        git(candidate, "replace", sha, replacement)
        assert not git(candidate, "status", "--porcelain")

    (tmp_path / "layout-queries.json").write_text(json.dumps({"base_sha": sha}))
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare",
            "--base",
            str(base),
            "--candidate",
            str(candidate),
            "--candidate-sha",
            sha,
            "--output",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(ValueError, match="Dirty worktree"):
        replay.main()
    assert not (tmp_path / "out").exists()


def test_comparison_old_git_stops_before_validating_worktrees(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "git version 2.43.0\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare",
            "--base",
            "unused",
            "--candidate",
            "unused",
            "--candidate-sha",
            "unused",
            "--output",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        replay.main()
    assert stopped.value.code == 2
    assert "Find layout comparison requires Git >= 2.45" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
