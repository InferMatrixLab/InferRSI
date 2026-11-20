"""Read settled service observations, including older records with embedded profiler output."""

import json

from . import project_service as service


def inline_profiles(attempts):
    profiles = {}
    for attempt in attempts:
        execution = attempt["execution"]
        profiles[attempt["attempt_id"]] = execution.get("profile")
        if attempt["kind"] == "refresh":
            for ref, run in zip(execution.get("references", ()), execution.get("runs", ())):
                profiles[ref["attempt_id"]] = run.get("profile")
    return profiles


def reference_view(ref, profiles):
    if not isinstance(ref, dict):
        return ref
    view = dict(ref)
    if "profile" not in ref:
        attempt_id = ref.get("attempt_id")
        profile = profiles.get(attempt_id) if isinstance(attempt_id, str) else None
        # New snapshots of a historical embedded receipt exposed only its original path.
        if isinstance(profile, dict) and "receipt" in profile:
            profile = {"result": profile.get("result")}
        view["profile"] = profile
    if ref.get("parent_reference_at_acceptance"):
        view["parent_reference_at_acceptance"] = reference_view(
            ref["parent_reference_at_acceptance"], profiles
        )
    return view


def selection_view(state, attempts):
    """Assemble selection profiles for readers after validating the original control record."""
    profiles = inline_profiles(state["attempts"])

    def observation(record):
        if record is None:
            return None
        view = dict(record)
        for key in ("parent", "initial", "best_after", "refresh_parent", "refresh_initial"):
            if key in record:
                view[key] = reference_view(record[key], profiles)
        execution = record.get("execution", {})
        if "references" in execution:
            view["execution"] = {
                **execution,
                "references": [reference_view(ref, profiles) for ref in execution["references"]],
            }
        return view

    stagnation = state["stagnation"]
    return {
        **state,
        "best": reference_view(state["best"], profiles),
        "initial_reference": reference_view(state["initial_reference"], profiles),
        "comparison_parent": reference_view(state["comparison_parent"], profiles),
        "pending": observation(state["pending"]),
        "final": observation(state["final"]),
        "attempts": [observation(attempt) for attempt in attempts],
        "stagnation": {
            **stagnation,
            "events": [
                {**event, "best": reference_view(event["best"], profiles)}
                for event in stagnation["events"]
            ],
        },
    }


def _large_profile_error(attempt):
    error = attempt["execution"].get("profiling_error")
    return (
        attempt["kind"] == "round"
        and isinstance(error, dict)
        and error.get("stage") == "profile"
        and "details_path" not in error
        and isinstance(error.get("message"), str)
        and len(error["message"]) > 2049
    )


def matches_control(root, attempt):
    path = service.safe_path(root, attempt["path"] + "/observation.json")
    if path.stat().st_size <= service.JSON_SIZE_LIMIT:
        return service.read(path) == attempt
    if not path.is_file():
        return False
    # Compare only bytes that the trusted state and the atomic JSON writer can account for.
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False)
    with path.open(encoding="utf-8") as stream:
        return all(stream.read(len(part)) == part for part in encoder.iterencode(attempt)) and (
            stream.read(2) == "\n"
        )


def display(root, attempt):
    if not _large_profile_error(attempt):
        return attempt
    execution = attempt["execution"]
    error = execution["profiling_error"]
    # The observation itself retains the full message even after a capture directory is lost.
    details = attempt["path"] + "/observation.json"
    receipt = attempt["path"] + "/execution/profile/result.json"
    try:
        if service.safe_path(root, receipt).is_file():
            details = receipt
    except (OSError, ValueError):
        pass
    error = {**error, "message": service._error_excerpt(error["message"]), "details_path": details}
    steps = []
    for step in execution["steps"]:
        if step["id"] == "profile":
            step = {k: v for k, v in step.items() if k != "result"}
            for key in ("reason", "error"):
                if isinstance(step.get(key), str):
                    step[key] = service._error_excerpt(step[key])
        steps.append(step)
    return {**attempt, "execution": {**execution, "profiling_error": error, "steps": steps}}
