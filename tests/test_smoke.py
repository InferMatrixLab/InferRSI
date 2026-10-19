"""Draft-lane smoke tests (CPU, no GPU)."""

import json

import pytest

from inferrsi import __version__
from inferrsi.evidence_paths import EVIDENCE_SEGMENTS, evidence_subpaths
from inferrsi.runspec import RunSpec


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


def test_executable_runspec_json_round_trip_keeps_argv_and_snapshot_fields() -> None:
    spec = RunSpec(
        repo="example/repo",
        revision="abc123",
        device="local",
        executor="external",
        snapshot_id="fixture",
        baseline_command=("python", "baseline.py"),
        candidate_command=("python", "candidate.py"),
        device_ids=("0",),
    )
    assert RunSpec.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec


def test_runspec_does_not_convert_command_strings_into_character_argv() -> None:
    with pytest.raises(ValueError, match="sequence"):
        RunSpec.from_dict({"repo": "example/repo", "baseline_command": "python baseline.py"})
