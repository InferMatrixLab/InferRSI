"""The positive finite metric contract shared by benchmark result adapters."""

import math


def read_metric(result: dict, key: str) -> float:
    value = result
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"missing metric: {key}")
        value = value[part]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metric {key} must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"metric {key} must be finite and positive")
    return float(value)
