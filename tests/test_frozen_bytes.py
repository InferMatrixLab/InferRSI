"""Git conversion must not change historical artifacts or future frozen bytes."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


@pytest.mark.parametrize("autocrlf", ["false", "true", "input"])
def test_frozen_bytes_survive_add_and_checkout(tmp_path, autocrlf):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.autocrlf", autocrlf)
    (tmp_path / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    paths = ["evidence/sample/plan/freeze.json", "tests/fixtures/legacy/helper.py"]
    payload = b'first line\r\nsecond line\nlast line\r\n'
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    git(tmp_path, "add", ".")
    for name in paths:
        assert git(tmp_path, "check-attr", "text", "--", name).strip().endswith(b": unset")
        assert git(tmp_path, "show", f":{name}") == payload
        (tmp_path / name).unlink()
    git(tmp_path, "checkout-index", "--all", "--force")
    for name in paths:
        assert (tmp_path / name).read_bytes() == payload
    for name in ("evidence/README.md", "evidence/_template/plan/README.md"):
        assert git(tmp_path, "check-attr", "text", "--", name).strip().endswith(b": set")


def test_checked_in_frozen_files_match_git_blobs():
    if not (ROOT / ".git").exists():
        pytest.skip("Git metadata is required for blob comparisons")
    names = git(ROOT, "ls-files", "-z", "evidence", "tests/fixtures/legacy").split(b"\0")
    checked = 0
    for encoded in filter(None, names):
        name = encoded.decode("utf-8")
        if name == "evidence/README.md" or name.startswith("evidence/_template/"):
            continue
        blob = git(ROOT, "show", f"HEAD:{name}")
        assert hashlib.sha256((ROOT / name).read_bytes()).digest() == hashlib.sha256(blob).digest()
        assert git(ROOT, "check-attr", "text", "--", name).strip().endswith(b": unset")
        checked += 1
    assert checked > 0
