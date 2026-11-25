"""Retain cleanup observations independently of execution and assessment receipts."""

import hashlib
import json
import time
import uuid
from pathlib import Path

from .atomic_json import durable_write_json
from .launch_records import observe
from .records.evidence import bounded_record_bytes

_CLEAR = {"not_spawned", "recorded_empty", "observed_empty"}
_FIELDS = (
    "state", "argv_sha256", "platform", "intent_at", "boot_id", "pid_namespace",
    "spawned", "pid", "process_group_id", "started_at", "ended_at", "status", "domain_empty",
)


def _entries(root, directory, prefix):
    try:
        if any(parent.is_symlink() for parent in (directory, *directory.parents)
               if parent.is_relative_to(root) and parent != root):
            raise ValueError("Unsafe launch directory")
        return {
            path.relative_to(root).as_posix() for path in directory.iterdir()
            if path.name.startswith(prefix) and path.suffix == ".json"
        }
    except FileNotFoundError:
        return set()


def _launch(root, path):
    raw, state = bounded_record_bytes(root, path, 16 * 1024)
    stage = Path(path).stem
    result = {"path": path, "stage": stage, "sha256": None, "observation": state}
    if raw is None:
        return result
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        record = json.loads(raw)
        if (not isinstance(record, dict) or record.get("schema_version") != 1
                or record.get("stage") != stage):
            raise ValueError("Invalid launch record")
    except (ValueError, RecursionError):
        result["observation"] = "invalid_record"
    else:
        result["record"] = {key: record[key] for key in _FIELDS if key in record}
        result["observation"] = observe(record)
    return result


def scan(root, attempt, *, receipt_present, earlier=()):
    """Observe every stage before the coordinator can start another child."""
    directory = root / attempt
    paths = {entry["path"] for entry in earlier if entry["path"]}
    entries = []
    for location, prefix in ((directory, "protocol-"), (directory / "execution", "launch-")):
        try:
            paths.update(_entries(root, location, prefix))
        except (OSError, ValueError):
            entries.append({"path": None, "stage": prefix.rstrip("-"), "sha256": None,
                            "observation": "unreadable_directory"})
    entries.extend(_launch(root, path) for path in sorted(paths))
    # Legacy attempts with an execution receipt may have no launch files.
    if not entries and not receipt_present:
        entries.append({"path": None, "stage": "unknown", "sha256": None,
                        "observation": "no_launch_record"})
    return entries


def retained(root, reference, attempt):
    raw, _ = bounded_record_bytes(root, reference["path"], 1024 * 1024)
    if raw is None or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("Retained recovery record changed")
    record = json.loads(raw)
    if (record.get("schema_version") != 1 or record.get("session") != root.name
            or record.get("attempt") != attempt):
        raise ValueError("Retained recovery record belongs to another attempt")
    return record


def _write(root, path, attempt, **detail):
    full = root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    durable_write_json(full, {"schema_version": 1, "session": root.name, "attempt": attempt,
                              "observed_at": time.time(), **detail})
    return {"path": path, "sha256": hashlib.sha256(full.read_bytes()).hexdigest()}


def capture(root, attempt, launches, receipt_present):
    path = f"{attempt}/recovery.json"
    if (root / path).exists():
        path = f"{attempt}/recovery-{uuid.uuid4().hex}.json"
    return _write(root, path, attempt, launches=launches, execution_receipt_present=receipt_present)


def _identity(entry):
    return entry["path"], entry["stage"], entry["sha256"], entry["observation"]


def unconfirmed(root, state, attempt, launches):
    acknowledged = set()
    for reference in state.get("recovery_confirmations", ()):
        if reference["attempt"] == attempt:
            proof = retained(root, reference, attempt)
            acknowledged.update(_identity(entry) for entry in proof["confirmed_stages"])
    return [entry for entry in launches if entry["observation"] not in _CLEAR and (
        entry["observation"] in ("live", "unreadable_directory")
        or _identity(entry) not in acknowledged
    )]


def confirm(root, state, gate, launches, blocked, *, manual):
    if any(entry["observation"] == "live" for entry in launches):
        raise ValueError("Cannot confirm cleanup while a recorded process group is live")
    attempt = gate["attempt"]
    ref = _write(root, f"recoveries/confirm-{uuid.uuid4().hex}.json", attempt,
                 recovery_sha256=gate["recovery_sha256"],
                 basis="manual" if manual else "observed_empty", launches=launches,
                 confirmed_stages=blocked if manual else [])
    state.setdefault("recovery_confirmations", []).append({**ref, "attempt": attempt})
