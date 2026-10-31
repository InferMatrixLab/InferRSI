"""Independent oracle anchors and sensitivity checks, CPU-only pytest style."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from build_fixtures import build
from oracle import evaluate
from verifier import compare, expected_actual, load_traces, observe_trusted, verify_observations

ROOT = Path(__file__).parent
TRACES = load_traces()
BY_ID = {trace["id"]: trace for trace in TRACES}
CONTROLS = json.loads((ROOT / "control_spec.json").read_text(encoding="utf-8"))


def test_fixture_generation_is_byte_reproducible():
    assert json.dumps(build(), indent=2, sort_keys=True) + "\n" == (
        ROOT / "fixtures.json"
    ).read_text(encoding="utf-8")


def test_splits_and_obligations_are_explicit():
    development = load_traces("development")
    grader = load_traces("grader")
    assert development and grader
    assert len(BY_ID) == len(TRACES)
    assert {t["id"] for t in development}.isdisjoint(t["id"] for t in grader)
    assert all(t["obligations"] for t in TRACES)
    assert all(len(t["events"]) == len(t["expected"]) for t in TRACES)


@pytest.mark.parametrize("trace", TRACES, ids=lambda trace: trace["id"])
def test_positive_frozen_replay_control(trace):
    assert compare(trace, deepcopy(expected_actual(trace)))
    assert verify_observations(trace, deepcopy(expected_actual(trace)))["passed"]


@pytest.mark.parametrize("control", CONTROLS["negative"], ids=lambda control: control["id"])
def test_negative_replay_control_is_rejected(control):
    trace = BY_ID[control["trace"]]
    actual = deepcopy(expected_actual(trace))
    target = actual["observations"][control["index"]]
    if "error" in control:
        target.pop("reclaimed", None)
        target["error"] = control["error"]
    if "reclaimed" in control:
        target.pop("error", None)
        target["reclaimed"] = control["reclaimed"]
    if "pending" in control:
        target["pending"] = control["pending"]
    assert not compare(trace, actual)
    result = verify_observations(trace, actual)
    assert not result["passed"]
    assert result["event_index"] == control["index"]


def test_oracle_save_fence_and_finish_literal_anchors():
    save = BY_ID["dev_requires_save"]["expected"]
    assert save[2] == {"reclaimed": [], "pending": [["a", 0, [17, 3]]]}
    assert save[3] == {"reclaimed": [17, 3], "pending": []}
    assert save[4:] == [{"reclaimed": [], "pending": []}] * 3
    fence = BY_ID["dev_requires_fence"]["expected"]
    assert fence[3] == {"reclaimed": [], "pending": [["b", 0, [6]]]}
    assert fence[4] == {"reclaimed": [6], "pending": []}
    finish = BY_ID["dev_requires_finish"]["expected"]
    assert finish[3] == {"reclaimed": [], "pending": [["c", 0, [1]]]}
    assert finish[4] == {"reclaimed": [1], "pending": []}
    assert BY_ID["dev_no_save"]["expected"][2] == {"reclaimed": [9, 0], "pending": []}


def test_oracle_order_and_reuse_literal_anchors():
    order = BY_ID["dev_order_and_nonblocking"]["expected"]
    assert order[9] == {"reclaimed": [4, 7, 5], "pending": [["head", 0, [8, 2]]]}
    assert order[10] == {"reclaimed": [8, 2], "pending": []}
    reuse = BY_ID["dev_reuse"]["expected"]
    assert reuse[3] == {"reclaimed": [4], "pending": []}
    assert reuse[7] == {"reclaimed": [], "pending": [["r", 2, [4]]]}
    assert reuse[8] == {"reclaimed": [4], "pending": []}
    unknown = BY_ID["grader_unknown_preallocation"]["expected"]
    assert unknown[4] == {"reclaimed": [], "pending": [["new", 7, [4]]]}
    assert unknown[5] == {"reclaimed": [4], "pending": []}


def test_invalid_calls_are_atomic_with_follow_through():
    for trace in TRACES:
        if trace["id"].startswith("grader_invalid_"):
            assert trace["expected"][2] == {
                "error": "ValueError", "pending": [["target", 0, [1]]]
            }
            assert trace["expected"][3] == {
                "reclaimed": [], "pending": [["target", 0, [1]]]
            }
            assert trace["expected"][4] == {"reclaimed": [1], "pending": []}
            assert trace["expected"][6] == {"reclaimed": [9], "pending": []}
    frontier = BY_ID["grader_frontier_atomic"]["expected"]
    assert frontier[1] == {"error": "ValueError", "pending": []}
    assert frontier[3] == {"reclaimed": [0], "pending": []}
    history = BY_ID["grader_atomic_block_history"]["expected"]
    assert history[2] == {"error": "ValueError", "pending": [["owner", 0, [10]]]}
    assert history[4] == {"reclaimed": [12], "pending": [["owner", 0, [10]]]}


def test_rejected_history_is_indistinguishable_from_omission():
    for trace in TRACES:
        accepted = [event for event, observation in zip(trace["events"], trace["expected"])
                    if "error" not in observation]
        accepted_observations = [o for o in trace["expected"] if "error" not in o]
        assert evaluate(accepted) == accepted_observations


def test_seeded_traces_are_legal_and_fully_drained():
    seeded = [t for t in TRACES if "_seed_" in t["id"]]
    assert seeded
    for trace in seeded:
        assert not any("error" in observation for observation in trace["expected"])
        assert trace["expected"][-1]["pending"] == []
        # Four two-block leases, reused over three generations, each returned once.
        assert sum(len(o["reclaimed"]) for o in trace["expected"]) == 24


def test_trusted_adapter_uses_exact_runtime_types_and_fresh_instances():
    trace = BY_ID["dev_requires_save"]

    class Replay:
        def __init__(self):
            self.index = -1

        def apply(self, event):
            self.index += 1
            assert event == trace["events"][self.index]
            return list(trace["expected"][self.index]["reclaimed"])

        def pending(self):
            return [(r, g, tuple(b)) for r, g, b in trace["expected"][self.index]["pending"]]

    assert compare(trace, observe_trusted(Replay, trace))
    assert compare(trace, observe_trusted(Replay, trace))

    class WrongPendingType(Replay):
        def pending(self):
            return trace["expected"][self.index]["pending"]

    assert not compare(trace, observe_trusted(WrongPendingType, trace))

    class WrongReclaimedType(Replay):
        def apply(self, event):
            return tuple(super().apply(event))

    assert not compare(trace, observe_trusted(WrongReclaimedType, trace))


def test_envelope_and_numeric_types_are_not_silently_coerced():
    trace = BY_ID["dev_requires_finish"]
    for replacement in ([True], [1.0], (1,)):
        actual = deepcopy(expected_actual(trace))
        actual["observations"][4]["reclaimed"] = replacement
        # JSON cannot distinguish tuple/list; the runtime adapter enforces that distinction.
        if isinstance(replacement, tuple):
            continue
        assert not compare(trace, actual)
    actual = deepcopy(expected_actual(trace))
    actual["extra"] = 0
    assert not compare(trace, actual)
    actual = deepcopy(expected_actual(trace))
    actual["observations"].pop()
    assert not compare(trace, actual)
    actual = deepcopy(expected_actual(trace))
    actual["pending"] = [["ghost", 0, [1]]]
    assert not compare(trace, actual)


def test_frozen_manifest_hashes_match():
    manifest = json.loads((ROOT / "FREEZE.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
