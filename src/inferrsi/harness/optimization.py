"""Shared, Agent-driven optimization lifecycle for project and packaged tasks."""

import hashlib
import json
import math
import time
import uuid
from pathlib import Path

from ..infra.artifacts import atomic_write_json, digest, file_lock, sha256
from . import candidates
from .usage import normalize_usage, usage_totals


def _locked(root):
    return file_lock(root / ".session.lock")


def initialize(root: Path, plan: dict) -> dict:
    if type(plan["round_limit"]) is not int or plan["round_limit"] < 1:
        raise ValueError("rounds must be a positive integer")
    if (type(plan["max_seconds"]) not in (int, float)
            or not math.isfinite(plan["max_seconds"]) or plan["max_seconds"] <= 0):
        raise ValueError("max-minutes must be finite and positive")
    if (root / "state.json").exists():
        raise ValueError("Session already initialized")
    if plan["round_mode"] not in ("exact", "up_to"):
        raise ValueError("Unknown round policy")
    if plan["selection"]["direction"] not in ("minimize", "maximize"):
        raise ValueError("Unknown selection direction")
    reserve = plan["final_reserve_seconds"]
    if type(reserve) not in (int, float) or not 0 < reserve < plan["max_seconds"]:
        raise ValueError("Final reserve must fit within the total time budget")
    started = time.time()
    plan["baseline_sha256"] = candidates.identity(root / plan["baseline_path"])
    atomic_write_json(root / "plan.json", plan)
    state = {
        "schema_version": 1, "plan_digest": digest(plan), "started_at": started,
        "deadline": started + plan["max_seconds"], "state": "active", "rounds": [],
        "contexts": [], "pending": None, "final": None,
        "best": {"path": plan["baseline_path"],
                 "sha256": plan["baseline_sha256"],
                 "score": plan["selection"]["initial_score"], "kind": "baseline"},
    }
    atomic_write_json(root / "campaign.json", {
        "campaign_id": root.name, "managed_optimization": True,
        "plan_digest": digest(plan), "task": plan["task"],
    })
    atomic_write_json(root / "state.json", state)
    return status(root)


def _control(root):
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    if digest(plan) != state["plan_digest"]:
        raise ValueError("Frozen optimization plan changed")
    manifest = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    if manifest.get("plan_digest") != state["plan_digest"]:
        raise ValueError("Campaign and optimization plan disagree")
    return plan, state


def _load(root):
    plan, state = _control(root)
    frozen = root / "frozen"
    paths = list(frozen.rglob("*"))
    if frozen.is_symlink() or any(path.is_symlink() for path in paths):
        raise ValueError("Frozen task resources cannot contain symbolic links")
    actual = {p.relative_to(frozen).as_posix(): sha256(p) for p in paths if p.is_file()}
    if actual != plan["frozen_files"]:
        raise ValueError("Frozen task resources changed (content or file set)")
    if candidates.identity(root / plan["baseline_path"]) != plan["baseline_sha256"]:
        raise ValueError("Frozen baseline changed")
    if candidates.identity(root / state["best"]["path"]) != state["best"]["sha256"]:
        raise ValueError("Selected candidate changed")
    for context in state["contexts"]:
        if sha256(root / context["path"]) != context["sha256"]:
            raise ValueError("Delivered knowledge context changed")
    for record in [*state["rounds"], *([state["final"]] if state["final"] else [])]:
        directory = root / record["path"]
        if sha256(directory / "observation.json") != record["observation_sha256"]:
            raise ValueError("Retained assessment record changed")
        if candidates.identity(directory / plan["candidate_name"]) != record["candidate_sha256"]:
            raise ValueError("Retained round candidate changed")
        if sha256(directory / "execution/execution.json") != record["execution_sha256"]:
            raise ValueError("Retained execution record changed")
        source = record["observations"]["usage_source"]
        if source and sha256(directory / "agent-usage.json") != source["sha256"]:
            raise ValueError("Retained usage export changed")
        for name, expected in record["assessment"].get("evidence_files", {}).items():
            if sha256(directory / name) != expected:
                raise ValueError("Retained task evidence changed")
    return plan, state


def status(root: Path) -> dict:
    _, control = _control(root)
    if control["state"] == "blocked" and control.get("integrity_error"):
        # A diagnostic is still readable after rejected input drift. Never expose
        # a selected score or a usable summary from an invalid evidence tree.
        return {"session": str(root), "state": "blocked", "next_action": "blocked",
                "can_finalize": False, "pending": control["pending"],
                "integrity_error": control["integrity_error"], "summary": None}
    plan, state = _load(root)
    next_action = "edit_candidate_and_submit_round"
    if len(state["rounds"]) == plan["round_limit"]:
        next_action = "independently_retest_selected_candidate_with_final"
    search_remaining = state["deadline"] - time.time() - plan["final_reserve_seconds"]
    if search_remaining <= 0 and state["final"] is None:
        next_action = ("independently_retest_selected_candidate_with_final"
                       if state["rounds"] and plan["round_mode"] == "up_to"
                       else "search_budget_exhausted_incomplete_session")
    if time.time() >= state["deadline"] and state["final"] is None:
        next_action = "deadline_exhausted_incomplete_session"
    if state["pending"] is not None:
        next_action = "recover_existing_attempt_without_relaunch"
    if state["state"] in ("completed", "blocked"):
        next_action = state["state"]
    return {
        "session": str(root), "state": state["state"], "next_action": next_action,
        "completed_rounds": len(state["rounds"]), "round_limit": plan["round_limit"],
        "remaining_seconds": max(0, state["deadline"] - time.time()),
        "remaining_search_seconds": max(0, search_remaining),
        "round_mode": plan["round_mode"],
        "can_finalize": (state["state"] == "active" and state["pending"] is None
                         and time.time() < state["deadline"] and bool(state["rounds"])
                         and (plan["round_mode"] == "up_to"
                              or len(state["rounds"]) == plan["round_limit"])),
        "task_instructions": str(root / "frozen/TASK.md"),
        "working_candidate": str(root / plan["working_candidate"]),
        "best": state["best"], "pending": state["pending"],
        "latest_observation": state["rounds"][-1] if state["rounds"] else None,
        "summary": str(root / "summary.json") if state["final"] is not None else None,
    }


def _active(state, *, reserve=0):
    if state["state"] != "active" or state["pending"] is not None:
        raise ValueError("Session is complete, blocked or has an unresolved attempt")
    if time.time() >= state["deadline"] - reserve:
        raise ValueError("Optimization deadline exhausted, final evaluation is incomplete")


def capture_context(root: Path, reader, *, retain_context, **request) -> dict:
    with _locked(root):
        plan, state = _load(root)
        _active(state, reserve=plan["final_reserve_seconds"])
        if plan.get("knowledge_allowed") is False:
            raise ValueError("Knowledge delivery is disabled by the frozen condition")
        path, fingerprint = retain_context(root, context_id="context-" + uuid.uuid4().hex,
                                           reader=reader, **request)
        reference = {"path": path.relative_to(root).as_posix(), "sha256": fingerprint,
                     "kind": "delivered_context"}
        state["contexts"].append(reference)
        atomic_write_json(root / "state.json", state)
    return {"reference": reference, "context": json.loads(path.read_text(encoding="utf-8"))}


def _usage_record(source):
    if source is None:
        return {"usage": None, "tool_calls": None, "usage_source": None}, None
    raw = Path(source).read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Usage export must be a JSON object")
    usage = normalize_usage(payload)
    if not usage or usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        raise ValueError("Usage export requires nonnegative input_tokens and output_tokens")
    return ({"usage": usage, "tool_calls": None,
             "usage_source": {"kind": "caller_export", "sha256": hashlib.sha256(raw).hexdigest()}},
            raw)


def _token_totals(records):
    totals = usage_totals(records)
    fields = ("input_tokens", "output_tokens", "cached_input_tokens", "total_tokens", "cost")
    return {name: totals[name] for name in fields}


def _summary(root, plan, state):
    rounds = state["rounds"]
    final = state["final"]
    return {
        "schema_version": 1, "task": plan["task"], "condition": plan["condition"],
        "state": state["state"], "planned_rounds": plan["round_limit"],
        "completed_rounds": len(rounds), "selected_candidate": state["best"],
        "final_assessment": final["assessment"] if final else None,
        "optimization_speedup": (
            1.0 if final and final["assessment"]["status"] == "completed"
            and state["best"]["kind"] == "baseline"
            else (final["assessment"].get("speedup")
                  if final["assessment"].get("speedup") is not None
                  else (final["assessment"]["score"] if plan["selection"]["metric"] == "speedup"
                        else None)) if final else None
        ),
        "selection": plan["selection"], "stop_reason": state.get("stop_reason"),
        "wall_elapsed_seconds": state.get("settled_at", time.time()) - state["started_at"],
        "usage": _token_totals(rounds), "usage_scope": "caller_round_exports",
        "session_usage_export": final.get("observations") if final else None,
        "knowledge_deliveries": state["contexts"],
        "curve": [
            {"round": index + 1, "hypothesis": item["hypothesis"],
             "assessment": item["assessment"], "best_score": item["best_after"]["score"],
             "cumulative_usage": _token_totals(rounds[:index + 1])}
            for index, item in enumerate(rounds)
        ],
    }


def _failure(error):
    return {"status": "infrastructure_failure", "score": None,
            "verdict": "INCONCLUSIVE", "reason": f"{type(error).__name__}: {error}"}


def _settle(root, plan, state, pending, execution, assess):
    directory = root / pending["path"]
    # Re-check integrity before accepting a score. Drift is terminal, but must
    # leave a recorded rejection rather than an attempt permanently in pending.
    try:
        _load(root)
        if candidates.identity(directory / plan["candidate_name"]) != pending["candidate_sha256"]:
            raise ValueError("Submitted candidate changed during evaluation")
    except (OSError, ValueError, TypeError, KeyError) as error:
        state["integrity_error"] = str(error)
    try:
        if state.get("integrity_error"):
            raise ValueError(state["integrity_error"])
        if execution.get("coordinator_error"):
            raise ValueError(execution["coordinator_error"])
        assessment = assess(root, directory, plan, execution)
        if not isinstance(assessment, dict) or assessment.get("status") not in (
            "completed", "candidate_failure", "infrastructure_failure"
        ):
            raise ValueError("Unknown task assessment status")
        score = assessment.get("score")
        if assessment["status"] == "completed":
            if type(score) not in (int, float) or not math.isfinite(score) or score <= 0:
                raise ValueError("Completed assessment requires a finite positive score")
            if pending["kind"] == "round" and state["best"]["score"] is None:
                baseline_score = assessment.get("baseline_score")
                if (type(baseline_score) not in (int, float)
                        or not math.isfinite(baseline_score) or baseline_score <= 0):
                    raise ValueError("The task must supply the measured baseline objective")
    except Exception as error:
        assessment = _failure(error)
    score = assessment.get("score")
    if assessment["status"] != "completed":
        assessment["score"] = None
    record = {**pending, "assessment": assessment, "execution": execution,
              "execution_sha256": sha256(directory / "execution/execution.json"),
              "elapsed_seconds": execution.get("elapsed_seconds")}
    if pending["kind"] == "round":
        best_score = state["best"]["score"]
        if best_score is None and assessment["status"] == "completed":
            best_score = assessment["baseline_score"]
            state["best"]["score"] = best_score
        improved = (score is not None and best_score is not None and (
            score < best_score if plan["selection"]["direction"] == "minimize"
            else score > best_score))
        if (assessment["status"] == "completed" and assessment.get("eligible", True)
                and improved and pending["candidate_sha256"] != candidates.identity(
                    root / plan["baseline_path"])):
            state["best"] = {"kind": "candidate",
                             "candidate_id": pending["candidate_id"],
                             "path": pending["path"] + "/" + plan["candidate_name"],
                             "sha256": pending["candidate_sha256"], "score": score}
        record["best_after"] = dict(state["best"])
        state["rounds"].append(record)
    else:
        state["final"] = record
        state["state"] = "completed" if assessment["status"] == "completed" else "blocked"
    if assessment["status"] == "infrastructure_failure":
        state["state"] = "blocked"
    if state["state"] in ("completed", "blocked"):
        state["settled_at"] = time.time()
    state["pending"] = None
    atomic_write_json(directory / "observation.json", record)
    record["observation_sha256"] = sha256(directory / "observation.json")
    atomic_write_json(root / "state.json", state)
    summary = _summary(root, plan, state)
    if state.get("integrity_error"):
        summary.update(integrity_error=state["integrity_error"], optimization_speedup=None,
                       selected_candidate=None)
    atomic_write_json(root / "summary.json", summary)
    return status(root)


def evaluate_round(root: Path, *, candidate: Path | None, hypothesis: str,
                   usage: Path | None, execute, assess, final=False, reason=None) -> dict:
    with _locked(root):
        plan, state = _load(root)
        _active(state, reserve=0 if final else plan["final_reserve_seconds"])
        count = len(state["rounds"])
        if final and (not count or (plan["round_mode"] == "exact"
                                   and count != plan["round_limit"])):
            raise ValueError("Finish every planned round before independent final evaluation")
        if final and plan["round_mode"] == "up_to" and not (reason or "").strip():
            raise ValueError("Record why search stopped before final evaluation")
        if not final and count >= plan["round_limit"]:
            raise ValueError("Round budget consumed, run independent final evaluation")
        if not final and (not isinstance(hypothesis, str) or not hypothesis.strip()):
            raise ValueError("Declare the round hypothesis before execution")
        source = root / state["best"]["path"] if final else Path(candidate)
        if (source.is_symlink() or (plan["candidate_kind"] == "file"
                and (not source.is_file() or source.suffix != ".py"))
                or (plan["candidate_kind"] == "directory" and not source.is_dir())):
            raise ValueError("Candidate does not match the frozen input format")
        observations, usage_bytes = _usage_record(usage)
        parent = "final" if final else f"rounds/round-{count + 1:02d}"
        relative = parent + "/attempt-" + uuid.uuid4().hex
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=False)
        if usage_bytes is not None:
            (directory / "agent-usage.json").write_bytes(usage_bytes)
        fingerprint = candidates.retain(source, directory / plan["candidate_name"],
                                        plan.get("candidate_includes"))
        pending = {"kind": "final" if final else "round", "path": relative,
                   "candidate_id": state["best"].get("candidate_id", "baseline") if final
                   else f"candidate-{count + 1:03d}",
                   "hypothesis": hypothesis, "observations": observations,
                   "candidate_sha256": fingerprint,
                   "contexts": list(state["contexts"]), "started_at": time.time()}
        state["pending"] = pending
        if final:
            state["stop_reason"] = reason or "fixed_round_budget_completed"
        atomic_write_json(root / "state.json", state)
        deadline = state["deadline"] - (0 if final else plan["final_reserve_seconds"])
        try:
            execution = execute(root, directory, plan, deadline)
        except Exception as error:
            # A completed child may have persisted its receipt before the caller
            # failed. Collect it without launching the same candidate again.
            path = directory / "execution/execution.json"
            atomic_write_json(directory / "coordinator-error.json", {
                "type": type(error).__name__, "error": str(error)})
            if path.is_file():
                execution = json.loads(path.read_text(encoding="utf-8"))
            else:
                execution = {"status": "error", "returncode": None,
                             "coordinator_error": str(error), "cleanup_verified": None}
                # No receipt does not prove termination. The resulting blocked
                # session cannot launch more work or claim device cleanup.
                path.parent.mkdir(exist_ok=True)
                atomic_write_json(path, execution)
        return _settle(root, plan, state, pending, execution, assess)


def read_records(root: Path) -> tuple[dict, dict, dict]:
    """Read one validated state for status, dashboard and reconstructable summaries."""
    plan, state = _load(root)
    return plan, state, _summary(root, plan, state)


def recover(root: Path, assess) -> dict:
    with _locked(root):
        _, control = _control(root)
        if control["state"] == "blocked" and control.get("integrity_error"):
            return status(root)
        plan, state = _load(root)
        pending = state["pending"]
        if pending is None:
            atomic_write_json(root / "summary.json", _summary(root, plan, state))
            return status(root)
        path = root / pending["path"] / "execution/execution.json"
        if not path.is_file():
            raise ValueError("Execution record unavailable, inspect cleanup before recovery")
        execution = json.loads(path.read_text(encoding="utf-8"))
        return _settle(root, plan, state, pending, execution, assess)
