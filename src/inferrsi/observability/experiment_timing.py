"""Elapsed experiment time from run events and an optional caller-reviewed timing ledger."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import timezone
from pathlib import Path

from .dashboard_data import _text
from .dashboard_workflow import _timestamp
from .optimization_log import _read_regular


def _utc(value):
    stamp = _timestamp(value)
    try:
        return stamp.astimezone(timezone.utc).isoformat() if stamp else None
    except (ValueError, OverflowError):
        return None


def _step(kind, label, start=None, end=None, *, seconds=None, basis, **fields):
    start, end = _utc(start), _utc(end)
    if start and end and seconds is None and end >= start and basis != "event":
        seconds = (_timestamp(end) - _timestamp(start)).total_seconds()
    return dict(kind=kind, label=label, start=start, end=end, seconds=seconds,
                basis=basis, **fields)


def _reviewed_steps(root: Path, campaign_id: str, digest: str) -> list[dict]:
    raw = _read_regular(root / "experiment-timing.json", 2 << 20)
    if len(raw) > 2 << 20 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("timing ledger failed verification")
    doc = json.loads(raw)
    if (not isinstance(doc, dict) or doc.get("schema_version") != 1
            or doc.get("campaign_id") != campaign_id or not isinstance(doc.get("steps"), list)
            or len(doc["steps"]) > 5000):
        raise ValueError("invalid timing ledger")
    steps = []
    for line, item in enumerate(doc["steps"], 1):
        if not isinstance(item, dict) or item.get("kind") not in (
            "experiment", "operation", "model_call", "profile_request",
        ):
            raise ValueError("invalid step kind")
        start, end = item.get("start"), item.get("end")
        if ((start is not None and not _utc(start)) or (end is not None and not _utc(end))
                or not (start or end) or (start and end and _timestamp(start) > _timestamp(end))):
            raise ValueError("invalid step bounds")
        keys = ["label", "basis", "actor"] + (["model"] if item["kind"] == "model_call" else [])
        if not all(isinstance(item.get(k), str) and 0 < len(item[k]) <= 240 for k in keys):
            raise ValueError("missing reviewed labels")
        n = item.get("round")
        if n is not None and (type(n) is not int or n < 1):
            raise ValueError("invalid round")
        fields = {k: _text(item[k]) for k in keys}
        steps.append(_step(item["kind"], start=start, end=end, round=n,
                           evidence=f"experiment-timing.json · {line}", **fields))
    return steps


def _agent_steps(row):
    pairs = defaultdict(lambda: defaultdict(list))
    for event in row["events"]:
        kind = event["type"]
        if not kind:
            continue
        number = event["details"].get("request")
        if kind in ("agent.request", "agent.response") and number is not None:
            pairs[event["source"], number][kind].append(event)
        elif event.get("source") == "agent_trace" or kind in ("agent.request", "agent.response"):
            yield _step("agent_event", event.get("tool") or kind, event["time"], basis="event",
                        round=row["round"], actor=row["candidate_id"],
                        evidence=f"{event['source']}:{event['line']}")
    for (source, number), pair in pairs.items():
        starts, ends = pair["agent.request"], pair["agent.response"]
        # Reused request numbers cannot identify one call.
        if len(starts) > 1 or len(ends) > 1:
            for event in sorted(starts + ends, key=lambda e: e["line"]):
                yield _step("agent_event", event["type"], event["time"], basis="event",
                            evidence=f"{source}:{event['line']}", round=row["round"],
                            actor=row["candidate_id"])
            continue
        start = starts[0] if starts else {}
        end = ends[0] if ends else {}
        a, b = start.get("time"), end.get("time")
        ordered = bool(_utc(a) and _utc(b) and _utc(b) >= _utc(a)
                       and start["line"] < end["line"])
        yield _step("model_call", f"#{number}", a if ordered or not end else None, b,
                    model=end.get("details", {}).get("provider_model")
                    or start.get("details", {}).get("provider_model"), actor=row["candidate_id"],
                    round=row["round"], basis="request_response" if ordered else "incomplete",
                    evidence=source + ":" + ",".join(str(e["line"]) for e in starts + ends))


def experiment_timing(view, root):
    steps = []
    ledger = "absent"
    digest = view.get("experiment_timing_sha256")
    if digest is not None:
        try:
            if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
                raise ValueError("invalid timing digest")
            steps.extend(_reviewed_steps(root, view["campaign_id"], digest))
            ledger = "verified"
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            ledger = "unavailable"

    for row in view["candidates"]:
        round_fields = {"round": row["round"], "actor": row["candidate_id"]}
        for n in row.get("run_workflow", {}).get("nodes", []):
            steps.append(_step("runner", n["kind"], n["start"], n["end"], seconds=n["seconds"],
                               basis=n["duration_source"] or "event", side=n["side"],
                               trial=n["trial"], state=n["state"], **round_fields))
        events = row["events"]
        starts = [e for e in events if e["source"] == "events" and e["phase"] == "source_snapshot"]
        ends = [e for e in events if e["source"] == "events"
                and e["phase"] in ("complete", "crashed")]
        if len(starts) == len(ends) == 1:
            steps.append(_step("run", "run", starts[0]["time"], ends[0]["time"],
                               basis="run_events", **round_fields))
        steps.extend(_agent_steps(row))

    story = view.get("story") or {}
    for retrieval in story.get("retrievals", []):
        if retrieval["state"] == "verified":
            steps.append(_step("knowledge", retrieval["context_id"], end=retrieval["captured_at"],
                               basis="capture_saved"))
    for version in story.get("versions", []):
        if version.get("state") == "present":
            steps.append(_step("review", f"v{version['version']}", end=version.get("recorded_at"),
                               basis="log_saved"))
    for c in view.get("profile_captures", []):
        if c.get("started_at"):
            steps.append(_step("profile", c["title"], c["started_at"], round=c["round"],
                               basis="profile_start"))

    steps.sort(key=lambda s: s["start"] or s["end"] or "~")
    stamps = [t for step in steps for t in (step["start"], step["end"]) if t]
    return {"steps": steps, "ledger": ledger,
            "first": min(stamps, default=None), "last": max(stamps, default=None)}
