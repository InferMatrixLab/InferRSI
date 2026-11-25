"""Every core's copy of the shared file helpers stays the same code with the same bytes.

#412 R2 gave Harness its own copies and #498 slice 1 gave Benchmark its own, so no core
imports another for them. This test fails when one copy drifts from the others.
"""

import errno
import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

# Each helper name and the modules that hold a copy. #498 slice 3b added the Apps copy
# and slice 5 deleted the Infra one, so Harness, Benchmark and Apps hold the three.
COPIES = {
    "sha256": ("inferrsi.apps.artifacts", "inferrsi.harness.artifact_primitives",
               "inferrsi.benchmark.artifacts"),
    "write_json": ("inferrsi.apps.artifacts", "inferrsi.benchmark.artifacts"),
    "atomic_write_json": ("inferrsi.apps.artifacts", "inferrsi.harness.atomic_json",
                          "inferrsi.benchmark.artifacts"),
    "digest": ("inferrsi.apps.artifacts", "inferrsi.harness.artifact_primitives"),
    "file_lock": ("inferrsi.apps.artifacts", "inferrsi.harness.artifact_primitives"),
}
CONSTANTS = ("REPLACE_ATTEMPTS", "REPLACE_DELAY_SECONDS")
VALUE = {"b": [1.5, None, True, 1e-07, 1e16], "a": "非 ASCII", "nested": {"z": 0.1 + 0.2}}


@pytest.mark.parametrize("name", sorted(COPIES))
def test_every_copy_has_the_same_source(name):
    sources = {module: inspect.getsource(getattr(importlib.import_module(module), name))
               for module in COPIES[name]}
    assert len(set(sources.values())) == 1, sorted(sources)


def test_the_atomic_writers_share_their_retry_constants():
    for constant in CONSTANTS:
        values = {getattr(importlib.import_module(module), constant)
                  for module in COPIES["atomic_write_json"]}
        assert len(values) == 1, constant


def test_the_benchmark_copy_imports_no_other_inferrsi_module():
    import ast

    from inferrsi.benchmark import artifacts

    tree = ast.parse(inspect.getsource(artifacts))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                and (node.level or (node.module or "").split(".")[0] == "inferrsi")]
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import)
                and any(alias.name.split(".")[0] == "inferrsi" for alias in node.names)]


def _assert_writer_copies(tmp_path, name, value):
    written = set()
    filenames = []
    for index, module in enumerate(COPIES[name]):
        path = tmp_path / f"{index}.json"
        filenames.append(path.name)
        getattr(importlib.import_module(module), name)(path, value)
        written.add(path.read_bytes())
    assert len(written) == 1
    assert json.loads(written.pop()) == value
    assert sorted(path.name for path in tmp_path.iterdir()) == filenames


@pytest.mark.parametrize("name", ["write_json", "atomic_write_json"])
def test_every_writer_writes_the_same_bytes(tmp_path, name):
    output = tmp_path / "output"
    output.mkdir()
    _assert_writer_copies(output, name, VALUE)
    for module in COPIES[name]:
        with pytest.raises(ValueError):
            getattr(importlib.import_module(module), name)(tmp_path / "nan.json",
                                                           {"value": float("nan")})
        assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("value", [
    {}, [], {"verdict": "PASS", "values": [1.0, 2, None, True]},
    {"文本": "未转义 ✓", "nested": {"path": "C:\\runs\\a", "quote": "\"", "line": "a\nb"}},
    {"float": 1e-308, "large": 1e308, "negative": -0.0},
])
def test_harness_writer_bytes_equal_the_apps_writer(tmp_path, value):
    _assert_writer_copies(tmp_path, "atomic_write_json", value)


def test_every_digest_copy_reads_the_same_bytes(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(bytes(range(256)) * 9000)  # crosses the 1 MiB read block
    digests = {getattr(importlib.import_module(module), "sha256")(blob)
               for module in COPIES["sha256"]}
    assert len(digests) == 1
    for module in COPIES["sha256"]:
        with pytest.raises(FileNotFoundError):
            importlib.import_module(module).sha256(tmp_path / "missing.bin")


@pytest.mark.parametrize("module_name", COPIES["file_lock"])
@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM, errno.EBADF])
def test_windows_only_translates_locking_contention(tmp_path, monkeypatch, module_name, code):
    module = importlib.import_module(module_name)
    failure = OSError(code, os.strerror(code))
    locking = Mock(side_effect=[failure, None, None])
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(
        locking=locking, LK_NBLCK=2, LK_UNLCK=0,
    ))
    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt", fstat=os.fstat))

    path = tmp_path / ".session.lock"
    expected = BlockingIOError if code == errno.EACCES else type(failure)
    with pytest.raises(expected) as raised, module.file_lock(path):
        pytest.fail("acquired a lock after the OS refused it")
    assert locking.call_count == 1
    if code == errno.EACCES:
        assert raised.value.errno == errno.EAGAIN
        assert raised.value.__cause__ is failure
    else:
        assert raised.value is failure

    with module.file_lock(path):
        assert locking.call_count == 2
    assert locking.call_count == 3
    assert [call.args[1:] for call in locking.call_args_list] == [(2, 1), (2, 1), (0, 1)]


@pytest.mark.parametrize("module_name", COPIES["file_lock"])
def test_lock_preserves_errors_opening_the_file(tmp_path, module_name):
    acquire = importlib.import_module(module_name).file_lock
    with pytest.raises(FileNotFoundError), acquire(tmp_path / "missing" / ".session.lock"):
        pytest.fail("opened a lock in a missing directory")

    path = Mock(spec=Path)
    denied = PermissionError(errno.EACCES, "cannot open lock file")
    path.open.side_effect = denied
    with pytest.raises(PermissionError) as raised, acquire(path):
        pytest.fail("opened a lock without permission")
    assert raised.value is denied
