"""Tiny independent-oracle checks plus literal modulo-boundary anchors."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from benchmark import benchmark_expected
from source_workload import workload

ROOT = Path(__file__).parent


@pytest.mark.parametrize("count", [1, 2, 3, 5])
def test_tiny_workloads_match_original_temporal_oracle(count):
    oracle_path = Path(os.environ.get(
        "KV_FROZEN_ORACLE", ROOT.parent / "kv-reclamation-independent-verifier" / "oracle.py"
    ))
    spec = importlib.util.spec_from_file_location("original_frozen_oracle", oracle_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # All tiny leases are reclaimed by frontier count-1. Omit only the remaining
    # no-op frontiers from the expensive temporal reference, not from production.
    events = workload(count)[: 3 * count + count]
    expected = module.evaluate(events)
    actual = benchmark_expected(count)
    assert actual["observations"][: len(events)] == [
        {"reclaimed": observation["reclaimed"]} for observation in expected
    ]
    assert expected[-1]["pending"] == actual["pending"] == []
    assert actual["observations"][len(events) :] == [{"reclaimed": []}] * (257 - count)


def test_count_259_literal_modulo_boundary():
    result = benchmark_expected(259)
    assert len(result["observations"]) == 3 * 259 + 257
    assert result["observations"][: 3 * 259] == [{"reclaimed": []}] * (3 * 259)
    advances = result["observations"][3 * 259 :]
    assert advances[0] == {"reclaimed": [0, 1, 514, 515]}
    assert advances[1] == {"reclaimed": [2, 3, 516, 517]}
    assert advances[2] == {"reclaimed": [4, 5]}
    assert advances[255] == {"reclaimed": [510, 511]}
    assert advances[256] == {"reclaimed": [512, 513]}
    assert result["pending"] == []
    returned = [block for item in advances for block in item["reclaimed"]]
    assert len(returned) == len(set(returned)) == 518
    assert sorted(returned) == list(range(518))


@pytest.mark.parametrize("count", [1, 256, 257, 258, 514, 515, 1029])
def test_exact_partition_without_state_simulation(count):
    result = benchmark_expected(count)
    assert len(result["observations"]) == len(workload(count)) == 3 * count + 257
    assert all(not row["reclaimed"] for row in result["observations"][: 3 * count])
    returned = []
    for frontier, observation in enumerate(result["observations"][3 * count :]):
        blocks = observation["reclaimed"]
        assert len(blocks) % 2 == 0
        indices = blocks[::2]
        assert indices == sorted(indices)
        assert all(block % 2 == 0 and (block // 2) % 257 == frontier for block in indices)
        assert blocks[1::2] == [block + 1 for block in indices]
        returned.extend(blocks)
    assert sorted(returned) == list(range(2 * count))
    assert result["pending"] == []


@pytest.mark.parametrize("count", [0, -1, True, False, 1.0, "1", None])
def test_count_validation_matches_pinned_workload(count):
    with pytest.raises(ValueError):
        benchmark_expected(count)
    with pytest.raises(ValueError):
        workload(count)


def test_supplemental_freeze_hashes():
    manifest = json.loads((ROOT / "supplemental-freeze.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
