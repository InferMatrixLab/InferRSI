#!/usr/bin/env python3
"""Check selected consistency fields of a saved Lily benchmark JSON record.

Adapted from perplexityai/pplx-garden lily/benchmarks/run_matrix.py's
validate_lily_report idea (Apache-2.0), at the owning skill's source provenance.
Changes: standalone offline JSON audit, stricter values/identity/digest checks;
no model, MLX imports, subprocesses, machine surveys, network or verdict.

Example: python audit_benchmark_record.py --report record.json
  --source-id <40-hex-source-id> --decode-steps 64 [--diagnostic]
Consistency of supplied fields does not authenticate execution or file hashes.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


def positive(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def audit(document: object, source_id: str, steps: int, diagnostic: bool = False) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_id) or type(steps) is not int or steps <= 0:
        raise ValueError("expected a lowercase full source SHA and positive decode count")
    if (
        not isinstance(document, dict)
        or type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("expected a schema-version-1 report object")
    meta = document.get("meta", {})
    workload = document.get("workload", {})
    if not isinstance(meta, dict) or not isinstance(workload, dict):
        raise ValueError("meta and workload must be objects")
    if meta.get("engine") != "lily" or meta.get("source_id") != source_id:
        raise ValueError("engine/source identity mismatch")
    if workload.get("gpu_timing_diagnostic") is not diagnostic:
        raise ValueError("diagnostic mode mismatch")
    if (
        type(workload.get("decode_steps")) is not int
        or workload["decode_steps"] != steps
        or type(workload.get("prompt_len")) is not int
        or workload["prompt_len"] <= 0
    ):
        raise ValueError("workload counts mismatch")
    results = document.get("results")
    if not isinstance(results, dict):
        raise ValueError("results must be an object")
    for metric in ("prefill", "decode"):
        value = results.get(metric)
        if not isinstance(value, dict) or not all(
            positive(value.get(field)) for field in ("wall_secs", "tok_s")
        ):
            raise ValueError("times and rates must be finite positive numbers")
    decode = results["decode"]
    intervals, tokens = decode.get("step_wall_secs"), decode.get("token_ids")
    if not isinstance(intervals, list) or len(intervals) != steps or not all(
        positive(value) for value in intervals
    ):
        raise ValueError("decode intervals mismatch")
    if not isinstance(tokens, list) or len(tokens) != steps or not all(
        type(token) is int and 0 <= token <= 0xFFFFFFFF for token in tokens
    ):
        raise ValueError("decode token IDs mismatch")
    digest = 0xCBF29CE484222325
    for token in tokens:
        digest = ((digest ^ token) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    if decode.get("token_digest") != f"{digest:016x}":
        raise ValueError("token digest mismatch")
    passes, lookahead = decode.get("gpu_passes"), decode.get("lookahead_gpu_pass")
    if diagnostic:
        if not isinstance(passes, list) or len(passes) != steps or not isinstance(
            lookahead, dict
        ):
            raise ValueError("diagnostic GPU record shape mismatch")
    elif passes != [] or lookahead is not None:
        raise ValueError("production record contains diagnostic GPU timing")
    return {
        "record_consistent": True,
        "source_id": source_id,
        "decode_steps": steps,
        "diagnostic": diagnostic,
        "scope": "supplied metadata only; no native execution or byte authentication",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--decode-steps", required=True, type=int)
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(
            json.loads(args.report.read_text(encoding="utf-8")),
            args.source_id,
            args.decode_steps,
            args.diagnostic,
        )
    except (OSError, ValueError, TypeError, OverflowError) as error:
        parser.exit(2, f"record inconsistent: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
