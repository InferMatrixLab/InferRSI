"""Stage boundaries inside the existing service campaign lock and round ledger."""

from .. import evaluator, executor
from ..records import service_io


def initialize(plan):
    settings = plan["evaluation_settings"]
    return {
        "stage_id": settings["staged_evaluation"]["initial_stage_id"],
        "stage_index": 0,
        "stage_protocol": "frozen/evaluation.json",
        "stage_transitions": plan["stage_transitions"],
    }


def settings_for(root, plan, row):
    settings = service_io.read(service_io.safe_path(root, row["stage_protocol"]))
    if row.get("settings") is not None and row["settings"] != settings:
        raise ValueError("Retained stage protocol differs from the frozen descriptor")
    return {**plan, "evaluation_settings": settings, "selection": {"ranking": settings["ranking"]}}


def active_plan(root, plan, state):
    if "stage_id" not in state:
        if plan.get("stage_transitions"):
            raise ValueError("Missing staged campaign control")
        return plan
    rows = state["stage_transitions"]
    count = len(plan["stage_transitions"])
    if rows[:count] != plan["stage_transitions"]:
        raise ValueError("Mandatory stages differ from the frozen plan")
    index = state["stage_index"]
    if type(index) is not int or not 0 <= index <= len(rows):
        raise ValueError("Invalid active stage index")
    committed = [
        a
        for a in state["attempts"]
        if a.get("switch_target") and a["assessment"]["verdict"] == "PASS"
    ]
    expected_path = committed[-1]["stage_protocol"] if committed else "frozen/evaluation.json"
    if [a["switch_target"] for a in committed] != [
        row["stage_id"] for row in rows[:index]
    ] or state["stage_protocol"] != expected_path:
        raise ValueError("Active stage differs from committed switch evidence")
    row = (
        rows[index - 1]
        if index
        else {
            "stage_id": plan["evaluation_settings"]["staged_evaluation"]["initial_stage_id"],
            "settings": plan["evaluation_settings"],
        }
    )
    if (
        state["stage_id"] != row["stage_id"]
        or state["protocol_id"] != row["settings"]["protocol_id"]
    ):
        raise ValueError("Active stage does not match the frozen plan")
    return settings_for(root, plan, {**row, "stage_protocol": state["stage_protocol"]})


def next_stage(state):
    rows = state.get("stage_transitions", [])
    index = state.get("stage_index", 0)
    return rows[index] if index < len(rows) else None


def due(state):
    row = next_stage(state)
    return (
        row
        if row and sum(r["terminal"] for r in state["rounds"]) >= row["after_completed_rounds"]
        else None
    )


def append(root, plan, state, path):
    if next_stage(state) or not state["accepted_attempt_ids"] or not state.get("best"):
        raise ValueError("Append requires a selected candidate under the formal protocol")
    protocol = service_io.safe_path(root, "frozen/protocol")
    row = executor.service_stage_descriptor(
        service_io.read(path), plan["evaluation_settings"], protocol, appended=True,
        parent_only=plan.get("stage_parent_only", False),
    )
    ids = {r["stage_id"] for r in state["stage_transitions"]}
    ids.update(a["stage_id"] for a in state["attempts"])
    if row["stage_id"] in ids:
        raise ValueError("Duplicate appended stage ID")
    row["after_completed_rounds"] = sum(r["terminal"] for r in state["rounds"])
    return row


def stage_scope(plan, index):
    formal = len(plan["stage_transitions"])
    if index < formal:
        return "iteration"
    return "formal" if index == formal else "additional_constraints"


def binding(state, plan):
    if "stage_id" not in state:
        return {}
    return {
        "stage_id": state["stage_id"],
        "stage_protocol": state["stage_protocol"],
        "protocol_id": plan["evaluation_settings"]["protocol_id"],
        "stage_scope": stage_scope(plan, state["stage_index"]),
    }


def report(plan, state, remaining):
    if "stage_id" not in state:
        return {}
    row = due(state)
    last = state["final"]
    current = (
        last
        if last
        and not next_stage(state)
        and last["stage_id"] == state["stage_id"]
        and last["reference_epoch"] == state["reference_epoch"]
        and last["assessment"]["verdict"] in ("PASS", "FAIL")
        and state["state"] == "completed"
        and not state.get("terminal_inconclusive")
        and not last.get("admission_failure")
        else None
    )
    return {
        **binding(state, plan),
        "pending_stage": row["stage_id"] if row else None,
        "stage_outcome": (
            "INCONCLUSIVE"
            if state.get("terminal_inconclusive")
            else current["assessment"]["verdict"]
            if current
            else None
        ),
        "stage_switch_reason": (row.get("reason", "planned_round_boundary") if row else None),
        "stage_completed_rounds": sum(
            r["terminal"] for r in state["rounds"] if r.get("stage_id") == state["stage_id"]
        ),
        "stage_trigger_round": row["after_completed_rounds"] if row else None,
        "remaining_rounds": plan["round_limit"] - len(state["rounds"]),
        "remaining_search_seconds": max(0, remaining - plan["final_reserve_seconds"]),
        "stage_final": current["assessment"] if current else None,
        "stage_final_attempt_id": current["attempt_id"] if current else None,
        "initial_reference": state["initial_reference"],
        "comparison_parent": state["comparison_parent"],
    }


def references(root, plan, state, pending, *, deadline=None):
    """With no deadline, reconcile retained child runs only. Never launch on recovery."""
    import time

    if pending.get("switch_target"):
        row = next_stage(state)
        plan = settings_for(root, plan, {**pending, "settings": row["settings"]})
    sources = [("parent", pending["refresh_parent"])]
    if "refresh_initial" in pending:
        sources.insert(0, ("baseline", pending["refresh_initial"]))
    references, runs = [], []
    complete_cleanup = True
    previous = [
        a for a in reversed(state["attempts"])
        if pending.get("switch_id") and a.get("switch_id") == pending["switch_id"]
    ]
    for index, (label, source) in enumerate(sources):
        if index and all(
            source.get(k) == sources[0][1].get(k) for k in ("revision", "source_repo", "conditions")
        ):
            references.append(references[0])
            break
        child = service_io.safe_path(root, pending["path"] + "/" + label)
        # An admitted child owns this slot until its cleanup and receipts are reconciled.
        for attempt in [pending] if child.exists() else [*previous, pending]:
            relative = attempt["path"] + "/" + label
            directory = service_io.safe_path(root, relative)
            job = {
                **pending,
                "path": relative,
                "revision": source["revision"],
                "source_repo": source["source_repo"],
                "candidate_id": source["candidate_id"],
                "attempt_id": attempt["attempt_id"] + "-" + label,
                "role": "baseline",
                "reference_kind": "stage_" + label,
                "parent": None,
                "initial": references[0] if index else None,
            }
            if directory.exists():
                try:
                    result = service_io.read(
                        service_io.safe_path(directory, "execution/execution.json")
                    )
                except (ValueError, OSError):
                    result = {}
            elif attempt is pending and deadline is not None and time.time() < deadline:
                directory.mkdir()
                result = executor.execute_service_attempt(root, directory, plan, job, deadline)
            else:
                continue
            verified, valid = evaluator.service_reference_result(root, directory, plan, job, result)
            if valid:
                references.append(evaluator.service_choice(job, result))
                runs.append(result)
                break
            if attempt is pending:
                complete_cleanup = verified
                runs.append(result)
        else:
            break

    if (len(sources) == 2 and not references
            and service_io.safe_path(root, pending["path"] + "/parent").exists()):
        complete_cleanup = False
    complete = len(references) == len(sources)
    return {
        "assessment": evaluator.service_assessment(
            "PASS" if complete else "INCONCLUSIVE",
            "references_refreshed_not_candidate_acceptance"
            if complete
            else "stage_references_incomplete",
            eligible=False,
        ),
        "references": references,
        "runs": runs,
        "cleanup_verified": complete_cleanup,
        "elapsed_seconds": max(0, time.time() - pending["started_at"]),
    }
