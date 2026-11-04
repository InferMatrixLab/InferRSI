"""Trusted history-based specification; never provide this module to candidates.

This is deliberately not an optimized queue or a candidate Reclaimer class.
Each observation is re-derived from accepted history using temporal predicates.
"""

from __future__ import annotations

from copy import deepcopy

_KEYS = {
    "allocate": {"op", "request_id", "generation", "blocks", "write_step", "save_required"},
    "finish": {"op", "request_id", "generation"},
    "save_complete": {"op", "request_id", "generation"},
    "advance": {"op", "processed_step"},
}


def _uint(value):
    return type(value) is int and value >= 0


def _leases(history):
    """Return allocations and earliest satisfying prefix, not an incremental queue."""
    leases = []
    for birth, allocation in enumerate(history):
        if allocation["op"] != "allocate":
            continue
        identity = (allocation["request_id"], allocation["generation"])
        reclaimed_at = None
        for end in range(birth, len(history)):
            prefix = history[: end + 1]
            frontier = max(
                (e["processed_step"] for e in prefix if e["op"] == "advance"), default=-1
            )
            matching = [
                e["op"]
                for e in history[birth + 1 : end + 1]
                if e["op"] in {"finish", "save_complete"}
                and (e["request_id"], e["generation"]) == identity
            ]
            if (
                "finish" in matching
                and (not allocation["save_required"] or "save_complete" in matching)
                and allocation["write_step"] <= frontier
            ):
                reclaimed_at = end
                break
        leases.append((birth, allocation, reclaimed_at))
    return leases


def _validate(event, history):
    if not isinstance(event, dict):
        raise ValueError("event must be a dictionary")
    op = event.get("op")
    if not isinstance(op, str) or op not in _KEYS or set(event) != _KEYS[op]:
        raise ValueError("invalid operation or key set")
    if op in {"allocate", "finish", "save_complete"}:
        if not isinstance(event["request_id"], str) or not _uint(event["generation"]):
            raise ValueError("invalid identity")
    if op == "advance":
        step = event["processed_step"]
        old = max((e["processed_step"] for e in history if e["op"] == op), default=-1)
        if not _uint(step) or step < old:
            raise ValueError("invalid frontier")
    if op != "allocate":
        return
    blocks = event["blocks"]
    if (
        not isinstance(blocks, list)
        or not blocks
        or any(not _uint(block) for block in blocks)
        or len(set(blocks)) != len(blocks)
        or not _uint(event["write_step"])
        or type(event["save_required"]) is not bool
    ):
        raise ValueError("invalid allocation fields")
    leases = _leases(history)
    for _, old, reclaimed_at in leases:
        if old["request_id"] == event["request_id"]:
            if reclaimed_at is None or event["generation"] <= old["generation"]:
                raise ValueError("request already active or generation not increasing")
        if reclaimed_at is None and set(blocks).intersection(old["blocks"]):
            raise ValueError("blocks already active")


def evaluate(events):
    """Produce JSON-compatible event observations, including atomic ValueError calls."""
    history = []
    observations = []
    for event in events:
        try:
            _validate(event, history)
        except ValueError:
            observation = {"error": "ValueError"}
        else:
            history.append(deepcopy(event))
            observation = {
                "reclaimed": [
                    block
                    for _, allocation, reclaimed_at in _leases(history)
                    if reclaimed_at == len(history) - 1
                    for block in allocation["blocks"]
                ]
            }
        observation["pending"] = [
            [a["request_id"], a["generation"], list(a["blocks"])]
            for _, a, reclaimed_at in _leases(history)
            if reclaimed_at is None
        ]
        observations.append(observation)
    return observations
