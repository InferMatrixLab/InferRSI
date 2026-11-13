"""Normalize observed usage and preserve unknown costs across runs."""

import math


def normalize_usage(usage) -> dict | None:
    """Keep valid token observations; malformed containers/fields remain unknown.

    The original provider event remains in the trace for diagnosis. This view is
    shared by live parsing and retained-result reporting, including older records.
    """
    if not isinstance(usage, dict):
        return None
    return {key: value if type(value) is int and value >= 0 else None
            for key, value in usage.items()
            if key in ("input_tokens", "output_tokens", "cached_input_tokens")}


def usage_totals(trials: list[dict]) -> dict:
    """Unknown and invalid metrics stay unknown; cached input is not added twice."""
    result = {"calls": len(trials), "cost": None}
    usage = [normalize_usage(t["observations"].get("usage")) for t in trials]
    for field in ("input_tokens", "output_tokens", "cached_input_tokens"):
        values = [(u or {}).get(field) for u in usage]
        result[field] = sum(values) if values and all(
            type(value) is int and value >= 0 for value in values) else None
    for field, values in (
        ("tool_calls", [t["observations"].get("tool_calls") for t in trials]),
        ("elapsed_seconds", [t.get("elapsed_seconds") for t in trials]),
    ):
        result[field] = sum(values) if values and all(
            type(value) in (int, float) and math.isfinite(value) and value >= 0
            for value in values) else None
    tokens = [result["input_tokens"], result["output_tokens"]]
    result["total_tokens"] = sum(tokens) if None not in tokens else None
    return result
