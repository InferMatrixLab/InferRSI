"""Claim contract types (rules only; campaign SHAs live in acceptance issues)."""

from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    """Campaign verdict labels — no other public labels."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


def parse_verdict(value: str) -> Verdict:
    """Parse a verdict string; raises ValueError if not a contract label."""
    try:
        return Verdict(value.upper())
    except ValueError:
        raise ValueError(
            f"Invalid verdict '{value}'; expected one of PASS, FAIL, INCONCLUSIVE"
        ) from None


def claim_requires_pinned_shas(verdict: Verdict) -> bool:
    """PASS claims require pinned baseline and candidate SHAs in the evidence issue."""
    return verdict is Verdict.PASS
