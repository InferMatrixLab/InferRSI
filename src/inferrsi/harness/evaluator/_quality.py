"""Interpret scorer output in the unit declared by the frozen quality gate."""

import math
from decimal import Decimal

UNSPECIFIED_QUALITY_UNITS = ("", "unknown", "unspecified", "n/a")


def quality_unit_declared(unit) -> bool:
    return isinstance(unit, str) and unit.strip().lower() not in UNSPECIFIED_QUALITY_UNITS


def quality_score_in_unit(score, reported_unit, approved_unit):
    """Return the score in the frozen unit; only proportional scales can cross units."""
    if not (quality_unit_declared(reported_unit) and quality_unit_declared(approved_unit)):
        raise ValueError("quality_unit_mismatch")
    if reported_unit == approved_unit:
        return score
    scales = {"%": 2, "percent": 2, "fraction": 0, "ratio": 0}
    if reported_unit not in scales or approved_unit not in scales:
        raise ValueError("quality_unit_mismatch")
    converted = float(Decimal(str(score)).scaleb(scales[approved_unit] - scales[reported_unit]))
    if not math.isfinite(converted):
        raise ValueError("quality_unit_mismatch")
    return converted
