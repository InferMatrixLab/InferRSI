import subprocess

import pytest

from tools.check_release import check_versions, release_version, resolve_release


@pytest.mark.parametrize("tag", ["v0.1.0", "v1.2.3", "v10.20.30"])
def test_stable_release_versions(tag):
    check_versions(tag, tag[1:], tag[1:])


@pytest.mark.parametrize("tag", [
    "1.2.3", "v01.2.3", "v1.2", "v1.2.3rc1", "v1.2.3+local", "v1.2.3\n", "--help",
])
def test_reject_ambiguous_and_nonstable_tags(tag):
    with pytest.raises(ValueError):
        release_version(tag)


@pytest.mark.parametrize("distribution,runtime", [("1.2.4", "1.2.3"), ("1.2.3", "1.2.4")])
def test_reject_inconsistent_distribution_or_runtime(distribution, runtime):
    with pytest.raises(ValueError, match="agree exactly"):
        check_versions("v1.2.3", distribution, runtime)


@pytest.fixture
def release_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def git(*args):
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Release Test")
    git("config", "user.email", "release@example.test")
    git("commit", "--allow-empty", "-m", "initial")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    return git


@pytest.mark.parametrize("annotated", [False, True])
def test_resolve_lightweight_and_annotated_tags(release_repo, annotated):
    git = release_repo
    args = ("-a", "-m", "release") if annotated else ()
    git("tag", *args, "v1.2.3")
    commit = git("rev-parse", "HEAD")
    assert resolve_release("v1.2.3", "main", commit) == commit


def test_branch_with_same_name_does_not_replace_a_missing_tag(release_repo):
    release_repo("branch", "v1.2.3")
    with pytest.raises(ValueError, match="existing tag"):
        resolve_release("v1.2.3", "main")


def test_reject_tag_outside_default_branch(release_repo):
    release_repo("checkout", "-b", "feature")
    release_repo("commit", "--allow-empty", "-m", "unmerged")
    release_repo("tag", "v1.2.3")
    with pytest.raises(ValueError, match="reachable"):
        resolve_release("v1.2.3", "main")


def test_reject_tag_moved_after_push_event(release_repo):
    release_repo("tag", "v1.2.3")
    with pytest.raises(ValueError, match="triggering commit"):
        resolve_release("v1.2.3", "main", "0" * 40)
