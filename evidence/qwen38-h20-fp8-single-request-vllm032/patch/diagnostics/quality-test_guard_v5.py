# ruff: noqa: E402
"""Synthetic source manifest coverage; no real dataset or sandbox execution."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, os.environ.get("QUALITY_SOURCE_DIR", str(ROOT.parent / "quality-source-v5")))
import prepare_guard

sys.path.append(os.environ["QUALITY_REFERENCE_TEST_DIR"])
import pytest
from protocol import canonical, sha
from test_prepare_guard import fixture


def test_complete_manifest_includes_provenance(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    observed = prepare_guard.snapshot(args)
    assert len(observed["tools"]) == 9
    assert "sandbox_provenance.py" in observed["tools"]


def test_old_eight_file_manifest_rejected(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    manifest = json.loads(args.source_manifest.read_bytes())
    manifest["files"] = [
        item for item in manifest["files"] if item["path"] != "sandbox_provenance.py"
    ]
    args.source_manifest.write_bytes(canonical(manifest))
    args.source_manifest_sha256 = sha(args.source_manifest.read_bytes())
    with pytest.raises(ValueError, match="complete preparation tool set"):
        prepare_guard.snapshot(args)


def test_provenance_source_drift_rejected(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    (args.source_dir / "sandbox_provenance.py").write_bytes(b"changed synthetic source")
    with pytest.raises(ValueError, match="preparation source changed"):
        prepare_guard.snapshot(args)
