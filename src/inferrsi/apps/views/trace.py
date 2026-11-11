"""Query retained trace events for the monitoring views."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ...harness.records import STAGES, fields
from ...harness.records.fields import _number, _relative_location

PHASE_STAGES = {
    "source_snapshot": "execution",
    "measurement": "execution",
    "quality_validation": "validation",
}
EVENT_TYPES = {
    "agent.context", "agent.request", "agent.response", "agent.tool",
    "agent.completed", "agent.failed", "agent.protocol", "agent.reservation",
    "edit.artifact", "edit.protocol", "edit.slot",
}


def _event_details(record: dict) -> dict:
    """Retain structured trace metadata, never arbitrary payloads or messages."""
    details = {}
    for key in ("request", "requests", "request_bytes", "bytes", "revision"):
        value = record.get(key)
        if type(value) is int and 0 <= value <= 1_000_000_000_000:
            details[key] = value
    for key in ("request_sha256", "result_sha256", "artifact_sha256", "sha256", "manifest_sha256",
                "actor_sha256", "check_receipt", "benchmark_receipt"):
        value = record.get(key)
        if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value):
            details[key] = value.lower()
    usage = record.get("usage")
    if isinstance(usage, dict):
        keys = ("input_tokens", "output_tokens", "cached_input_tokens")
        values = {key: usage[key] for key in keys
                  if type(usage.get(key)) is int and 0 <= usage[key] <= 1_000_000_000_000}
        if values:
            details["usage"] = values
    if record.get("client_kind") in ("anthropic-messages-agent-v1",
                                     "anthropic-messages-full-context-v1",
                                     "anthropic-messages-edit-check-v1"):
        details["client_kind"] = record["client_kind"]
    files = record.get("files")
    if isinstance(files, list):
        entries = []
        for file in files[:50]:
            if not isinstance(file, dict):
                continue
            path = _relative_location(file.get("path"))
            size, digest = file.get("bytes"), file.get("sha256")
            if (path and type(size) is int and 0 <= size <= 1_000_000_000_000
                    and isinstance(digest, str) and re.fullmatch(r"[a-fA-F0-9]{64}", digest)):
                entries.append({"path": path, "bytes": size, "sha256": digest.lower()})
        if entries:
            details["files"] = entries
    reason = record.get("reason")
    reasons = {"timeout", "interrupted", "agent_error", "edit_agent_error",
               "readiness_or_worker_error", "request_bytes_limit", "input_token_limit",
               "output_token_limit", "tool_call_limit", "invalid_tool_call",
               "candidate_bytes_limit",
               "credential_echo", "credential_in_payload", "deadline_exceeds_frozen_limit",
               "feedback_bytes_limit", "incompatible_response", "invalid_candidate",
               "invalid_credential_shape", "invalid_or_premature_answer", "invalid_response_json",
               "invalid_tool_utf8", "invalid_visible_feedback", "invalid_workspace_file",
               "missing_agent_tool_call", "missing_task", "protected_workspace_changed",
               "provider_transport_error", "request_allocation_unavailable",
               "request_authorization_denied", "request_limit", "response_bytes_limit",
               "revision_retention_error", "stale_or_missing_receipt", "task_not_read",
               "tool_read_limit", "transport_error", "unexposed_path", "unknown_usage",
               "unsupported_tool", "visible_callback_error", "workspace_symlink"}
    if isinstance(reason, str) and (reason in reasons
                                    or re.fullmatch(r"http_[1-5][0-9]{2}", reason)):
        details["reason"] = reason
    for key, allowed in (("stop_reason", {"tool_use", "end_turn", "max_tokens", "stop_sequence",
                                          "pause_turn", "refusal"}),
                         ("state", {"running", "completed", "failed", "crashed", "timeout",
                                    "cancelled"}),
                         ("verdict", {"PASS", "FAIL", "INCONCLUSIVE"})):
        value = record.get(key)
        if isinstance(value, str) and value in allowed:
            details[key] = value
    path = _relative_location(record.get("path"))
    if path is not None:
        details["path"] = path
    artifact = _relative_location(record.get("artifact"))
    if artifact is not None:
        details["artifact"] = artifact
    receipt = record.get("receipt")
    expected_kind = {"run_visible_checks": "checks", "run_visible_benchmark": "benchmark"}.get(
        record.get("name") if isinstance(record.get("name"), str) else None
    )
    if isinstance(receipt, dict) and expected_kind and receipt.get("kind") == expected_kind:
        summary = {"kind": expected_kind}
        digest = receipt.get("receipt_sha256")
        if isinstance(digest, str) and re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            summary["receipt_sha256"] = digest.lower()
        feedback = receipt.get("feedback")
        if isinstance(feedback, dict):
            for key in ("verdict", "quality_verdict"):
                value = feedback.get(key)
                if isinstance(value, str) and value in {"PASS", "FAIL", "INCONCLUSIVE"}:
                    summary[key] = value
            improvement = _number(feedback.get("improvement_pct"))
            if improvement is not None:
                summary["improvement_pct"] = improvement
            checks = feedback.get("checks")
            if (isinstance(checks, dict) and len(checks) <= 1000
                    and all(type(value) is bool for value in checks.values())):
                summary["checks_total"] = len(checks)
                summary["checks_passed"] = sum(checks.values())
            for key in ("baseline_values", "candidate_values"):
                values = feedback.get(key)
                if isinstance(values, list) and len(values) <= 100:
                    numbers = [_number(value) for value in values]
                    if all(value is not None and value > 0 for value in numbers):
                        summary[key] = numbers
        details["recorded_receipt"] = summary
    return details


def _read_events(
    path: Path, root: Path, expected: dict | None = None, unique_candidate: bool = False,
) -> tuple[list[dict], list[int], str, dict[str, list[int]], dict]:
    """Read events for the view, which resolves declared references before exposing them."""
    unlinked = {"unlinked": [], "mismatched": []}
    raw, ref = fields._snapshot(root, path, "events")
    if raw is None:
        state = "unsafe" if ref["missing_reason"] == "unsafe_path" else "missing"
        return [], [], state, unlinked, ref
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        return [], [], "corrupt", unlinked, {**ref, "state": "missing", "missing_reason": "corrupt"}
    events, corrupt = [], []
    for line_number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("event is not an object")
        except (json.JSONDecodeError, ValueError):
            corrupt.append(line_number)
            continue
        link_state = "linked"
        if expected is not None:
            identity = {key: record.get(key) for key in (
                "campaign_id", "candidate_id", "run_id", "round"
            )}
            valid = (type(record.get("schema_version")) is int
                     and record["schema_version"] == 1
                     and all(isinstance(identity[key], str) and identity[key]
                             for key in ("campaign_id", "candidate_id"))
                     and all(isinstance(expected[key], str) and expected[key]
                             for key in ("campaign_id", "candidate_id"))
                     and unique_candidate
                     and (identity["run_id"] is None or (
                         isinstance(identity["run_id"], str) and identity["run_id"]
                         and expected["run_id"] is not None))
                     and (identity["round"] is None or (
                         type(identity["round"]) is int and identity["round"] > 0
                         and expected["round"] is not None))
                     and record.get("stage") in STAGES
                     and isinstance(record.get("time"), str) and bool(record["time"]))
            if any(value is not None and expected[key] is not None and value != expected[key]
                   for key, value in identity.items()):
                unlinked["mismatched"].append(line_number)
                continue
            if not valid:
                unlinked["unlinked"].append(line_number)
                link_state = "unlinked"
        phase = record.get("phase")
        if phase not in (*PHASE_STAGES, "complete", "crashed"):
            phase = None
        kind = record.get("type")
        event_type = kind if isinstance(kind, str) and kind in EVENT_TYPES else None
        stage = None
        if phase is not None or event_type is not None:
            stage = (record.get("stage") if record.get("stage") in STAGES
                     else PHASE_STAGES.get(phase))
        time = record.get("time")
        if not isinstance(time, str) or not re.fullmatch(r"[0-9TtZz:+.\-]{10,40}", time):
            time = None
        trial = record.get("trial")
        events.append({
            "line": line_number, "time": time, "phase": phase, "type": event_type,
            "stage": stage, "side": record.get("side")
            if record.get("side") in ("baseline", "candidate") else None,
            "trial": trial if isinstance(trial, int) and not isinstance(trial, bool)
            and 0 < trial <= 1_000_000 else None,
            "tool": record.get("name") if record.get("name") in (
                "read_file", "submit_answer", "submit_candidate", "write_candidate",
                "run_visible_checks", "run_visible_benchmark",
            ) else None,
            "details": _event_details(record),
            "_declared_refs": record.get("refs") if isinstance(record.get("refs"), list) else [],
            "_link_state": link_state,
        })
    return events, corrupt, "present", unlinked, ref
