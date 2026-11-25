"""Read-only interpretation of the Issue-label cutover and the hourly writer handoff."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

_MANIFEST = Path(__file__).resolve().parents[1] / ".github" / "labels.json"
LABELS = json.loads(_MANIFEST.read_text(encoding="utf-8"))
AREAS = frozenset(row["name"] for row in LABELS if row["group"] == "area")


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("an explicit time zone is required")
    return result.astimezone(timezone.utc)


def merge_event(events: list[dict], merge_sha: str, pr_url: str) -> dict:
    matches = [e for e in events if e.get("event") == "merged"]
    if len(matches) != 1:
        raise ValueError("cutover needs exactly one GitHub merged timeline event")
    event = matches[0]
    if not event.get("id") or not merge_sha or event.get("commit_id") != merge_sha:
        raise ValueError("merge event ID and merged PR's matching commit are required")
    at = instant(event["created_at"]).isoformat().replace("+00:00", "Z")
    return {
        "at": at,
        "event_id": event["id"],
        "sha": merge_sha,
        "url": f"{pr_url}#event-{event['id']}",
    }


def replay_pr_kind(obj: dict, events: list[dict], snapshot: dict, cutover: dict) -> dict:
    """Reconstruct one object's kinds at T and isolate additions strictly after T."""
    url = obj["html_url"]
    result = {"at_cutover": None, "new_additions": [], "replayed": [], "pending": []}
    missing = result["pending"]
    end = instant(cutover["at"])
    created = instant(obj["created_at"])
    if created > end:
        start, kinds = created, set()
    else:
        start_text = snapshot.get("at")
        if not start_text:
            missing.append("exact timestamp of the original snapshot")
            return result
        start = instant(start_text)
        if start >= end:
            raise ValueError("baseline snapshot must precede the merge event")
        if created > start:
            kinds = set()  # The object did not yet exist, independently of cohort membership.
        else:
            row = snapshot.get("objects", {}).get(str(obj["number"]))
            if not isinstance(row, list):
                missing.append("original object-level snapshot row")
                return result
            if not all(isinstance(v, str) and v.startswith("kind:") for v in row):
                raise ValueError("a snapshot row must list exact kind labels")
            kinds = set(row)
    at_cut = set(kinds)
    seen = {}
    ordered = []
    for event in events:
        op = event.get("event")
        label = (event.get("label") or {}).get("name", "")
        if op not in ("labeled", "unlabeled") or not label.startswith("kind:"):
            continue
        if not event.get("id") or not event.get("created_at"):
            missing.append("timestamp and event ID for each kind change")
            continue
        when = instant(event["created_at"])
        key = event["id"]
        details = when, op, label
        if key in seen:
            if seen[key] != details:
                missing.append(f"conflicting records for event {key}")
            continue
        seen[key] = details
        if when < start:
            continue
        ordered.append((when, key, op, label))
    # GitHub IDs identify events. They do not order events across timelines.
    # Preserve the order from the paginated object timeline within each second.
    for when, key, op, label in sorted(ordered, key=lambda row: row[0]):
        if when == end or (
            created <= start
            and snapshot.get("at")
            and when == start
            and created <= instant(snapshot["at"])
        ):
            missing.append(f"event {key} shares a boundary second; ordering is unknown")
            continue
        if when < created:
            missing.append(f"event {key} predates the object")
            continue
        add = op == "labeled"
        if (label in kinds) == add:
            missing.append(f"event {key} disagrees with the reconstructed prior state")
        if add:
            kinds.add(label)
        else:
            kinds.discard(label)
        entry = {
            "id": key,
            "at": when.isoformat(),
            "event": op,
            "label": label,
            "url": f"{url}#event-{key}",
        }
        if when < end:
            at_cut = set(kinds)
            result["replayed"].append(entry)
        elif add:
            result["new_additions"].append(entry)
    observed = {label["name"] for label in obj["labels"] if label["name"].startswith("kind:")}
    if kinds != observed:
        missing.append("timeline and current label readback disagree")
    if missing:
        result["new_additions"] = []  # No count from an unresolved replay.
    else:
        result["at_cutover"] = sorted(at_cut)
    return result


def hourly_area_plan_current(plan: dict, writer: dict) -> bool:
    """Can this queued area addition still be considered after the handoff?

    Re-evaluate immediately before *each* send or retry. A new generation after
    the freeze invalidates every old plan. This predicate issues no requests.
    """
    return (
        writer.get("mode") == "resumed"
        and bool(writer.get("generation"))
        and plan.get("generation") == writer["generation"]
        and plan.get("operation") == "add"
        and plan.get("label") in AREAS
        and bool(plan.get("area_evidence"))
    )


def handoff_gaps(receipt: dict, cutover: dict) -> list[str]:
    """Validate an operator's counters and timestamps, preserving missing evidence."""
    gaps = []
    freeze = receipt.get("freeze") or {}
    stop_time = freeze.get("at")
    if (
        not stop_time
        or instant(stop_time) >= instant(cutover["at"])
        or not public_link(freeze.get("url"))
        or freeze.get("scope") != "all-label-writes"
        or not freeze.get("invalidated_generation")
        or any(
            type(freeze.get(k)) is not int or freeze[k] != 0
            for k in ("queued", "retries", "in_flight")
        )
    ):
        gaps.append(
            "dated pre-merge operator record: all writes paused, old generation "
            "invalidated, queues, retries and in-flight traffic drained"
        )
    trial = receipt.get("trial") or {}
    timestamp = trial.get("at")
    if (
        not timestamp
        or instant(timestamp) <= instant(cutover["at"])
        or not public_link(trial.get("url"))
        or not trial.get("run_id")
        or not re.fullmatch(
            r"https://github\.com/InferMatrixLab/InferRSI/pull/\d+", trial.get("pr_url", "")
        )
        or not re.fullmatch(r"[0-9a-f]{40}", trial.get("head", ""))
        or not public_link(trial.get("readback_url"))
        or trial.get("readback_url") == trial.get("url")
        or trial.get("existing_open_pr") is not True
        or trial.get("inspected") is not True
        or type(trial.get("remote_label_requests")) is not int
        or trial["remote_label_requests"] != 0
        or trial.get("kinds_before") != []
        or trial.get("kinds_after") != []
    ):
        gaps.append(
            "dated post-merge operator dry run on an existing open PR without kind: "
            "inspection, zero remote label writes and independent readback"
        )
    return gaps


def public_link(value) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
