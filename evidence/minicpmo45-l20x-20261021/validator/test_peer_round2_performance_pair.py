"""Preflight controls require no model or GPU service."""

import subprocess

import pytest
from peer_round2_performance_pair import check_revision, require_single_gpu, require_unused_port


@pytest.mark.parametrize("value", [None, "", " ", "0,1", "-1", "all"])
def test_reject_ambiguous_device(value):
    with pytest.raises(ValueError):
        require_single_gpu(value)


@pytest.mark.parametrize("value", ["0", "GPU-test-reservation"])
def test_one_device(value):
    require_single_gpu(value)


def test_revision_and_clean_tree_are_required(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-q")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-qm",
        "fixture",
    )
    revision = git("rev-parse", "HEAD")
    assert check_revision(tmp_path, revision) == revision
    with pytest.raises(ValueError):
        check_revision(tmp_path, "0" * 40)
    (tmp_path / "untracked.py").write_text("changed source\n")
    with pytest.raises(ValueError):
        check_revision(tmp_path, revision)


def test_live_port_is_rejected():
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(ValueError):
            require_unused_port(listener.getsockname()[1])
