"""Recorded handoff to a host's native fresh-session tools.

The host creates and observes the conversation. This module never launches an
Agent CLI, infers task success, or claims to enforce a native host's deadline.
"""

import json
import math
import time
import uuid
from pathlib import Path

from ..infra.artifacts import atomic_write_json, digest, file_lock, sha256
from .usage import normalize_usage

TERMINAL = {"completed", "failed", "cancelled"}
OBSERVED_STATES = {"running", "needs_attention", *TERMINAL}
MAX_EXPORT_BYTES = 2 * 1024 * 1024


def _locked(root):
    return file_lock(root / ".session.lock")


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 16384:
        raise ValueError(f"{name} must be a nonempty bounded string")
    return value


def _export(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_EXPORT_BYTES + 1)
    if len(raw) > MAX_EXPORT_BYTES:
        raise ValueError("Host export exceeds 2 MiB")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Host export must be a JSON object")
    return raw, value


def _retain(root, raw):
    name = f"receipts/{uuid.uuid4().hex}.json"
    (root / "receipts").mkdir(exist_ok=True)
    (root / name).write_bytes(raw)
    return {"path": name, "sha256": sha256(root / name)}


def _load(root):
    request = json.loads((root / "request.json").read_text(encoding="utf-8"))
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    if digest(request) != state["request_digest"]:
        raise ValueError("Frozen Agent request changed")
    if sha256(root / "prompt.md") != request["prompt_sha256"]:
        raise ValueError("Frozen Agent prompt changed")
    for source in request["frozen_inputs"]:
        if sha256(source["path"]) != source["sha256"]:
            raise ValueError("Frozen Agent input changed")
    for record in state["receipts"]:
        if sha256(root / record["path"]) != record["sha256"]:
            raise ValueError("Retained host receipt changed")
    for artifact in state["artifacts"]:
        if sha256(root / artifact["path"]) != artifact["sha256"]:
            raise ValueError("Retained Agent artifact changed")
    return request, state


def _view(root, request, state):
    expired = time.time() >= request["deadline"]
    return {
        "job": str(root), "job_id": request["job_id"], "state": state["state"],
        "native_session": state["native_session"], "request": request,
        "last_observation": state["last_observation"], "artifacts": state["artifacts"],
        "deadline_exceeded": expired, "deadline_enforcement": "native_host_not_enforced",
        "usage": state["usage"], "usage_scope": "latest_observation_session_total",
        "last_observed_usage": state.get("last_observed_usage"),
        "cost": None, "task_acceptance": "not_assessed",
        "next_action": (
            "inspect_native_host_and_stop_if_still_running" if expired
            and state["state"] not in TERMINAL else {
                "prepared": "dispatch_then_use_native_fresh_session_tool",
                "dispatching": "inspect_original_host_call_and_bind_without_relaunch",
                "running": "observe_native_session_and_record_receipt",
                "needs_attention": "inspect_native_session",
                "completed": "independently_verify_delivered_artifacts",
                "failed": "inspect_failure_and_retained_artifacts",
                "cancelled": "inspect_cancellation_and_retained_artifacts",
            }[state["state"]]
        ),
    }


def prepare(root: Path, *, prompt: str, workspace: Path, title: str,
            max_seconds: float, model=None, effort=None, plugin_ref=None,
            task_reference=None, frozen_inputs=()) -> dict:
    """Freeze explicit task/configuration, without inheriting a parent conversation."""
    root, workspace = root.resolve(), workspace.resolve()
    if not workspace.is_dir():
        raise ValueError("Agent workspace must be an existing directory")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > MAX_EXPORT_BYTES:
        raise ValueError("Agent prompt must be nonempty and at most 2 MiB")
    _text(title, "title")
    for name, value in (("model", model), ("effort", effort), ("plugin_ref", plugin_ref)):
        if value is not None:
            _text(value, name)
    if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or max_seconds <= 0):
        raise ValueError("max-minutes must be finite and positive")
    inputs = [{"path": str(Path(path).resolve()), "sha256": sha256(path)}
              for path in frozen_inputs]
    root.mkdir(parents=True, exist_ok=False)
    (root / "prompt.md").write_bytes(prompt.encode("utf-8"))
    request = {
        "schema_version": 1, "job_id": uuid.uuid4().hex, "host": "current",
        "context_mode": "fresh", "title": title, "workspace": str(workspace),
        "model": model, "effort": effort, "plugin_ref": plugin_ref,
        "configuration_source": "caller_requested_not_host_verified",
        "created_at": time.time(), "deadline": time.time() + max_seconds,
        "prompt_sha256": sha256(root / "prompt.md"), "task_reference": task_reference,
        "frozen_inputs": inputs,
    }
    state = {
        "request_digest": digest(request), "state": "prepared", "native_session": None,
        "receipts": [], "artifacts": [], "last_observation": None, "usage": None,
    }
    atomic_write_json(root / "request.json", request)
    atomic_write_json(root / "state.json", state)
    return _view(root, request, state)


def status(root: Path) -> dict:
    root = root.resolve()
    with _locked(root):
        return _view(root, *_load(root))


def dispatch(root: Path) -> dict:
    """Reserve exactly one native creation attempt before calling the host tool."""
    root = root.resolve()
    with _locked(root):
        request, state = _load(root)
        if state["state"] != "prepared":
            return {**_view(root, request, state), "may_create": False}
        if time.time() >= request["deadline"]:
            raise ValueError("Agent request deadline exhausted before dispatch")
        state["state"] = "dispatching"
        state["dispatched_at"] = time.time()
        atomic_write_json(root / "state.json", state)
        return {
            **_view(root, request, state), "may_create": True,
            "handoff": {
                "operation": "native_create_fresh_session", "context_mode": "fresh",
                "title": request["title"], "workspace": request["workspace"],
                "model": request["model"], "effort": request["effort"],
                "prompt": (root / "prompt.md").read_text(encoding="utf-8"),
                "instructions": (
                    "Use the current host's new-session tool once; do not fork or inherit "
                    "this conversation. Map only supported, authorized settings. Save the "
                    "native tool receipt and bind its confirmed session ID. If delivery is "
                    "uncertain, inspect the original host operation; never create a replacement. "
                    "If the host lacks this capability, report unsupported without CLI fallback."
                ),
            },
        }


def bind(root: Path, *, host: str, session_id: str, receipt: Path, host_id=None) -> dict:
    """Associate a confirmed native ID with its opaque, caller-exported tool receipt."""
    root = root.resolve()
    native = {"host": _text(host, "host"), "session_id": _text(session_id, "session_id"),
              "host_id": _text(host_id, "host_id") if host_id is not None else None}
    raw, _ = _export(receipt)
    with _locked(root):
        request, state = _load(root)
        if state["native_session"] is not None:
            if state["native_session"] != native:
                raise ValueError("Agent job is already bound to another native session")
            return _view(root, request, state)
        if state["state"] != "dispatching":
            raise ValueError("Dispatch must be recorded before native session binding")
        record = _retain(root, raw)
        state["receipts"].append({**record, "kind": "caller_exported_native_creation"})
        state["native_session"], state["state"] = native, "running"
        atomic_write_json(root / "state.json", state)
        return _view(root, request, state)


def record(root: Path, *, observation: Path, artifacts=()) -> dict:
    """Retain an explicit host observation; completed execution is not task acceptance."""
    root = root.resolve()
    raw, value = _export(observation)
    if value.get("state") not in OBSERVED_STATES:
        raise ValueError("Unknown native observation state")
    if not isinstance(value.get("native_receipt"), dict) or not value["native_receipt"]:
        raise ValueError("Observation requires the exported native_receipt")
    usage = value.get("usage")
    if usage is not None:
        normalized = normalize_usage(usage)
        if (value.get("usage_scope") != "session_total" or not normalized
                or normalized.get("input_tokens") is None
                or normalized.get("output_tokens") is None
                or any(item is None for item in normalized.values())
                or normalized.get("cached_input_tokens", 0) > normalized["input_tokens"]):
            raise ValueError("Usage must be a valid session_total with input and output tokens")
        usage = normalized
    with _locked(root):
        request, state = _load(root)
        native = state["native_session"]
        if native is None:
            if (state["state"] != "dispatching" or value["state"] != "failed"
                    or value.get("creation_outcome") != "not_created"
                    or value.get("session_id") is not None or usage is not None or artifacts):
                raise ValueError("Unbound job requires a definite not_created failure receipt")
            _text(value.get("host"), "host")
        elif any(value.get(key) != native[key] for key in ("host", "session_id", "host_id")):
            raise ValueError("Observation does not identify the bound native session")
        if state["state"] in TERMINAL and value["state"] != state["state"]:
            raise ValueError("A terminal native session cannot change state in this job")
        previous_usage = (state.get("last_observed_usage") or {}).get("usage")
        if usage is not None and previous_usage is not None and any(
            usage[key] < previous_usage[key] for key in ("input_tokens", "output_tokens")
        ):
            raise ValueError("Cumulative native usage cannot decrease")
        prepared = []
        workspace = Path(request["workspace"])
        for source in artifacts:
            source = Path(source).resolve()
            if not source.is_relative_to(workspace) or not source.is_file():
                raise ValueError("Artifact must be a file inside the declared workspace")
            if source.is_relative_to(root):
                raise ValueError("Native job records are not Agent deliverables")
            prepared.append((source, source.read_bytes()))
        record = _retain(root, raw)
        state["receipts"].append({**record, "kind": "caller_exported_native_observation"})
        for source, data in prepared:
            (root / "artifacts").mkdir(exist_ok=True)
            name = f"artifacts/{uuid.uuid4().hex}-{source.name}"
            (root / name).write_bytes(data)
            state["artifacts"].append({
                "source": source.relative_to(workspace).as_posix(),
                "path": name, "sha256": sha256(root / name),
            })
        state["state"], state["last_observation"] = value["state"], record
        # A previous partial meter must not become a completed session's final cost.
        state["usage"] = usage
        if usage is not None:
            state["last_observed_usage"] = {"usage": usage, "receipt": record}
        atomic_write_json(root / "state.json", state)
        return _view(root, request, state)
