"""Paid-state continuation sampling, isolated from natural GVO actor groups."""

import copy
import math
import time
from dataclasses import asdict, replace

from .records.artifact_primitives import digest
from .search_records import decode, encode
from .vats import Action, Search


def continue_from(search, step_index, action_key, search_id, *, copy_cap_ms, seed):
    """Clone a retained paid decision state and force exactly its first action.

    Original observations are explicit imports with their physical execution IDs.
    Copying is charged; all suffix edits/checks use ordinary WorkControl claims.
    No holdout or unobserved outcome is used. The entire suffix is Scorer-only.
    """
    search.control.recover_unstarted(search.campaign)
    doc, source, _ = search.read()
    if doc["final_claim"] is not None or source["status"] != "complete":
        raise ValueError("Continuation source must be a completed development search")
    if (
        source["forced"]
        or type(step_index) is not int
        or not 0 <= step_index < len(source["trace"])
    ):
        raise ValueError("Select a retained natural paid decision state")
    step = source["trace"][step_index]
    actions = [Action(**raw) for raw in step["menu"]]
    selected = next((i for i, action in enumerate(actions) if action.key == action_key), None)
    if selected is None:
        raise ValueError("Forced action is outside the original paid menu")
    action = actions[selected]
    fork = Search(
        search.control, search.campaign, search_id, search.snapshot, search.settings, search.adapter
    )
    if search_id in doc["state"]["searches"]:
        _, retained, _ = fork.read()
        if retained.get("continuation") != {
            "source": search.search_id,
            "step": step_index,
            "action": action_key,
            "paid_state": digest(step["paid_state"]),
            "seed": seed,
        }:
            raise ValueError("Continuation identity already belongs to another paid state")
        return fork.run()
    operation = "copy-" + search_id
    search.control.claim(
        search.campaign,
        doc["revision"],
        operation,
        category="continuation_copy",
        cap_ms=copy_cap_ms,
        binding={"search": search_id, "source": search.search_id, "step": step_index},
    )
    search.control.launch(search.campaign, operation)
    started = time.monotonic()
    current = decode(copy.deepcopy(step["paid_state"]))
    # Change the receiving scope, retaining immutable physical source identities.
    imports = {
        attempt.attempt_id: replace(
            attempt, search_id=search_id, attempt_id=f"{search_id}-import-{attempt.attempt_id}"
        )
        for attempt in current.attempts
    }
    current = replace(
        current,
        contract=replace(current.contract, search_id=search_id),
        attempts=tuple(imports[a.attempt_id] for a in current.attempts),
        receipts=tuple(replace(r, attempt=imports[r.attempt.attempt_id]) for r in current.receipts),
    )
    record = copy.deepcopy(source)
    forced_step = copy.deepcopy(step)
    now = time.time()
    forced_step.update(
        action=asdict(action),
        features=step["vectors"][selected],
        forced=True,
        draft_choices=[],
        at=now,
    )
    record.update(
        tree=encode(current),
        seed=seed,
        forced=True,
        trace=[forced_step],
        status="active",
        pending=None,
        spent_ms=step["spent_before"],
        started_at=now,
        elapsed_ms=0,
        draft_attempts=step["draft_attempts"],
        initial_gain=step["gain_before"],
        initial_spent_ms=step["spent_before"],
        continuation={
            "source": search.search_id,
            "step": step_index,
            "action": action_key,
            "paid_state": digest(step["paid_state"]),
            "seed": seed,
        },
        active_action=None
        if action.kind == "accept"
        else {
            "action": asdict(action),
            "cursor": 0,
            "last_child": None,
            "jobs": step["jobs"],
        },
    )
    record.pop("gain", None)
    record.pop("stop_reason", None)
    elapsed = max(1, math.ceil((time.monotonic() - started) * 1000))

    def commit(state):
        if search_id in state["searches"]:
            raise ValueError("Continuation search was concurrently created")
        state["searches"][search_id] = record
        return state

    search.control.settle(
        search.campaign,
        operation,
        {"record": record},
        actual_ms=elapsed,
        cleanup_verified=True,
        transition=commit,
    )
    if action.kind == "accept":
        return fork.finish("forced_accept")
    return fork.run()


def paired_targets(records, *, expense_weight, elapsed_weight):
    """Produce differences only for two settled continuations of the same paid state."""
    from .gvo import suffix_examples

    if len(records) != 2:
        raise ValueError("A matched comparison needs exactly two continuations")
    left, right = records
    keys = ("source", "step", "paid_state", "seed")
    if (
        not all(r["forced"] and r.get("continuation") for r in records)
        or any(left["continuation"][k] != right["continuation"][k] for k in keys)
        or any(left[k] != right[k] for k in ("snapshot", "settings", "adapter"))
        or left["continuation"]["action"] == right["continuation"]["action"]
    ):
        raise ValueError("Scorer pair must share a paid state and frozen continuation policy")
    first = [
        suffix_examples(r, expense_weight=expense_weight, elapsed_weight=elapsed_weight)[0]
        for r in records
    ]
    return (first[0][0], first[1][0], first[0][1] - first[1][1])
