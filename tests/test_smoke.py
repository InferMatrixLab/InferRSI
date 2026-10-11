"""Draft-lane smoke tests (CPU, no GPU)."""

import json

from rsi_scaffold import __version__
from rsi_scaffold.evidence_paths import EVIDENCE_SEGMENTS, evidence_subpaths
from rsi_scaffold.runspec import RunSpec


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_runspec_round_trip() -> None:
    spec = RunSpec(
        repo="example/repo",
        revision="abc123",
        backend="cpu",
        device="local",
        model="tiny",
        scenario="smoke",
    )
    payload = spec.to_dict()
    restored = RunSpec.from_dict(payload)
    assert restored == spec
    assert json.dumps(payload)


def test_evidence_segments() -> None:
    paths = evidence_subpaths(__import__("pathlib").Path("/tmp/campaign"))
    assert set(paths) == set(EVIDENCE_SEGMENTS)
