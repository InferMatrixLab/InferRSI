"""Read settled service observations, including older records with embedded profiler output."""

import json

from . import project_service as service


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
