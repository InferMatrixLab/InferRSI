#!/usr/bin/env python3
"""Reduce supplied decode records offline; no engine, byte authentication or verdict.

Example: python summarize_decode_records.py --input records.json --source-commit <SHA>
Original stdlib helper; not an importer or executor of a Project Maya source runner.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_SAMPLES = 10_000
TOP_FIELDS = {"schema_version", "source_commit", "family", "metric", "controls_sha256", "samples"}
SAMPLE_FIELDS = {
    "variant",
    "phase",
    "execution",
    "tokens",
    "decode_ms",
    "drafts_offered",
    "drafts_accepted",
}
MEASURE_FIELDS = ("tokens", "decode_ms", "drafts_offered", "drafts_accepted")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def integer(value: object, minimum: int) -> bool:
    return type(value) is int and value >= minimum


def positive(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def hex_id(value: object, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value: str) -> None:
    raise ValueError("nonfinite JSON constant")


def summarize(document: object, source_commit: str) -> dict:
    require(hex_id(source_commit, 40), "expected source must be lowercase 40-hex")
    require(isinstance(document, dict) and set(document) == TOP_FIELDS, "invalid top-level fields")
    require(type(document["schema_version"]) is int, "schema version must be an integer")
    require(document["schema_version"] == 1, "unsupported schema version")
    require(
        document["source_commit"] == source_commit, "supplied source differs from expected source"
    )
    require(document["family"] in ("glm", "ds4", "mm3", "qwen"), "unknown family")
    require(document["metric"] == "engine-decode", "only engine-decode records are supported")
    require(hex_id(document["controls_sha256"], 64), "controls identifier must be lowercase 64-hex")
    samples = document["samples"]
    require(isinstance(samples, list) and 0 < len(samples) <= MAX_SAMPLES, "invalid sample count")
    for sample in samples:
        require(isinstance(sample, dict) and set(sample) == SAMPLE_FIELDS, "invalid sample fields")
        require(sample["variant"] in ("baseline", "candidate"), "unknown variant")
        require(sample["phase"] in ("warmup", "measured"), "unknown phase")
        require(
            sample["execution"] in ("completed", "skipped", "failed", "blocked"),
            "unknown execution",
        )
        if sample["execution"] != "completed":
            require(
                all(sample[key] is None for key in MEASURE_FIELDS),
                "noncompleted metrics must be null",
            )
            continue
        require(integer(sample["tokens"], 1), "completed token count must be a positive integer")
        require(positive(sample["decode_ms"]), "completed decode_ms must be positive and finite")
        for key in ("drafts_offered", "drafts_accepted"):
            require(integer(sample[key], 0), "draft counts must be nonnegative integers")
        require(sample["drafts_accepted"] <= sample["drafts_offered"], "accepted exceeds offered")

    variants = {}
    for variant in ("baseline", "candidate"):
        rows = [row for row in samples if row["variant"] == variant]
        measured = [row for row in rows if row["phase"] == "measured"]
        complete = [row for row in measured if row["execution"] == "completed"]
        tokens = sum(row["tokens"] for row in complete)
        duration = sum(row["decode_ms"] for row in complete)
        offered = sum(row["drafts_offered"] for row in complete)
        accepted = sum(row["drafts_accepted"] for row in complete)
        rates = [row["tokens"] / row["decode_ms"] * 1000 for row in complete]
        require(math.isfinite(duration), "aggregate duration overflow")
        require(all(math.isfinite(rate) for rate in rates), "per-sample rate overflow")
        rate = tokens / duration * 1000 if duration else None
        require(rate is None or math.isfinite(rate), "aggregate rate overflow")
        median = statistics.median(rates) if rates else None
        require(median is None or math.isfinite(median), "median rate overflow")
        variants[variant] = {
            "warmup_records": len(rows) - len(measured),
            "execution_counts_all_phases": dict(
                sorted(Counter(row["execution"] for row in rows).items())
            ),
            "execution_counts_measured": dict(
                sorted(Counter(row["execution"] for row in measured).items())
            ),
            "completed_measured_samples": len(complete),
            "tokens": tokens,
            "decode_ms": duration,
            "token_weighted_tok_s": rate,
            "median_sample_tok_s": median,
            "draft_acceptance_fraction": accepted / offered if offered else None,
        }
    baseline = variants["baseline"]["token_weighted_tok_s"]
    candidate = variants["candidate"]["token_weighted_tok_s"]
    change = candidate / baseline - 1 if baseline and candidate is not None else None
    require(change is None or math.isfinite(change), "relative rate overflow")
    return {
        "schema_version": 1,
        "source_commit": source_commit,
        "family": document["family"],
        "metric": "engine-decode",
        "variants": variants,
        "completed_subset_relative_rate_change": change,
        "scope": ("supplied records only; no native execution, "
                  "byte authentication, quality or verdict"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="normalized caller-owned JSON")
    parser.add_argument(
        "--source-commit", required=True, help="expected lowercase 40-hex source identity"
    )
    args = parser.parse_args()
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "input exceeds 8 MiB parser bound")
        document = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
        result = summarize(document, args.source_commit)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        parser.exit(
            2, "invalid supplied records: check schema, identities, counts and finite durations\n"
        )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
