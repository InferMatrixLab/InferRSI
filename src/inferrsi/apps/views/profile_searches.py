"""Relate each profile capture to the knowledge searches it names."""

from __future__ import annotations

from inferrsi.harness.records.timing_clock import recorded_time


def pre_profile_searches(capture: dict, retrievals: dict) -> list[dict]:
    """Link only explicitly named, verified searches completed before this capture."""
    links = []
    for key in capture.get("context_ids", []):
        search = retrievals.get(key)
        if not search or search["state"] != "verified":
            state = "unverified"
        else:
            try:
                searched_at = recorded_time(search.get("captured_at"))
                before = searched_at < recorded_time(capture.get("started_at"))
            except ValueError:
                state = "unknown_time"
            else:
                state = "verified" if before else "not_before"
        links.append({"context_id": key, "state": state})
    return links
