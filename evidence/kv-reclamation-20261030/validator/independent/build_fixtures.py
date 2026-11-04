"""Deterministic, evaluator-only fixture authoring; contains no candidate solution."""

from __future__ import annotations

import json
import random
from pathlib import Path

from oracle import evaluate


def alloc(request, generation, blocks, step, save=True):
    return {
        "op": "allocate",
        "request_id": request,
        "generation": generation,
        "blocks": blocks,
        "write_step": step,
        "save_required": save,
    }


def signal(op, request, generation=0):
    return {"op": op, "request_id": request, "generation": generation}


def advance(step):
    return {"op": "advance", "processed_step": step}


def make_trace(name, split, events, obligations):
    return {
        "id": name,
        "split": split,
        "obligations": obligations,
        "events": events,
        "expected": evaluate(events),
    }


def _seeded(seed, split):
    rng = random.Random(seed)
    events = [advance(0)]
    for generation in range(3):
        names = [f"r{i}" for i in range(4)]
        rng.shuffle(names)
        step_base = generation * 10
        for i, request in enumerate(names):
            blocks = [i * 3 + 2, i * 3]
            rng.shuffle(blocks)
            events.append(alloc(request, generation, blocks, step_base + 1 + i, i % 2 == 0))
        notifications = [
            signal(op, request, generation)
            for request in names
            for op in ("finish", "save_complete")
        ]
        rng.shuffle(notifications)
        for i, event in enumerate(notifications):
            events.append(event)
            if i in (1, 4):
                events.extend([dict(event), advance(step_base + (2 if i == 1 else 3))])
            if i == 3:
                events.extend(
                    [signal("finish", names[0], generation + 1),
                     signal("save_complete", names[1], generation + 1)]
                )
        events.extend([advance(step_base + 9), advance(step_base + 9)])
        if generation:
            events.extend([signal("finish", names[0], generation - 1),
                           signal("save_complete", names[1], generation - 1)])
    return make_trace(
        f"{split}_seed_{seed}", split, events,
        ["mixed_readiness", "stable_order", "reuse", "duplicates", "ignored_future"],
    )


def build():
    traces = []

    def add(name, split, events, *obligations):
        traces.append(make_trace(name, split, events, list(obligations)))

    add("dev_initial_empty", "development", [], "empty", "initial_state")
    add("dev_empty", "development", [advance(0), advance(0),
        signal("finish", "unknown"), signal("save_complete", "unknown")],
        "empty", "unknown", "duplicate_frontier")
    add("dev_requires_save", "development", [
        alloc("a", 0, [17, 3], 4), signal("finish", "a"), advance(4),
        signal("save_complete", "a"), signal("finish", "a"),
        signal("save_complete", "a"), advance(4)],
        "save_conjunct", "duplicate_free", "block_order")
    add("dev_requires_fence", "development", [
        alloc("b", 0, [6], 8), signal("save_complete", "b"),
        signal("finish", "b"), advance(7), advance(8)],
        "fence_conjunct", "inclusive_frontier", "save_before_finish")
    add("dev_requires_finish", "development", [advance(2), alloc("c", 0, [1], 2),
        signal("save_complete", "c"), advance(2), signal("finish", "c")],
        "finish_conjunct")
    add("dev_no_save", "development", [alloc("n", 0, [9, 0], 0, False),
        signal("finish", "n"), advance(0), signal("save_complete", "n")],
        "no_save_bypass", "initial_frontier")
    add("dev_order_and_nonblocking", "development", [
        alloc("head", 0, [8, 2], 9), alloc("middle", 0, [4, 7], 2),
        alloc("tail", 0, [5], 2), signal("finish", "head"),
        signal("finish", "middle"), signal("finish", "tail"),
        signal("save_complete", "tail"), signal("save_complete", "middle"),
        signal("save_complete", "head"), advance(2), advance(9)],
        "nonblocking_drain", "stable_order", "block_order", "drain_all")
    add("dev_reuse", "development", [advance(3), alloc("r", 1, [4], 3),
        signal("save_complete", "r", 1), signal("finish", "r", 1),
        signal("save_complete", "r", 2), alloc("r", 2, [4], 3),
        signal("finish", "r", 2), signal("save_complete", "r", 1),
        signal("save_complete", "r", 2)],
        "reuse", "stale_identity", "ignored_future")
    add("dev_invalid_atomic", "development", [advance(4), alloc("a", 0, [1], 4),
        {**signal("save_complete", "a"), "extra": True}, signal("finish", "a"),
        signal("save_complete", "a"), {**alloc("b", 2, [2], 4), "extra": 0},
        alloc("b", 1, [2], 4, False), advance(3), signal("finish", "b", 1)],
        "schema_validation", "atomic_notification", "atomic_history", "monotone_frontier")

    add("grader_cross_request", "grader", [advance(5), alloc("x", 4, [2], 5),
        alloc("y", 4, [3], 5), signal("finish", "x", 4),
        signal("save_complete", "y", 4), signal("save_complete", "x", 4),
        signal("finish", "y", 4)], "full_identity", "save_conjunct", "finish_conjunct")
    add("grader_unknown_preallocation", "grader", [
        signal("finish", "new", 7), signal("save_complete", "new", 7), advance(0),
        alloc("new", 7, [4], 0), signal("finish", "new", 7),
        signal("save_complete", "new", 7)], "ignored_future", "full_identity")
    add("grader_reused_blocks", "grader", [advance(8), alloc("old", 1, [11, 5], 8),
        signal("finish", "old", 1), signal("save_complete", "old", 1),
        alloc("new", 1, [5, 11], 8), signal("finish", "old", 1),
        signal("save_complete", "old", 1), signal("finish", "new", 1),
        signal("save_complete", "new", 1)], "reused_blocks", "stale_identity", "block_order")
    add("grader_generation_rules", "grader", [advance(0), alloc("g", 4, [0], 0, False),
        alloc("g", 5, [1], 0, False), signal("finish", "g", 4),
        alloc("g", 4, [0], 0, False), alloc("g", 3, [0], 0, False),
        alloc("g", 9, [0], 0, False), signal("finish", "g", 4),
        signal("finish", "g", 9)], "generation_monotonicity", "active_request_conflict")
    add("grader_atomic_block_history", "grader", [advance(5), alloc("owner", 0, [10], 5),
        alloc("rejected", 9, [12, 10], 5, False),
        alloc("rejected", 1, [12], 5, False), signal("finish", "rejected", 1),
        signal("finish", "owner"), signal("save_complete", "owner")],
        "active_block_conflict", "atomic_allocation", "atomic_history")
    add("grader_stable_survivors", "grader", [advance(0),
        alloc("a", 0, [31, 20], 0), alloc("b", 0, [2], 0),
        alloc("c", 0, [7, 6], 0), alloc("d", 0, [8], 0),
        signal("finish", "d"), signal("finish", "b"),
        signal("save_complete", "d"), signal("save_complete", "b"),
        signal("finish", "a"), signal("finish", "c"),
        signal("save_complete", "c"), signal("save_complete", "a")],
        "stable_survivor_order", "nonblocking_drain")
    add("grader_empty_id_and_large_values", "grader", [advance(2**63),
        alloc("", 2**63, [2**64, 0], 2**63, False),
        signal("finish", "", 2**63), alloc("", 2**63 + 1, [0], 2**63, False),
        signal("finish", "", 2**63 + 1)], "empty_request_id", "unbounded_integers", "reuse")
    add("grader_frontier_atomic", "grader", [advance(12), advance(11),
        alloc("f", 0, [0], 12, False), signal("finish", "f"), advance(12)],
        "atomic_frontier", "monotone_frontier", "inclusive_frontier")

    # Every malformed call is followed by valid calls that expose leaked state.
    malformed = [None, [], "advance", {}, {"op": "bogus"}, {"op": []},
                 {"op": "advance"}, {"op": "advance", "processed_step": 2, "extra": 0}]
    for bad in (-1, True, False, 1.0, "1", None, [], {}):
        malformed.append({"op": "advance", "processed_step": bad})
    for op in ("finish", "save_complete"):
        malformed.extend([
            {"op": op, "request_id": "target"},
            {"op": op, "generation": 0},
            {"op": op, "request_id": "target", "generation": 0, "extra": 1},
            {"op": op, "request_id": 1, "generation": 0},
        ])
        for bad in (-1, True, 0.0, None):
            malformed.append({"op": op, "request_id": "target", "generation": bad})
    base = alloc("rejected", 9, [9], 1)
    for field, bad_values in {
        "request_id": [None, 1, True],
        "generation": [-1, True, 0.0, "0"],
        "blocks": [[], [1, 1], [-1], [True], [0.0], [None], "1", {}, None],
        "write_step": [-1, True, 1.0, None],
        "save_required": [0, 1, "true", None],
    }.items():
        for bad in bad_values:
            malformed.append({**base, field: bad})
    for missing in tuple(base):
        malformed.append({key: value for key, value in base.items() if key != missing})
    malformed.append({**base, "extra": 1})
    for i, bad in enumerate(malformed):
        add(f"grader_invalid_{i:02d}", "grader", [advance(1),
            alloc("target", 0, [1], 1), bad, signal("finish", "target"),
            signal("save_complete", "target"), alloc("rejected", 1, [9], 1, False),
            signal("finish", "rejected", 1)],
            "schema_validation", "atomic_notification", "atomic_allocation", "atomic_history")

    for seed in (11, 23):
        traces.append(_seeded(seed, "development"))
    for seed in (37, 53, 71, 89, 107, 127):
        traces.append(_seeded(seed, "grader"))
    return {"schema": "synthetic-kv-reclamation-traces-v1", "traces": traces}


if __name__ == "__main__":
    destination = Path(__file__).with_name("fixtures.json")
    destination.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
