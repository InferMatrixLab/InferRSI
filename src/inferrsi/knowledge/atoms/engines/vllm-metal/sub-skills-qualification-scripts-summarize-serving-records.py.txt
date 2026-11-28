#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline descriptive token accounting; no inference or benchmark execution.

Adapts the token-count summary idea in tools/avg_gen_length.py without its
MLX/model/dataset dependencies. Usage: python summarize_serving_records.py run.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


def number(value, *, integer=False, positive=False):
    if isinstance(value, bool) or not isinstance(value, int if integer else (int, float)):
        raise ValueError("numeric field has wrong type")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("numeric field outside range")
    return value


def summarize(data: dict) -> dict:
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "source_commit", "controls_sha256", "metric", "samples"
    }:
        raise ValueError("invalid record keys")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported schema")
    for name, length in (("source_commit", 40), ("controls_sha256", 64)):
        if not isinstance(data[name], str) or not re.fullmatch("[a-f0-9]{%d}" % length,
                                                            data[name]):
            raise ValueError("invalid identity syntax")
    if data["metric"] not in ("http-serving", "offline-generation", "kernel"):
        raise ValueError("metric must declare the actual measurement scope")
    rows = data["samples"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("requires 1..10000 samples")
    result = {}
    for variant in ("baseline", "candidate"):
        selected, counts, tokens, duration, warmup = [], Counter(), 0, 0.0, 0
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "variant", "phase", "execution", "output_tokens", "duration_ms"
            }:
                raise ValueError("invalid sample keys")
            if row["variant"] not in ("baseline", "candidate") or row["phase"] not in (
                "warmup", "measured"
            ) or row["execution"] not in ("completed", "failed", "blocked", "cancelled"):
                raise ValueError("invalid sample classification")
            completed = row["execution"] == "completed"
            if completed:
                number(row["output_tokens"], integer=True)
                number(row["duration_ms"], positive=True)
            elif row["output_tokens"] is not None or row["duration_ms"] is not None:
                raise ValueError("incomplete rows require null measurements")
            if row["variant"] != variant:
                continue
            if row["phase"] == "warmup":
                warmup += 1
                continue
            selected.append(row)
            counts[row["execution"]] += 1
            if completed:
                tokens += row["output_tokens"]
                duration += row["duration_ms"]
        if not selected:
            raise ValueError("both variants require measured execution records")
        rate = tokens * 1000 / duration if duration else None
        if not math.isfinite(duration) or (rate is not None and not math.isfinite(rate)):
            raise ValueError("aggregate exceeds finite arithmetic range")
        result[variant] = {
            "execution_counts": dict(counts), "warmup_records_excluded": warmup,
            "completed_output_tokens": tokens, "completed_duration_ms": duration,
            "completed_subset_tokens_per_second": rate,
        }
    return {
        "metric": data["metric"], "variants": result,
        "evidence_state": "INCONCLUSIVE",
        "native_verification": "not_established_by_this_helper",
        "scope": "descriptive completed subsets only; no comparable-work, identity-byte, "
                 "quality, route, failure-adjusted throughput or campaign verdict verification",
    }


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576:
            raise ValueError("input exceeds 1 MiB")
        result = summarize(json.loads(raw, object_pairs_hook=unique_object))
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        parser.error("invalid bounded measurement record; see the documented schema")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
