"""Minimal bench harness stub for CI smoke (no external deps)."""

from __future__ import annotations

from inferrsi.claim import Verdict
from inferrsi.runspec import RunSpec


def dry_run_verdict(spec: RunSpec) -> Verdict:
    """Placeholder runner: INCONCLUSIVE until a real harness records evidence."""
    if not spec.revision or spec.revision.startswith("<"):
        return Verdict.INCONCLUSIVE
    return Verdict.INCONCLUSIVE
