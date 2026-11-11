"""Explicit, caller-reviewed optimization narratives and bounded artifact reads.

The record is a caller assertion, not proof that an agent consumed its context.
It is never populated from raw requests, logs, or the process environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

MAX_OPTIMIZATION_TRACE_BYTES = 2 * 1024 * 1024
ATTRIBUTION = "caller_declared_not_proof_of_model_consumption"
_STATES = {"complete", "partial", "redacted"}
_KINDS = {"observation", "attempt", "decision"}
_OUTCOMES = {"succeeded", "failed", "inconclusive", "skipped", "not_recorded"}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}")


class TraceError(ValueError):
    """A fixed error code that never includes caller-supplied text."""


def _object(value: object, fields: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise TraceError("invalid_format")
    return value


def _string(value: object, *, required: bool = False) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise TraceError("invalid_format")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise TraceError("invalid_format")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise TraceError("invalid_format") from exc
    return value


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        raise TraceError("invalid_format")
    return [_string(item) for item in value]


def _section(value: object, fields: set[str]) -> dict:
    section = _object(value, fields | {"state", "missing_reason"})
    state = section["state"]
    if not isinstance(state, str) or state not in _STATES:
        raise TraceError("invalid_format")
    reason = _string(section["missing_reason"])
    if state != "complete" and not reason.strip():
        raise TraceError("missing_explanation")
    if state == "complete" and reason.strip():
        raise TraceError("invalid_format")
    return section


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise TraceError("invalid_format")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise TraceError("invalid_format")


def parse_optimization_trace(raw: bytes) -> dict:
    """Validate one complete UTF-8 JSON snapshot, without truncating any text."""
    if not isinstance(raw, bytes):
        raise TraceError("invalid_format")
    if len(raw) > MAX_OPTIMIZATION_TRACE_BYTES:
        raise TraceError("too_large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, TraceError):
            raise
        raise TraceError("invalid_format") from exc
    if not isinstance(value, dict):
        raise TraceError("invalid_format")
    required = {"schema_version", "reviewed_by_caller", "campaign_id", "candidate_id",
                "context", "search_space", "steps", "summary"}
    if not required <= set(value) or set(value) - (required | {"round", "run_id"}):
        raise TraceError("invalid_format")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise TraceError("invalid_format")
    if value["reviewed_by_caller"] is not True:
        raise TraceError("not_reviewed")
    for key in ("campaign_id", "candidate_id"):
        if not isinstance(value[key], str) or not _IDENTIFIER.fullmatch(value[key]):
            raise TraceError("invalid_format")
    round_number = value.get("round")
    if round_number is not None and (type(round_number) is not int or round_number < 1):
        raise TraceError("invalid_format")
    run_id = value.get("run_id")
    if run_id is not None and (not isinstance(run_id, str) or not _IDENTIFIER.fullmatch(run_id)):
        raise TraceError("invalid_format")

    context = _section(value["context"], {"text", "queries", "sources"})
    _string(context["text"], required=context["state"] == "complete")
    _strings(context["queries"])
    if not isinstance(context["sources"], list):
        raise TraceError("invalid_format")
    for source in context["sources"]:
        source = _object(source, {"ref", "revision", "locator"})
        _string(source["ref"], required=True)
        _string(source["revision"])
        _string(source["locator"])

    space = _section(value["search_space"], {"items"})
    if not isinstance(space["items"], list):
        raise TraceError("invalid_format")
    space_ids = set()
    for item in space["items"]:
        item = _object(item, {"id", "description"})
        identity = _string(item["id"], required=True)
        _string(item["description"], required=True)
        if identity in space_ids:
            raise TraceError("invalid_format")
        space_ids.add(identity)

    steps = _section(value["steps"], {"items"})
    if not isinstance(steps["items"], list):
        raise TraceError("invalid_format")
    previous = 0
    for item in steps["items"]:
        required_step = {"sequence", "kind", "action", "motivation", "outcome", "result",
                         "search_id"}
        if (not isinstance(item, dict) or not required_step <= set(item)
                or set(item) - (required_step | {"event_ref"})):
            raise TraceError("invalid_format")
        sequence = item["sequence"]
        if type(sequence) is not int or sequence <= previous:
            raise TraceError("invalid_format")
        previous = sequence
        if (not isinstance(item["kind"], str) or item["kind"] not in _KINDS
                or not isinstance(item["outcome"], str) or item["outcome"] not in _OUTCOMES):
            raise TraceError("invalid_format")
        _string(item["action"], required=True)
        _string(item["motivation"], required=True)
        _string(item["result"])
        search_id = _string(item["search_id"])
        if search_id and space["state"] == "complete" and search_id not in space_ids:
            raise TraceError("invalid_format")
        if "event_ref" in item:
            event = _object(item["event_ref"], {"source", "line", "sha256"})
            if (event["source"] not in ("events", "agent_trace") or type(event["line"]) is not int
                    or not 0 < event["line"] <= 10_000_000
                    or not isinstance(event["sha256"], str)
                    or not _SHA256.fullmatch(event["sha256"])):
                raise TraceError("invalid_format")

    summary = _section(value["summary"], {"successes", "failures", "limitations"})
    for key in ("successes", "failures", "limitations"):
        _strings(summary[key])
    return {**value, "round": round_number, "run_id": run_id, "attribution": ATTRIBUTION}


def assemble_optimization_trace(template: bytes, context: bytes) -> bytes:
    """Insert an explicitly reviewed UTF-8 context into a trace template.

    This does not inspect an agent request or assert that a model consumed the
    context. The template and context must both be reviewed by the caller.
    """
    if (not isinstance(template, bytes) or not isinstance(context, bytes)
            or len(template) > MAX_OPTIMIZATION_TRACE_BYTES
            or len(context) > MAX_OPTIMIZATION_TRACE_BYTES):
        raise TraceError("too_large")
    try:
        value = json.loads(template.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_constant)
        text = context.decode("utf-8")
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, TraceError):
            raise
        raise TraceError("invalid_format") from exc
    if not isinstance(value, dict) or value.get("reviewed_by_caller") is not True:
        raise TraceError("not_reviewed")
    section = value.get("context")
    if not isinstance(section, dict) or section.get("text") != "":
        raise TraceError("invalid_format")
    section["text"] = text
    try:
        result = (json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TraceError("invalid_format") from exc
    parse_optimization_trace(result)
    return result


def _read(root: Path, raw_path: object) -> tuple[bytes | None, dict]:
    if not isinstance(raw_path, str) or not raw_path:
        return None, _missing("not_collected")
    # The campaign root is the trust boundary. A single filename avoids
    # resolving attacker-replaceable intermediate directories.
    if not _IDENTIFIER.fullmatch(raw_path) or raw_path in {".", ".."}:
        return None, _missing("unsafe_path")
    try:
        root = Path(root).resolve()
        path = root / raw_path
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not before.st_ino:
            return None, _missing("unsafe_path")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or not opened.st_ino
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                return None, _missing("unsafe_path")
            raw = stream.read(MAX_OPTIMIZATION_TRACE_BYTES + 1)
    except (ValueError, RuntimeError):
        return None, _missing("unsafe_path")
    except FileNotFoundError:
        return None, _missing("file_absent")
    except OSError:
        return None, _missing("unreadable")
    if len(raw) > MAX_OPTIMIZATION_TRACE_BYTES:
        return None, _missing("too_large")
    return raw, {"kind": "optimization_trace", "state": "present", "path": raw_path,
                 "sha256": hashlib.sha256(raw).hexdigest()}


def _missing(reason: str) -> dict:
    return {"kind": "optimization_trace", "state": "missing", "missing_reason": reason}


def read_optimization_trace(root: Path, reference: object, *, campaign_id: object,
                            candidate_id: object, round_number: object,
                            unique_candidate: bool, round_ambiguous: bool = False,
                            run_id: object = None,
                            require_hash: bool = True) -> tuple[dict | None, dict]:
    """Read, hash, validate and bind the exact same bounded snapshot."""
    if not isinstance(reference, dict):
        return None, _missing("not_collected")
    if reference.get("state") == "missing":
        reason = reference.get("missing_reason")
        allowed = {"not_collected", "file_absent", "redacted", "not_applicable"}
        result = _missing(reason if isinstance(reason, str) and reason in allowed
                          else "not_collected")
        digest = reference.get("sha256")
        if isinstance(digest, str) and _SHA256.fullmatch(digest):
            result["sha256"] = digest.lower()
        return None, result
    if reference.get("state") not in (None, "present"):
        return None, _missing("invalid_format")
    digest = reference.get("sha256")
    if require_hash and (not isinstance(digest, str) or not _SHA256.fullmatch(digest)):
        return None, _missing("hash_not_recorded")
    raw, ref = _read(root, reference.get("path"))
    if raw is None:
        return None, ref
    if require_hash and digest.lower() != ref["sha256"]:
        return None, _missing("hash_mismatch")
    try:
        value = parse_optimization_trace(raw)
    except TraceError as exc:
        return None, _missing(str(exc))
    if unique_candidate is not True or round_ambiguous:
        return None, _missing("identity_ambiguous")
    if (not isinstance(campaign_id, str) or not isinstance(candidate_id, str)
            or value["campaign_id"] != campaign_id or value["candidate_id"] != candidate_id
            or (value["round"] is not None and value["round"] != round_number)
            or (value["run_id"] is not None and value["run_id"] != run_id)):
        return None, _missing("identity_mismatch")
    return value, ref
