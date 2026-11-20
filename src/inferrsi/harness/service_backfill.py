"""Publish supplemental profiles under the settled round's directory."""

import re
import time
import uuid

from . import optimization
from . import project_service as service
from .atomic_json import atomic_write_json


def _target(state, number):
    for attempt in reversed(state["attempts"]):
        if (
            attempt["kind"] == "round"
            and attempt["round_number"] == number
            and attempt["assessment"]["verdict"] in ("PASS", "FAIL")
        ):
            return attempt
    raise ValueError(f"Round {number} has no settled PASS or FAIL attempt")


def _lineage(attempt, capture_id):
    return {
        "capture_id": capture_id,
        "target_attempt_id": attempt["attempt_id"],
        "target_binding": attempt["execution"]["binding"],
        "round_number": attempt["round_number"],
        "protocol_path": attempt["protocol_path"],
    }


def _original_binding(root, target):
    directory = service.safe_path(root, target["path"])
    binding = service.read(directory / "request.json")
    config = service.read(directory / "effective-config.json")
    if (
        binding != target["execution"].get("binding")
        or any(binding.get(k) != target[k] for k in ("attempt_id", "revision", "conditions"))
        or not binding.get("service_id")
        or not binding.get("run_id")
        or config != target["conditions"]["effective_config"]
        or config != binding.get("effective_config")
    ):
        raise ValueError("Cannot reproduce the target revision, binding or effective configuration")
    return binding


def _index(root, attempt):
    path = service.safe_path(root, attempt["path"] + "/backfills/index.json")
    if not path.exists():
        return path, []
    document = service.read(path)
    captures = document.get("captures")
    if document.get("target_attempt_id") != attempt["attempt_id"] or not isinstance(captures, list):
        raise ValueError("Invalid profile index for the target attempt")
    return path, captures


def _validated(root, target, capture_id):
    if not isinstance(capture_id, str) or not re.fullmatch(r"[0-9a-f]{32}", capture_id):
        return None
    relative = target["path"] + "/backfills/" + capture_id
    directory = service.safe_path(root, relative)
    if service.read(directory / "target.json") != _lineage(target, capture_id):
        return None
    execution = service.read(service.safe_path(directory, "execution/execution.json"))
    binding = execution["binding"]
    original = _original_binding(root, target)
    if (
        execution.get("status") != "completed"
        or execution.get("profiling_error")
        or binding["service_id"] == original["service_id"]
        or binding["run_id"] == original["run_id"]
    ):
        return None
    return service.attempt_profile(
        root, {**target, "attempt_id": capture_id, "path": relative, "execution": execution}
    )


def latest(root, attempt):
    """Read the latest usable published capture; each one has its own service binding."""
    try:
        _, captures = _index(root, attempt)
    except (ValueError, OSError):
        return None
    for capture_id in reversed(captures):
        try:
            profile = _validated(root, attempt, capture_id)
        except (KeyError, TypeError, ValueError, OSError, RecursionError):
            continue
        if profile:
            return profile
    return None


def _diagnostic(root, pending, execution, status, message):
    steps = execution.get("steps") or []
    last = steps[-1] if isinstance(steps, list) and steps and isinstance(steps[-1], dict) else {}
    stage = execution.get("failed_stage") or last.get("id") or "startup"
    return service.capture_diagnostic(
        root, service.safe_path(root, pending["path"]), stage, status, message
    )


def _finish(root, plan, state, execution, *, preparation_seconds=None):
    started = time.monotonic()
    pending = state["pending"]
    target = _target(state, pending["round_number"])
    capture_id = pending["attempt_id"]
    if pending["target_attempt_id"] != target["attempt_id"]:
        raise ValueError("Pending capture target disagrees with the settled attempt")
    cleanup = optimization._service_cleanup_confirmed(state, {**pending, "execution": execution})
    error = execution.get("profiling_error")
    directory = service.safe_path(root, pending["path"])
    # Each invocation starts a new monotonic interval. Only committed progress survives a crash.
    previous = execution.get("publication_elapsed_seconds", 0)
    if not service.number(previous) or previous < 0:
        previous = 0
    timed = preparation_seconds is not None or (cleanup and not error)

    def elapsed():
        return previous + (preparation_seconds or 0) + (time.monotonic() - started if timed else 0)

    def settle():
        return _settle(root, directory, plan, state, target, execution, cleanup, timed, elapsed)

    try:
        return settle()
    except KeyboardInterrupt:
        # A signal can arrive on either side of the atomic index replacement.
        try:
            committed = capture_id in _index(root, target)[1]
        except (OSError, ValueError):
            committed = False
        message = (
            "Publication interrupted after the capture was published"
            if committed
            else "Publication interrupted before the capture was published"
        )
        field = "publication_interruption" if committed else "profiling_error"
        execution[field] = service.capture_diagnostic(
            root, directory, "publication", "interrupted", message
        )
        if timed:
            execution["publication_elapsed_seconds"] = elapsed()
        _write_execution(directory, execution)
        return settle()


def _publish(root, target, capture_id, checkpoint):
    profile = _validated(root, target, capture_id)
    if not profile:
        raise ValueError("Captured evidence does not validate against this attempt")
    path, captures = _index(root, target)
    checkpoint()
    if capture_id not in captures:
        atomic_write_json(
            path, {"target_attempt_id": target["attempt_id"], "captures": [*captures, capture_id]}
        )
    return profile


def _settle(root, directory, plan, state, target, execution, cleanup, timed, elapsed):
    pending = state["pending"]
    capture_id = pending["attempt_id"]
    # Keep the entry state intact if interruption requires replay under this lock.
    state = {**state, "profiling_accounting": dict(state.get("profiling_accounting", {}))}
    error = execution.get("publication_interruption") or execution.get("profiling_error")
    published = None

    def checkpoint():
        if timed:
            execution["publication_elapsed_seconds"] = elapsed()
            _write_execution(directory, execution)

    if not cleanup:
        error = error or _diagnostic(
            root, pending, execution, "failed", "Inspect cleanup and supply --cleanup-receipt"
        )
    elif not error:
        try:
            published = _publish(root, target, capture_id, checkpoint)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            error = service.capture_diagnostic(root, directory, "publication", "failed", str(exc))
            execution["profiling_error"] = error
            _write_execution(directory, execution)
    profiling = optimization._service_profiling(root, target, published=published)
    attempts = [
        optimization._service_round_view(
            root, attempt, profiling=profiling if attempt is target else None
        )
        for attempt in state["attempts"]
    ]
    ledger_entry = None
    budget_time = None
    if cleanup:
        optimization._service_account_capture(root, state, pending, execution)
        ledger_entry = state.get("profiling_accounting", {}).get(capture_id)
        if ledger_entry is not None:
            # Match the report's decision clock to this provisional credit.
            budget_time = time.time() if timed else None
            capture_seconds = ledger_entry["elapsed_seconds"]
            ledger_entry["elapsed_seconds"] = capture_seconds + elapsed()
        state["last_profiling_error"] = error
        state["pending"] = None
    summary = optimization._service_summary(
        root, plan, state, attempts=attempts, budget_time=budget_time
    )
    atomic_write_json(root / "summary.json", summary)
    checkpoint()
    if ledger_entry is not None:
        ledger_entry["elapsed_seconds"] = capture_seconds + elapsed()
    # Clearing pending is the final commit: recover can replay any earlier index/summary write.
    atomic_write_json(root / "state.json", state)
    result = {
        "round": target["round_number"],
        "target_attempt_id": target["attempt_id"],
        "capture_id": capture_id,
        "profiling": profiling,
        "exit_code": 0,
        "cleanup_verified": cleanup,
    }
    if error:
        result["profiling_error"] = error
        result["exit_code"] = 130 if error["status"] == "interrupted" else 2
    return result


def run(root, args):
    """Start a profile-only service under the caller's nonblocking campaign lock."""
    started = time.monotonic()
    plan, state = optimization._load(root)
    if state["pending"]:
        raise ValueError("Resolve the pending attempt and verify cleanup before capture")
    if state["attempts"] and not optimization._service_cleanup_confirmed(
        state, state["attempts"][-1]
    ):
        raise ValueError("Verify the previous service cleanup before capture")
    target = _target(state, args.round)
    _original_binding(root, target)
    compatible = ("workload", "model", "precision", "topology", "runtime", "timing_scope")
    if any(target["conditions"][key] != state["conditions"][key] for key in compatible):
        raise ValueError(
            "Cannot reproduce the target workload, model, device or runtime conditions"
        )
    if not plan["evaluation_settings"]["commands"].get("profile"):
        raise ValueError("No profiler configured in the retained protocol")
    capture_id = uuid.uuid4().hex
    pending = {
        key: target[key]
        for key in (
            "round_number",
            "candidate_id",
            "source_repo",
            "revision",
            "conditions",
            "protocol_path",
        )
    }
    pending.update(
        kind="profile",
        role="candidate",
        attempt_id=capture_id,
        target_attempt_id=target["attempt_id"],
        path=target["path"] + "/backfills/" + capture_id,
        started_at=time.time(),
    )
    directory = service.safe_path(root, pending["path"])
    directory.mkdir(parents=True)
    atomic_write_json(directory / "target.json", _lineage(target, capture_id))
    state["pending"] = pending
    atomic_write_json(root / "state.json", state)
    preparation_seconds = time.monotonic() - started
    try:
        sampling = plan["evaluation_settings"]["sampling"]
        timeout = sampling.get("profile_timeout_seconds", sampling["stage_timeout_seconds"])
        execution = service.execute(root, directory, plan, pending, time.time() + timeout)
    except (Exception, KeyboardInterrupt) as error:
        execution = _read_execution(directory)
        status = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        execution["profiling_error"] = _diagnostic(
            root, pending, execution, status, str(error) or status
        )
        _write_execution(directory, execution)
    return _finish(root, plan, state, execution, preparation_seconds=preparation_seconds)


def _read_execution(directory):
    try:
        return service.read(service.safe_path(directory, "execution/execution.json"))
    except (OSError, ValueError):
        return {}


def _write_execution(directory, execution):
    path = service.safe_path(directory, "execution/execution.json")
    path.parent.mkdir(exist_ok=True)
    atomic_write_json(path, execution)


def recover(root, plan, state, args):
    """Settle a single capture from durable evidence, without restarting its service."""
    pending = state["pending"]
    directory = service.safe_path(root, pending["path"])
    execution = _read_execution(directory)
    if execution.get("status") != "completed" and not execution.get("profiling_error"):
        execution["profiling_error"] = _diagnostic(
            root,
            pending,
            execution,
            "interrupted",
            "Capture interrupted before completion; further error details were not recorded",
        )
        _write_execution(directory, execution)
    return _finish(root, plan, state, execution)
