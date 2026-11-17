"""Publication diagnostics and durable directory ordering."""

import errno
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.apps import archive


def _result():
    root = Path(__file__).resolve().parents[1]
    path = root / "docs/contracts/fixtures/t108-v4/apps-not-started.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("code,category", [
    (errno.EEXIST, "conflict"), (errno.ENOTEMPTY, "conflict"),
    (errno.ENOSYS, "unsupported"), (errno.EINVAL, "unsupported"),
    (errno.ENOTSUP, "unsupported"), (errno.EIO, "I/O"),
])
def test_publication_diagnostic_preserves_category_and_refs(tmp_path, monkeypatch, code, category):
    def fail(*args):
        raise OSError(code, "private path must not leak")

    monkeypatch.setattr(archive, "_publish_directory", fail)
    result = _result()
    output = archive.publish_result(tmp_path, result, output_id="failed")
    assert output.directory is None
    assert output.result["exit_code"] == 6
    assert category in output.result["error"]["message"]
    assert "private path" not in output.result["error"]["message"]
    assert output.result["record_ref"] == result["record_ref"]
    assert not (tmp_path / "output/failed").exists()


def test_directory_sync_order(tmp_path, monkeypatch):
    events = []
    original = archive._publish_directory

    def sync(path):
        events.append(("sync", path.name))

    def publish(staging, destination):
        events.append(("rename", destination.name))
        original(staging, destination)

    monkeypatch.setattr(archive, "_sync_directory", sync)
    monkeypatch.setattr(archive, "_publish_directory", publish)
    output = archive.publish_result(tmp_path, _result(), output_id="ordered")
    assert output.directory is not None
    assert events[0] == ("sync", tmp_path.name)
    assert events[1][0] == "sync" and events[1][1].startswith(".pending-")
    assert events[2:] == [("sync", "output"), ("rename", "ordered"), ("sync", "output")]


def test_sync_failure_after_rename_keeps_publication_and_reports_unknown(tmp_path, monkeypatch):
    renamed = False
    original = archive._publish_directory

    def publish(staging, destination):
        nonlocal renamed
        original(staging, destination)
        renamed = True

    def sync(path):
        if renamed:
            raise OSError(errno.EIO, "private detail")

    monkeypatch.setattr(archive, "_publish_directory", publish)
    monkeypatch.setattr(archive, "_sync_directory", sync)
    result = _result()
    output = archive.publish_result(tmp_path, result, output_id="uncertain")
    assert output.directory is None
    assert output.result["exit_code"] == 6
    assert "uncertain" in output.result["error"]["message"]
    assert output.result["record_ref"] == result["record_ref"]
    assert archive.read_result(tmp_path, "uncertain").result == result


def test_existing_empty_directory_is_not_replaced(tmp_path):
    destination = tmp_path / "output/existing"
    destination.mkdir(parents=True)
    output = archive.publish_result(tmp_path, _result(), output_id="existing")
    assert output.directory is None
    assert "conflict" in output.result["error"]["message"]
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("fail", [False, True])
def test_posix_directory_sync_always_closes_fd(monkeypatch, fail):
    events = []

    def fsync(fd):
        events.append(("fsync", fd))
        if fail:
            raise OSError(errno.EIO, "sync failed")

    fake_os = SimpleNamespace(
        name="posix", O_RDONLY=0, O_DIRECTORY=2,
        open=lambda path, flags: events.append(("open", str(path), flags)) or 17,
        fsync=fsync, close=lambda fd: events.append(("close", fd)),
    )
    monkeypatch.setattr(archive, "os", fake_os)
    if fail:
        with pytest.raises(OSError):
            archive._sync_directory(Path("directory"))
    else:
        archive._sync_directory(Path("directory"))
    assert events == [("open", "directory", 2), ("fsync", 17), ("close", 17)]


def test_prepublication_sync_failure_never_renames(tmp_path, monkeypatch):
    def fail(path):
        raise OSError(errno.EINVAL, "not supported")

    def unexpected(*args):
        pytest.fail("rename must not run after failed directory sync")

    monkeypatch.setattr(archive, "_sync_directory", fail)
    monkeypatch.setattr(archive, "_publish_directory", unexpected)
    output = archive.publish_result(tmp_path, _result(), output_id="unsynced")
    assert "unsupported" in output.result["error"]["message"]
    assert not (tmp_path / "output/unsynced").exists()
