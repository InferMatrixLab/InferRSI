"""Harness: command execution and RunStore records, the AB/BA runner, optimization
sessions and their records. Verdict labels come from contracts; reports are injected."""

from inferrsi.contracts.claim import Verdict, parse_verdict

__all__ = ["Verdict", "parse_verdict"]
