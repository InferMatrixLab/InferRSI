from __future__ import annotations

import copy
import os
import re
import shutil
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inferrsi import _json_v1
from inferrsi.harness import input_binding, local_process, run_store
from inferrsi.harness.errors import PublicError

# H02 single local-CPU execute in ordinary command mode (V05 null set). Evaluation mode,
# entry-code digests (T37) and generation chaining are later slices and are refused here.
ATTEMPT_FIELDS = (
    "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
    "resources", "budget", "retry_of", "retry_reason",
)
_SPEC_FIELDS = frozenset(
    {
        *ATTEMPT_FIELDS, "schema_version", "generation_record_ref", "prepared_ref",
        "protocol_digest", "operation", "validation_scope", "inputs", "candidate", "steps",
        "output_root", "required_capabilities",
    }
)
_EVALUATION_FIELDS = ("prepared_ref", "protocol_digest", "operation", "validation_scope",
                      "candidate")
_STEP_FIELDS = frozenset(
    {
        "step_id", "runtime_role", "entrypoint_kind", "entrypoint", "entrypoint_revision",
        "expected_code_sha256", "args", "cwd", "outputs", "timeout_seconds",
    }
)
_INPUT_FIELDS = frozenset(
    {"role", "source", "source_namespace", "source_ref", "snapshot_format", "expected_sha256",
     "materialized_path"}
)
_OUTPUT_FIELDS = frozenset({"role", "path", "required", "media_type", "format_schema"})
_REF_FIELDS = frozenset({"location", "sha256", "size_bytes", "media_type"})
_DIMENSION_FIELDS = frozenset({"dimension", "unit", "limit", "reserve_estimate"})
_DEFINITION_FIELDS = frozenset({"name", "revision"})
_DECIMAL = re.compile(r"(?:0|-?[1-9][0-9]*|-?(?:0|[1-9][0-9]*)\.[0-9]*[1-9])", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
# Roles of the retained stdout/stderr observations; a declared output may not reuse them.
_STREAM_ROLES = ("stdout", "stderr")
_STREAM_SCHEMA = {"name": "process-stream", "revision": "1"}
_STREAM_MEDIA_TYPE = "application/octet-stream"
_INPUT_MEDIA_TYPE = "application/octet-stream"
_INPUT_SCHEMA = {"name": "input-identity", "revision": "1"}
# The one snapshot format this slice captures: the bytes of one regular file.
SNAPSHOT_FORMAT = "file-v1"
# The only capability this target provides: one command tree in an OS-owned domain.
PROCESS_TREE = "local-process-tree"
EXECUTOR_VERSION = "inferrsi-harness-local-cpu@1"
_CONTROL_DOMAIN = "windows-job" if os.name == "nt" else "posix-process-group"
_HARNESS = "inferrsi-harness"
_USAGE_SOURCE = "harness-local-process"


@dataclass(frozen=True)
class LocalCpuTarget:
    """Trusted host configuration of the local CPU target; never read from a request.

    ``work_root`` holds per-attempt workspaces (``workspaces/<output_root>``) and private
    capture snapshots. ``controller_root`` / ``target_root`` authorize input sources of
    those namespaces; ``None`` leaves that namespace unauthorized.
    """

    target_id: str
    config_revision: str
    work_root: Path
    controller_root: Path | None = None
    target_root: Path | None = None

    def __post_init__(self) -> None:
        errors = [
            f"{name}: not an Id"
            for name in ("target_id", "config_revision")
            if not run_store._is_id(getattr(self, name))
        ]
        for name in ("work_root", "controller_root", "target_root"):
            value = getattr(self, name)
            if value is None:
                continue
            object.__setattr__(self, name, Path(value))
            if not Path(value).is_absolute():
                errors.append(f"{name}: must be an explicit absolute local path")
        if errors:
            raise PublicError(
                "InvalidRequest", stage="configure", message="illegal local CPU target",
                field_errors=errors,
            )


def _decimal(seconds: float) -> str:
    """A canonical non-negative Decimal string with microsecond resolution."""
    text = f"{max(seconds, 0.0):.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _deadline_seconds(deadline_utc: str) -> float:
    """Seconds from now until a legal Timestamp; negative once it has passed."""
    moment = datetime.strptime(deadline_utc[:19], "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    fraction = deadline_utc[20:-1] if deadline_utc[19] == "." else ""
    return (moment - datetime.now(timezone.utc)).total_seconds() + float(f"0.{fraction or 0}")


def _is_path(value: object) -> bool:
    return isinstance(value, str) and input_binding.RELATIVE_PATH.fullmatch(value) is not None


def _is_ids(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(run_store._is_id(item) for item in value)
        and len(set(value)) == len(value)
    )


def _is_uint(value: object) -> bool:
    return type(value) is int and 0 <= value <= _json_v1.MAX_SAFE_INTEGER


def _is_definition(value: object) -> bool:
    return run_store._has_fields(value, _DEFINITION_FIELDS) and all(
        run_store._is_id(value[name]) for name in _DEFINITION_FIELDS
    )


def _is_artifact_ref(value: object) -> bool:
    return (
        run_store._has_fields(value, _REF_FIELDS)
        and _is_path(value["location"])
        and isinstance(value["sha256"], str)
        and _SHA256.fullmatch(value["sha256"]) is not None
        and _is_uint(value["size_bytes"])
        and isinstance(value["media_type"], str)
        and bool(value["media_type"])
    )


def _optional(value: object, check) -> bool:
    return value is None or check(value)


def _positive_decimal(value: object) -> bool:
    return (
        isinstance(value, str)
        and _DECIMAL.fullmatch(value) is not None
        and not value.startswith("-")
        and value != "0"
    )


def _input_errors(inputs: object) -> list[str]:
    if not isinstance(inputs, list):
        return ["inputs: must be a list"]
    errors: list[str] = []
    for index, item in enumerate(inputs):
        where = f"inputs[{index}]"
        if not run_store._has_fields(item, _INPUT_FIELDS):
            errors.append(f"{where}: fields must be exactly the InputSpec fields")
            continue
        if not run_store._is_id(item["role"]):
            errors.append(f"{where}.role: not an Id")
        if not isinstance(item["source"], str):
            errors.append(f"{where}.source: not a Text")
        if item["source_namespace"] not in ("controller", "target", "artifact"):
            errors.append(f"{where}.source_namespace: not controller, target or artifact")
        if not run_store._is_id(item["snapshot_format"]):
            errors.append(f"{where}.snapshot_format: not an Id")
        if not _optional(item["expected_sha256"], lambda v: isinstance(v, str)
                         and _SHA256.fullmatch(v) is not None):
            errors.append(f"{where}.expected_sha256: not null or a Sha256")
        if not _is_path(item["materialized_path"]):
            errors.append(f"{where}.materialized_path: not a relative Path")
        # V04: an artifact source is exactly its Ref; other namespaces carry none.
        if item["source_namespace"] == "artifact":
            ref = item["source_ref"]
            if not _is_artifact_ref(ref):
                errors.append(f"{where}.source_ref: an artifact source needs an ArtifactRef")
            elif item["source"] != ref["location"] or item["expected_sha256"] != ref["sha256"]:
                errors.append(f"{where}.source_ref: source and expected_sha256 must equal it")
        elif item["source_ref"] is not None:
            errors.append(f"{where}.source_ref: must be null outside the artifact namespace")
    if not errors:
        roles = [item["role"] for item in inputs]
        paths = [item["materialized_path"] for item in inputs]
        if len(set(roles)) != len(roles):
            errors.append("inputs: roles must be unique")
        if len(set(paths)) != len(paths):
            errors.append("inputs: materialized paths must be unique")
    return errors


def _step_errors(steps: object, ordinary: bool) -> list[str]:
    if not isinstance(steps, list) or not steps:
        return ["steps: must be a non-empty list"]
    errors: list[str] = []
    for index, step in enumerate(steps):
        where = f"steps[{index}]"
        if not run_store._has_fields(step, _STEP_FIELDS):
            errors.append(f"{where}: fields must be exactly the CommandStep fields")
            continue
        for name in ("step_id", "runtime_role", "entrypoint_revision"):
            if not run_store._is_id(step[name]):
                errors.append(f"{where}.{name}: not an Id")
        if step["entrypoint_kind"] not in ("python_module", "executable"):
            errors.append(f"{where}.entrypoint_kind: not python_module or executable")
        if not isinstance(step["entrypoint"], str):
            errors.append(f"{where}.entrypoint: not a Text")
        digest = step["expected_code_sha256"]
        if not _optional(digest, lambda v: isinstance(v, str) and _SHA256.fullmatch(v)):
            errors.append(f"{where}.expected_code_sha256: not null or a Sha256")
        elif ordinary and digest is not None:
            # V32-N1: ordinary command mode carries no expected entry digest.
            errors.append(f"{where}.expected_code_sha256: must be null in ordinary command mode")
        if not (isinstance(step["args"], list) and all(isinstance(a, str) for a in step["args"])):
            errors.append(f"{where}.args: not a list of Text")
        if step["cwd"] != "." and not _is_path(step["cwd"]):
            errors.append(f"{where}.cwd: not '.' or a relative Path")
        if not _optional(step["timeout_seconds"], _positive_decimal):
            errors.append(f"{where}.timeout_seconds: not null or a positive Decimal")
        errors.extend(_output_errors(step["outputs"], where))
    if not errors:
        ids = [step["step_id"] for step in steps]
        if len(set(ids)) != len(ids):
            errors.append("steps: step_id values must be unique")
    return errors


def _output_errors(outputs: object, where: str) -> list[str]:
    if not isinstance(outputs, list):
        return [f"{where}.outputs: must be a list"]
    errors: list[str] = []
    for index, output in enumerate(outputs):
        place = f"{where}.outputs[{index}]"
        if not run_store._has_fields(output, _OUTPUT_FIELDS):
            errors.append(f"{place}: fields must be exactly the OutputSpec fields")
            continue
        if not run_store._is_id(output["role"]):
            errors.append(f"{place}.role: not an Id")
        elif output["role"] in _STREAM_ROLES:
            errors.append(f"{place}.role: {output['role']} is reserved for the process stream")
        if not _is_path(output["path"]):
            errors.append(f"{place}.path: not a relative Path")
        if not isinstance(output["required"], bool):
            errors.append(f"{place}.required: not a boolean")
        if not isinstance(output["media_type"], str) or not output["media_type"]:
            errors.append(f"{place}.media_type: an ArtifactRef needs a non-empty media type")
        if not _is_definition(output["format_schema"]):
            errors.append(f"{place}.format_schema: not a DefinitionRef")
    if not errors:
        roles = [output["role"] for output in outputs]
        paths = [output["path"] for output in outputs]
        if len(set(roles)) != len(roles) or len(set(paths)) != len(paths):
            errors.append(f"{where}.outputs: roles and paths must be unique")
    return errors


def _request_errors(spec: Mapping) -> list[str]:
    """Shape and resource/budget field errors beyond the AttemptContext rules."""
    errors: list[str] = []
    if not _is_path(spec["output_root"]):
        errors.append("output_root: not a relative Path")
    if not _is_ids(spec["required_capabilities"]):
        errors.append("required_capabilities: not a list of unique Ids")
    resources = spec["resources"]
    if run_store._has_fields(resources, run_store._RESOURCE_FIELDS):
        for name in ("cpu_count", "memory_bytes"):
            # V11: a stated CPU or memory request is positive.
            if not _optional(resources[name], lambda v: _is_uint(v) and v > 0):
                errors.append(f"resources.{name}: not null or a positive integer")
        if not _is_ids(resources["required_capabilities"]):
            errors.append("resources.required_capabilities: not a list of unique Ids")
    budget = spec["budget"]
    if run_store._has_fields(budget, run_store._BUDGET_FIELDS):
        if not _optional(budget["policy_ref"], _is_definition):
            errors.append("budget.policy_ref: not null or a DefinitionRef")
        for name in ("scope_id", "declared_by"):
            if not run_store._is_id(budget[name]):
                errors.append(f"budget.{name}: not an Id")
        if not _is_ids(budget["required_enforcement"]):
            errors.append("budget.required_enforcement: not a list of unique Ids")
        dimensions = budget["dimensions"]
        if not isinstance(dimensions, list) or not all(
            run_store._has_fields(item, _DIMENSION_FIELDS)
            and run_store._is_id(item["dimension"])
            and run_store._is_id(item["unit"])
            and all(
                _optional(item[name], lambda v: isinstance(v, str) and _DECIMAL.fullmatch(v))
                for name in ("limit", "reserve_estimate")
            )
            for item in dimensions
        ):
            errors.append("budget.dimensions: not a list of BudgetDimension")
    return errors


def validate(spec: object, target: LocalCpuTarget) -> None:
    """Refuse a request before registration (D021 priority: version, fields, support)."""
    if isinstance(spec, Mapping):
        version = spec.get("schema_version")
        if type(version) is int and version != 1:
            raise PublicError(
                "UnsupportedSchema", stage="validate", message="only ExecutionSpec v1 is supported"
            )
    if not run_store._has_fields(spec, _SPEC_FIELDS):
        raise PublicError(
            "InvalidExecutionSpec", stage="validate", message="illegal ExecutionSpec",
            field_errors=["spec: fields must be exactly the ExecutionSpec fields"],
        )
    errors = [] if spec["schema_version"] == 1 and type(spec["schema_version"]) is int else [
        "schema_version: must be the integer 1"
    ]
    errors += run_store._attempt_errors({name: spec[name] for name in ATTEMPT_FIELDS})
    errors += _request_errors(spec)
    evaluation = [name for name in _EVALUATION_FIELDS if spec[name] is not None]
    if evaluation and len(evaluation) != len(_EVALUATION_FIELDS):
        errors.append("prepared_ref: evaluation fields must be all null or all set (V05)")
    errors += _input_errors(spec["inputs"])
    errors += _step_errors(spec["steps"], ordinary=not evaluation)
    try:
        _json_v1.encode(spec)
    except _json_v1.CanonicalError as exc:
        errors.append(f"spec: not canonical inferrsi-json-v1 ({exc.stage})")
    if errors:
        raise PublicError(
            "InvalidExecutionSpec", stage="validate", message="illegal ExecutionSpec",
            field_errors=errors,
        )
    unsupported = []
    if evaluation:
        unsupported.append("evaluation mode is not implemented in this slice")
    if spec["generation_record_ref"] is not None:
        unsupported.append("generation chaining is not implemented in this slice")
    request = spec["target_request"]
    if (request["target_id"], request["config_revision"]) != (
        target.target_id, target.config_revision
    ):
        unsupported.append("target_request does not name this local CPU target")
    if unsupported:
        raise PublicError(
            "UnsupportedOperation", stage="validate", message="; ".join(unsupported)
        )


def _error(code: str, stage: str, message: str) -> dict:
    return {"code": code, "stage": stage, "message": message, "retryable": False}


def _capabilities(spec: Mapping) -> tuple[list[dict], list[dict]]:
    """Capability checks and admission errors; a target never substitutes another resource."""
    resources = spec["resources"]
    requested = sorted(set(spec["required_capabilities"]) | set(resources["required_capabilities"]))
    checks = [
        {
            "capability": name,
            "status": "supported" if name == PROCESS_TREE else "unsupported",
            "source": "local-cpu-target",
            "reason": None if name == PROCESS_TREE else "not_provided_by_target",
        }
        for name in requested
    ]
    errors = [
        _error("capability_unsupported", "admission", f"capability {c['capability']} unavailable")
        for c in checks if c["status"] == "unsupported"
    ]
    if resources["cpu_count"] is not None and resources["cpu_count"] > (os.cpu_count() or 0):
        errors.append(_error("capacity_unavailable", "admission", "not enough local CPUs"))
    if resources["memory_bytes"] is not None:
        checks.append({"capability": "memory-reservation", "status": "unsupported",
                       "source": "local-cpu-target", "reason": "not_enforced_by_target"})
        errors.append(_error("capacity_unavailable", "admission", "memory is not reservable"))
    return checks, errors


def _budget(budget: Mapping) -> tuple[dict, list[dict]]:
    """H budget admission. Only free local CPU without a policy is admitted (V12)."""
    enforcement = [
        {"capability": name, "status": "unsupported", "source": "local-cpu-target",
         "reason": "budget_enforcement_unavailable"}
        for name in budget["required_enforcement"]
    ]
    reasons = []
    if budget["policy_ref"] is not None:
        reasons.append("budget_policy_unsupported")
    elif budget["dimensions"]:
        reasons.append("budget_policy_required")
    if enforcement:
        reasons.append("budget_enforcement_unavailable")
    admission = {
        "scope_id": budget["scope_id"],
        "policy_ref": copy.deepcopy(budget["policy_ref"]),
        "declared_by": budget["declared_by"],
        "decision": "rejected" if reasons else "admitted",
        # Nothing is reserved or charged by a free local CPU target.
        "dimensions": [
            {"dimension": d["dimension"], "unit": d["unit"], "limit": d["limit"],
             "reserved_capacity": None, "charged_capacity": None}
            for d in budget["dimensions"]
        ],
        "enforcement": enforcement,
        "reasons": reasons or ["free_local_cpu"],
    }
    errors = [_error(code, "admission", "budget admission rejected") for code in reasons]
    return admission, errors


@dataclass
class _Context:
    spec: Mapping
    namespace: str
    attempt_id: str
    workspace: Path
    captures: Path
    claimed_at: float
    retained: list
    observations: list
    # When H saw a cancellation before a step could start.
    cancel_seen_at: str | None = None

    def object_ref(self, path: Path, sha256: str, size: int, media_type: str) -> dict:
        """The store ArtifactRef of a captured file; it becomes valid with the commit."""
        ref = {
            "location": run_store.object_location(self.namespace, sha256),
            "sha256": sha256,
            "size_bytes": size,
            "media_type": media_type,
        }
        self.retained.append((ref, path))
        return ref


class _RetentionFailure(Exception):
    """H could not write its own capture or materialized copy before any start."""


def _capture_input(ctx: _Context, index: int, item: Mapping, target: LocalCpuTarget, reader):
    """Capture one source once into a private snapshot; return (BoundInput, check, snapshot)."""
    snapshot = ctx.captures / f"input-{index}"
    status, reasons, sha256, size, ref, route = "error", [], None, None, None, "local-file-capture"
    try:
        if item["snapshot_format"] != SNAPSHOT_FORMAT:
            # Directory manifests and other formats are refused, never captured as a file.
            raise input_binding.BindingError("snapshot_format_unsupported", "not file-v1")
        if item["source_namespace"] == "artifact":
            route = "artifact-reader"
            if reader is None:
                raise input_binding.BindingError("artifact_reader_unavailable", "no reader")
            stream = reader.open(item["source_ref"])
        else:
            root = getattr(target, f"{item['source_namespace']}_root")
            if root is None:
                raise input_binding.BindingError("source_namespace_unauthorized", "no root")
            source = Path(item["source"])
            if source.is_absolute():
                if not source.is_relative_to(root):
                    raise input_binding.BindingError("unsafe_path", "outside its root")
                source = source.relative_to(root)
            stream = input_binding.open_regular(Path(root), source.as_posix())
    except input_binding.BindingError as exc:
        reasons = [exc.code]
    except FileNotFoundError:
        reasons = ["source_missing"]
    except PublicError as exc:
        # An ArtifactReader refusal is never a verified identity (D021 section 1).
        reasons = [exc.code]
    except OSError:
        reasons = ["source_unreadable"]
    else:
        try:
            with stream:
                sha256, size = input_binding.copy_stream(stream, snapshot)
        except OSError as exc:
            raise _RetentionFailure("input snapshot write failed") from exc
        media = (
            item["source_ref"]["media_type"] if item["source_ref"] else _INPUT_MEDIA_TYPE
        )
        ref = ctx.object_ref(snapshot, sha256, size, media)
        expected = item["expected_sha256"]
        if expected is None:
            status, reasons = "not_performed", ["no_expected_sha256"]
        elif expected == sha256:
            status = "matched"
        else:
            status, reasons = "mismatched", ["actual_sha256_differs"]
    bound = {
        "role": item["role"],
        "retained_ref": ref,
        "actual_sha256": sha256,
        "snapshot_format": item["snapshot_format"],
        "captured_at": run_store.utc_now() if sha256 is not None else None,
        "attempt_id": ctx.attempt_id,
        "step_ids": [step["step_id"] for step in ctx.spec["steps"]],
        "materialized_path": None,
        "expected_sha256": item["expected_sha256"],
        "identity_status": status,
        "reasons": reasons,
    }
    check = {
        "check_id": "input_identity",
        "checker_revision": "1",
        "subject": item["role"],
        "phase": "preparing",
        "operation": None,
        "validation_scope": None,
        "attempt_id": ctx.attempt_id,
        "status": {"matched": "passed", "mismatched": "failed", "not_performed": "not_performed",
                   "error": "execution_error"}[status],
        "producer": {"kind": "harness_capture", "identity": _HARNESS, "revision": "1",
                     "control_domain": _CONTROL_DOMAIN, "capture_route": route},
        "evidence_refs": [] if ref is None else [ref],
        "artifact_schema": _INPUT_SCHEMA,
        "reasons": reasons,
    }
    return bound, check, (snapshot if sha256 is not None else None)


def _argv(step: Mapping) -> list[str] | None:
    """Resolve a supported entry on this host; None when it cannot be resolved."""
    if step["entrypoint_kind"] == "python_module":
        return [sys.executable, "-m", step["entrypoint"], *step["args"]]
    executable = shutil.which(step["entrypoint"])
    return None if executable is None else [executable, *step["args"]]


def _retain_stream(ctx: _Context, stream, name: str, media_type: str) -> dict | None:
    """Snapshot one produced file from its open stream; None when the copy fails."""
    target = ctx.captures / name
    try:
        with stream:
            sha256, size = input_binding.copy_stream(stream, target)
    except OSError:
        return None
    return ctx.object_ref(target, sha256, size, media_type)


def _observation(ctx: _Context, step_id: str, role: str, schema: dict, ref, status, reasons):
    item = {
        "role": role,
        "artifact": ref,
        "format_schema": copy.deepcopy(schema),
        "attempt_id": ctx.attempt_id,
        "step_id": step_id,
        "status": status,
        "reasons": reasons,
    }
    ctx.observations.append(item)
    return item


def _collect_outputs(ctx: _Context, index: int, step: Mapping, logs: tuple[Path, Path]):
    artifacts = []
    for role, log in zip(_STREAM_ROLES, logs):
        try:
            stream = open(log, "rb")
        except OSError:
            ref = None
        else:
            ref = _retain_stream(ctx, stream, f"step-{index}.{role}.retained", _STREAM_MEDIA_TYPE)
        artifacts.append(_observation(
            ctx, step["step_id"], role, _STREAM_SCHEMA, ref,
            "available" if ref else "unavailable", [] if ref else ["retention_failed"],
        ))
    for number, output in enumerate(step["outputs"]):
        ref, status, reasons = None, "missing", ["not_produced"]
        try:
            stream = input_binding.open_regular(ctx.workspace, output["path"])
        except FileNotFoundError:
            pass
        except input_binding.BindingError as exc:
            status, reasons = "invalid", [exc.code]
        except OSError:
            status, reasons = "unavailable", ["output_unreadable"]
        else:
            # Copy from the stream that passed the regular-file check, not a reopened path.
            ref = _retain_stream(
                ctx, stream, f"step-{index}.output-{number}", output["media_type"]
            )
            status, reasons = ("available", []) if ref else ("unavailable", ["retention_failed"])
        if status == "missing" and output["required"]:
            reasons = [*reasons, "required_output_missing"]
        artifacts.append(_observation(
            ctx, step["step_id"], output["role"], output["format_schema"], ref, status, reasons
        ))
    return artifacts


def _not_started_step(step: Mapping, reason: str) -> dict:
    return {
        "step_id": step["step_id"], "status": "not_started", "started_at": None,
        "ended_at": None, "elapsed_seconds": None, "exit_code": None, "artifacts": [],
        "reasons": [reason],
    }


_STEP_STATUS = {"completed": "exited", "failed": "exited", "timeout": "timed_out",
                "cancelled": "cancelled", "error": "execution_error"}


def _run_steps(ctx: _Context, argvs: list[list[str]], deadline: float, cancellation):
    """Run steps in fixed order, failing fast; return step records and per-step facts."""
    records, runs = [], []
    stop = None
    for index, (step, argv) in enumerate(zip(ctx.spec["steps"], argvs)):
        if stop is None and cancellation is not None and cancellation.is_set():
            stop = "cancelled"
            ctx.cancel_seen_at = run_store.utc_now()
        if stop is None and deadline <= time.monotonic():
            stop = "deadline_exhausted"
        if stop is not None:
            records.append(_not_started_step(step, stop))
            continue
        timeout = step["timeout_seconds"]
        bound = deadline if timeout is None else min(deadline, time.monotonic() + float(timeout))
        # A missing cwd is a recorded launch failure, not a directory H invents.
        logs = (ctx.captures / f"step-{index}.stdout", ctx.captures / f"step-{index}.stderr")
        run = local_process._supervise(
            argv, ctx.workspace / step["cwd"], os.environ.copy(), logs[0], logs[1], bound,
            cancellation=cancellation,
        )
        runs.append((step, run))
        if run["pid"] is None and run["status"] == "timeout":
            records.append(_not_started_step(step, "deadline_exhausted"))
            stop = "deadline_exhausted"
            continue
        status = _STEP_STATUS[run["status"]]
        exited = status == "exited"
        if run["pid"] is None:
            reasons = ["launch_failed"]
        elif status == "timed_out":
            reasons = ["deadline_exceeded" if bound >= deadline else "step_timeout"]
        elif status == "cancelled":
            reasons = [run["cancellation_source"]]
        elif status == "execution_error":
            reasons = ["supervision_failed"]
        else:
            reasons = []
        records.append({
            "step_id": step["step_id"],
            "status": status,
            "started_at": run["started_at"],
            "ended_at": run["ended_at"],
            "elapsed_seconds": (
                None if run["process_seconds"] is None else _decimal(run["process_seconds"])
            ),
            # A harness-terminated process has no exit code of its own.
            "exit_code": run["returncode"] if exited else None,
            "artifacts": (
                _collect_outputs(ctx, index, step, logs) if run["pid"] is not None else []
            ),
            "reasons": reasons,
        })
        if not (exited and run["returncode"] == 0):
            stop = "previous_step_failed"
    return records, runs


def _outcome(records: list[dict]) -> tuple[str, int | None]:
    """Record-level outcome from the first step that did not exit 0."""
    started = any(r["started_at"] is not None for r in records)
    for record in records:
        if record["status"] == "exited" and record["exit_code"] == 0:
            continue
        if record["status"] == "exited":
            return "exited", record["exit_code"]
        if record["status"] == "not_started":
            if record["reasons"] == ["cancelled"]:
                return "cancelled", None
            return ("timed_out" if started else "not_started"), None
        return record["status"], None
    return "exited", 0


def _cleanup(runs: list) -> tuple[dict, dict]:
    """Cleanup and lease facts of each started process domain, kept independent (V19)."""
    started = [(step, run) for step, run in runs if run["pid"] is not None]
    if not started:
        return (
            {"status": "not_needed", "termination_requested": False,
             "process_exit_confirmed": None, "reasons": []},
            {"applicability": "not_applicable", "leases": [], "reasons": ["no_resource_acquired"]},
        )
    exit_confirmed = all(run["returncode"] is not None for _, run in started)
    emptied = [run["domain_empty"] for _, run in started]
    if all(value is True for value in emptied) and exit_confirmed:
        status, reason = "confirmed", "process_domain_empty"
    elif any(value is False for value in emptied):
        status, reason = "failed", "process_domain_not_empty"
    else:
        status, reason = "unknown", "process_domain_unconfirmed"
    leases = [
        {
            "lease_id": f"{step['step_id']}/process-domain",
            "resource_id": "local-cpu",
            "control_domain": _CONTROL_DOMAIN,
            "owner": _HARNESS,
            "acquired_at": run["started_at"],
            "release_requested_at": run["ended_at"],
            "release_confirmed": run["domain_empty"],
            "release_confirmed_at": run["ended_at"] if run["domain_empty"] else None,
            "reasons": [
                {True: "process_domain_empty", False: "process_domain_not_empty",
                 None: "process_domain_unconfirmed"}[run["domain_empty"]]
            ],
        }
        for step, run in started
    ]
    cleanup = {
        "status": status,
        "termination_requested": any(run["termination_requested"] for _, run in started),
        "process_exit_confirmed": exit_confirmed,
        "reasons": [reason],
    }
    return cleanup, {"applicability": "applicable", "leases": leases, "reasons": []}


def _cancellation(ctx: _Context, runs: list) -> dict:
    for _, run in runs:
        if run["cancellation_requested_at"] is not None:
            return {"requested": True, "requested_at": run["cancellation_requested_at"],
                    "source": run["cancellation_source"]}
    if ctx.cancel_seen_at is not None:
        return {"requested": True, "requested_at": ctx.cancel_seen_at, "source": "caller"}
    return {"requested": False, "requested_at": None, "source": None}


def _usage(runs: list) -> list[dict]:
    started = [run for _, run in runs if run["pid"] is not None]
    if not started:
        return [{"dimension": "wall-time", "unit": "second", "amount": None, "currency": None,
                 "source": _USAGE_SOURCE, "completeness": "not_applicable", "observed_at": None,
                 "reasons": ["no_process_started"]}]
    seconds = [run["process_seconds"] for run in started if run["process_seconds"] is not None]
    return [{
        "dimension": "wall-time",
        "unit": "second",
        "amount": _decimal(sum(seconds)),
        "currency": None,
        "source": _USAGE_SOURCE,
        "completeness": "complete" if len(seconds) == len(started) else "partial",
        "observed_at": run_store.utc_now(),
        "reasons": [],
    }]


def _payload(ctx: _Context, **facts) -> dict:
    spec = ctx.spec
    payload = {
        "schema_version": 1,
        "request_id": spec["request_id"],
        "run_id": spec["run_id"],
        "attempt_id": spec["attempt_id"],
        "request_digest": facts["request_digest"],
        "owner": spec["owner"],
        "target_request": copy.deepcopy(spec["target_request"]),
        "target_binding": facts["target_binding"],
        "retry_of": spec["retry_of"],
        "retry_reason": spec["retry_reason"],
        "generation_record_ref": None,
        "prepared_ref": None,
        "protocol_digest": None,
        "operation": None,
        "validation_scope": None,
        "candidate": None,
        "record_version": 1,
        "recorded_at": run_store.utc_now(),
        "bound_inputs": facts["bound_inputs"],
        "phase": facts["phase"],
        "started": facts["started"],
        "side_effect_unknown": False,
        "process_outcome": facts["process_outcome"],
        "exit_code": facts["exit_code"],
        "elapsed_seconds": _decimal(time.monotonic() - ctx.claimed_at),
        "steps": facts["steps"],
        "cancellation": facts["cancellation"],
        "cleanup": facts["cleanup"],
        "artifacts": ctx.observations,
        "checks": facts["checks"],
        "budget_admission": facts["budget_admission"],
        "usage": facts["usage"],
        "resource_leases": facts["resource_leases"],
        "errors": facts["errors"],
    }
    return payload


def _target_binding(target: LocalCpuTarget, capability_checks, runtime) -> dict:
    return {
        "target_id": target.target_id,
        "config_revision": target.config_revision,
        "executor_version": EXECUTOR_VERSION,
        "runtime_bindings_by_step": runtime,
        "control_domain": _CONTROL_DOMAIN,
        "capability_checks": capability_checks,
    }


def _refusal(ctx, digest, binding, admission, bound, checks, errors, reason) -> dict:
    """The fixed not_started encoding for a registered refusal that acquired nothing."""
    cleanup, leases = _cleanup([])
    return _payload(
        ctx, request_digest=digest, target_binding=binding, bound_inputs=bound,
        phase="finished", started=False, process_outcome="not_started", exit_code=None,
        steps=[_not_started_step(step, reason) for step in ctx.spec["steps"]],
        cancellation={"requested": False, "requested_at": None, "source": None},
        cleanup=cleanup, checks=checks, budget_admission=admission, usage=_usage([]),
        resource_leases=leases, errors=errors,
    )


def _run_claimed(ctx, target, digest, reader, deadline, cancellation) -> dict:
    capability_checks, errors = _capabilities(ctx.spec)
    admission, budget_errors = _budget(ctx.spec["budget"])
    errors += budget_errors
    binding = _target_binding(target, capability_checks, [])
    if errors:
        return _refusal(ctx, digest, binding, admission, [], [], errors, "admission_rejected")
    argvs = [_argv(step) for step in ctx.spec["steps"]]
    if None in argvs:
        errors = [_error("entrypoint_unavailable", "binding", "an executable entry is not found")]
        return _refusal(ctx, digest, binding, admission, [], [], errors, "entrypoint_unavailable")
    try:
        ctx.workspace.mkdir(parents=True)
    except FileExistsError:
        errors = [_error("workspace_exists", "binding", "the attempt workspace already exists")]
        return _refusal(ctx, digest, binding, admission, [], [], errors, "workspace_exists")
    except OSError as exc:
        raise _RetentionFailure("workspace creation failed") from exc
    captured = [
        _capture_input(ctx, index, item, target, reader)
        for index, item in enumerate(ctx.spec["inputs"])
    ]
    bound = [item[0] for item in captured]
    checks = [item[1] for item in captured]
    failed = [b for b in bound if b["identity_status"] in ("mismatched", "error")]
    if failed:
        # H02-3: the actual binding is refused after registration and before any start.
        errors = [
            _error("input_identity_mismatch" if b["identity_status"] == "mismatched"
                   else "input_unavailable", "binding", f"input {b['role']} not bound")
            for b in failed
        ]
        return _refusal(ctx, digest, binding, admission, bound, checks, errors, "input_refused")
    for item, (record, _, snapshot) in zip(ctx.spec["inputs"], captured):
        try:
            input_binding.materialize(
                snapshot, ctx.workspace / item["materialized_path"], record["actual_sha256"],
                record["retained_ref"]["size_bytes"],
            )
        except (OSError, input_binding.BindingError) as exc:
            raise _RetentionFailure("input materialization failed") from exc
        record["materialized_path"] = item["materialized_path"]
    steps, runs = _run_steps(ctx, argvs, deadline, cancellation)
    outcome, exit_code = _outcome(steps)
    cleanup, leases = _cleanup(runs)
    launched = {step["step_id"] for step, run in runs if run["pid"] is not None}
    binding["runtime_bindings_by_step"] = [
        {
            "step_id": step["step_id"],
            "runtime_role": step["runtime_role"],
            "executable": argv[0],
            "entrypoint": step["entrypoint"],
            "entrypoint_revision": step["entrypoint_revision"],
            # Ordinary command mode resolves no entry digest (T37 is a later slice).
            "code_sha256": None,
            "argv": argv,
            "environment_identity": None,
        }
        for step, argv in zip(ctx.spec["steps"], argvs)
        if step["step_id"] in launched
    ]
    codes = {"timed_out": "timeout", "cancelled": "cancelled",
             "execution_error": "execution_error", "not_started": "deadline_exhausted"}
    run_errors = (
        [_error(codes[outcome], "running", f"process outcome {outcome}")]
        if outcome in codes else []
    )
    return _payload(
        ctx, request_digest=digest, target_binding=binding, bound_inputs=bound,
        # V18: finished only once every started process domain is confirmed closed.
        phase="finished" if cleanup["status"] in ("not_needed", "confirmed")
        else "recovery_required",
        started=bool(launched), process_outcome=outcome, exit_code=exit_code, steps=steps,
        cancellation=_cancellation(ctx, runs), cleanup=cleanup, checks=checks,
        budget_admission=admission, usage=_usage(runs), resource_leases=leases,
        errors=run_errors,
    )


def execute(
    store: run_store.RunStore,
    target: LocalCpuTarget,
    spec: Mapping,
    *,
    cancellation=None,
    artifact_reader=None,
) -> dict:
    """H ``execute``: register, admit, bind, run and commit one ordinary command request."""
    validate(spec, target)
    digest = run_store.request_digest(spec)
    attempt = {name: copy.deepcopy(spec[name]) for name in ATTEMPT_FIELDS}
    # Re-entry is decided by the store before any binding or start (V14 / D021 section 3).
    claimed = store.claim(attempt, digest)
    if isinstance(claimed, run_store.CommittedRecord):
        return run_store.flatten(claimed, run_store.utc_now())
    claimed_at = time.monotonic()
    deadline = claimed_at + _deadline_seconds(spec["deadline_utc"])
    ctx = _Context(
        spec=copy.deepcopy(dict(spec)),
        namespace=store.namespace,
        attempt_id=spec["attempt_id"],
        workspace=target.work_root / "workspaces" / spec["output_root"],
        captures=target.work_root / "captures" / run_store.attempt_hash(spec["attempt_id"]),
        claimed_at=claimed_at,
        retained=[],
        observations=[],
    )
    with claimed as claim:
        try:
            try:
                ctx.captures.mkdir(parents=True)
            except OSError as exc:
                raise _RetentionFailure("capture directory creation failed") from exc
            payload = _run_claimed(ctx, target, digest, artifact_reader, deadline, cancellation)
        except _RetentionFailure as exc:
            # Raised only before any start: no start and no record (figure 6).
            shutil.rmtree(ctx.captures, ignore_errors=True)
            raise PublicError(
                "ExecutionPersistenceError", stage="bind", attempt_id=ctx.attempt_id,
                started=False, message=f"{exc}: {run_store._describe(exc.__cause__)}",
            ) from exc
        try:
            committed = claim.commit(payload, ctx.retained)
        finally:
            # Snapshots are retained by the commit or reported lost; the copies are scratch.
            shutil.rmtree(ctx.captures, ignore_errors=True)
    return run_store.flatten(committed, run_store.utc_now())
