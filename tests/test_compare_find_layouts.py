import json
import subprocess
import sys

import pytest

from tools import compare_find_layouts as replay


@pytest.mark.parametrize("dirty", ["index", "tracked", "untracked"])
def test_second_dirty_arm_stops_before_any_search(tmp_path, monkeypatch, dirty):
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
