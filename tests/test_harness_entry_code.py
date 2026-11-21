"""Actual entry-byte capture is separate from preparation declaration checks."""

from hashlib import sha256

import pytest

from inferrsi.harness import entry_code


def test_capture_reads_actual_source_without_importing_or_executing_it(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir()
    source = b"raise RuntimeError('this worker must never be imported during binding')\n"
    (root / "fixture_worker.py").write_bytes(source)
    result = entry_code.capture_module(root, "fixture_worker", tmp_path / "captures")
    assert result.path.read_bytes() == source
    assert (result.sha256, result.size_bytes) == (sha256(source).hexdigest(), len(source))
    (root / "fixture_worker.py").write_bytes(b"changed after capture\n")
    assert result.path.read_bytes() == source


@pytest.mark.parametrize("module", ["missing", "package.worker", "../outside", "worker.py"])
def test_unresolvable_entry_has_no_actual_digest_or_capture(tmp_path, module):
    with pytest.raises(entry_code.EntryUnavailable):
        entry_code.capture_module(tmp_path, module, tmp_path / "captures")
    assert not (tmp_path / "captures").exists()


def test_existing_snapshot_is_preserved_instead_of_replaced(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir()
    (root / "worker.py").write_bytes(b"new bytes")
    captures = tmp_path / "captures"
    captures.mkdir()
    retained = captures / "worker.py"
    retained.write_bytes(b"already retained")
    with pytest.raises(entry_code.EntryCaptureError):
        entry_code.capture_module(root, "worker", captures)
    assert retained.read_bytes() == b"already retained"
