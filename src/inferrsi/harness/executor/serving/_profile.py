"""Read bound profile receipts and retain service diagnostics."""

import json
import re

from ...records import service_io

# Round and reference records repeat this metadata. The collector's raw receipt stays on disk.
PROFILE_METADATA_LIMIT = 32 * 1024


def validated_profile(root, directory, attempt_id, conditions, binding, step, *, captured=None):
    """Reconstruct a usable profile only from the capture's own bound on-disk evidence."""
    directory = service_io.safe_path(root, directory.relative_to(root).as_posix())
    result = service_io.safe_path(directory, "execution/profile/result.json")
    if (
        not isinstance(binding, dict)
        or binding.get("attempt_id") != attempt_id
        or binding.get("conditions") != conditions
        or binding.get("effective_config") != conditions["effective_config"]
        or not all(binding.get(key) for key in ("revision", "service_id", "run_id"))
        or service_io.read(service_io.safe_path(directory, "request.json")) != binding
        or service_io.read(service_io.safe_path(directory, "effective-config.json"))
        != conditions["effective_config"]
    ):
        raise ValueError("profile: incompatible capture binding")
    trace = service_io.read(result)
    if (
        trace.get("binding") != binding
        or trace.get("status") != "completed"
        or trace.get("validated") is not True
        or (captured is not None and captured != trace)
        or not isinstance(step, dict)
        or step.get("id") != "profile"
        or step.get("status") != "completed"
        or ("result" in step and step["result"] != trace)
    ):
        raise ValueError("profile: missing or incompatible validated receipt")
    interval = (
        step.get("started_at"), trace.get("capture_started_at"),
        trace.get("capture_ended_at"), step.get("ended_at"),
    )
    if not all(service_io.finite_number(t) for t in interval) or not (
        interval[0] <= interval[1] <= interval[2] <= interval[3]
    ):
        raise ValueError("profile: missing or incompatible capture interval")
    artifacts = trace.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("profile: missing artifacts")
    legacy = "result" in step
    locations = []
    metadata = {"artifacts": locations}
    if legacy:
        # Previously written profiles kept the full receipt in both the step and the profile.
        metadata["receipt"] = trace
    else:
        metadata.update(capture_started_at=interval[1], capture_ended_at=interval[2])
        metadata_bytes = len(json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
    for relative in artifacts:
        path = service_io.safe_path(directory, relative)
        location = path.relative_to(root).as_posix()
        if not legacy:
            # Account for the encoded path and the JSON list separator between locations.
            metadata_bytes += len(json.dumps(location, ensure_ascii=False).encode("utf-8"))
            if locations:
                metadata_bytes += 2
            if metadata_bytes > PROFILE_METADATA_LIMIT:
                raise ValueError(f"profile: metadata exceeds {PROFILE_METADATA_LIMIT} bytes")
        if not path.is_file():
            raise ValueError("profile: missing or empty artifact")
        with path.open("rb") as artifact:
            if not artifact.read(1):
                raise ValueError("profile: missing or empty artifact")
        locations.append(location)
    return {
        "attempt_id": attempt_id,
        "conditions": conditions,
        "binding": binding,
        "result": result.relative_to(root).as_posix(),
        **metadata,
    }


def read_service_attempt_profile(root, attempt):
    """Return the retained profile, or None if its evidence is missing or disagrees."""
    execution = attempt["execution"]
    profile = execution.get("profile")
    if not isinstance(profile, dict):
        return None
    try:
        binding = execution["binding"]
        if binding["revision"] != attempt["revision"]:
            return None
        step = next((s for s in execution["steps"] if s.get("id") == "profile"), None)
        validated = validated_profile(
            root,
            service_io.safe_path(root, attempt["path"]),
            attempt["attempt_id"],
            attempt["conditions"],
            binding,
            step,
        )
        return validated if validated == profile else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None


def service_capture_diagnostic(root, directory, stage, status, message, *, process_failed=False):
    if not isinstance(stage, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", stage):
        stage = "startup"
    diagnostic = {"stage": stage, "status": status, "message": service_io.error_excerpt(message)}
    stage_dir = directory / ("service" if stage == "service" else "execution/" + stage)
    try:
        receipts = ("execution.json", "result.json") if process_failed else (
            "result.json", "execution.json"
        )
        for name in receipts:
            receipt = service_io.safe_path(root, (stage_dir / name).relative_to(root).as_posix())
            if receipt.is_file():
                diagnostic["details_path"] = receipt.relative_to(root).as_posix()
                break
        if diagnostic["message"] != message:
            # Unexpected coordinator exceptions can lack a stage receipt with the original detail.
            relative = (directory / f"{stage}-error.txt").relative_to(root).as_posix()
            service_io.safe_path(root, relative).write_text(
                message, encoding="utf-8", errors="replace"
            )
            diagnostic["details_path"] = relative
        log = service_io.safe_path(root, (stage_dir / "stderr.log").relative_to(root).as_posix())
        if log.is_file():
            diagnostic["log"] = log.relative_to(root).as_posix()
            with log.open("rb") as stream:
                stream.seek(max(0, log.stat().st_size - 1024))
                detail = stream.read(1024).decode("utf-8", errors="replace").strip()
            if detail:
                diagnostic["message"] += f"\n{detail}"
    except (OSError, ValueError):
        pass  # The stage error remains available even if its log cannot be read.
    return diagnostic


def service_capture_elapsed(root, pending, execution):
    """Recover monotonic capture progress without charging a crash-to-recovery interval."""
    capture = execution.get("capture")
    if not isinstance(capture, dict) or capture.get("id") != pending.get("attempt_id"):
        return 0.0
    elapsed = capture.get("elapsed_seconds")
    if not service_io.finite_number(elapsed) or elapsed < 0:
        return 0.0
    steps = execution.get("steps")
    if (
        service_io.finite_number(capture.get("ended_at"))
        or not isinstance(steps, list)
        or not steps
    ):
        return elapsed
    step = steps[-1]
    if not isinstance(step, dict):
        return elapsed
    try:
        offset = step["capture_offset_seconds"]
        stage = step["id"]
        if (
            step.get("status") != "running"
            or not service_io.finite_number(offset)
            or offset != elapsed
            or capture["id"] != execution["binding"]["attempt_id"]
            or not re.fullmatch(r"precheck|ready|warmup-[0-9]+|profile|stop", stage)
            or (pending["kind"] != "profile" and stage != "profile")
        ):
            return elapsed
        directory = service_io.safe_path(root, pending["path"])
        if service_io.read(service_io.safe_path(directory, "request.json")) != execution["binding"]:
            return elapsed
        stage_dir = service_io.safe_path(directory, f"execution/{stage}")
        receipt = service_io.read(service_io.safe_path(stage_dir, "execution.json"))
        duration = receipt["elapsed_seconds"]
        if (
            receipt.get("status") not in ("completed", "failed", "cancelled", "timeout", "error")
            or receipt.get("cwd") != str(directory / "workspace")
            or receipt.get("result_path") != str(stage_dir / "result.json")
            or type(receipt.get("pid")) is not int
            or receipt["pid"] <= 0
            or not service_io.finite_number(duration)
            or duration < 0
            or not service_io.finite_number(offset + duration)
        ):
            return elapsed
        return offset + duration
    except (KeyError, TypeError, OSError, ValueError):
        return elapsed
