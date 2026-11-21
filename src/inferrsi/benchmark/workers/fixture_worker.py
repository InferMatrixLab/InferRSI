"""Standalone p1-cpu-smoke@1 worker; no inference quality or performance-gain claim."""

import json
import sys
import time
from pathlib import Path

INPUT_BYTES = b"InferRSI CPU evidence smoke task\n"


def baseline():
    return str(sum(INPUT_BYTES)).encode("ascii") + b"\n"


def _milliseconds(nanoseconds):
    # Integer conversion preserves canonical decimals without rounding or clamping.
    return (f"{nanoseconds // 1_000_000}.{nanoseconds % 1_000_000:06d}"
            .rstrip("0").rstrip("."))


def _samples(candidate_path, clock):
    rows, complete = [], True
    for sample_id, role, round_ in (("A1", "baseline", 1), ("B1", "candidate", 1),
                                    ("B2", "candidate", 2), ("A2", "baseline", 2)):
        try:
            start = clock()
            baseline() if role == "baseline" else candidate_path.read_bytes()
            end = clock()
        except (OSError, ArithmeticError, ValueError):
            complete = False
            continue
        if type(start) is not int or type(end) is not int or end <= start:
            complete = False
            continue
        rows.append({"sample_id": sample_id, "role": role, "round": round_,
                     "value": _milliseconds(end - start), "unit": "ms"})
    return rows if complete else None


def evaluate(candidate_path, *, clock=None):
    """Grade exact bytes, then measure all four operations independently of C."""
    candidate_path = Path(candidate_path)
    try:
        candidate = candidate_path.read_bytes()
    except OSError:
        grader = None
    else:
        matched = candidate == baseline()
        grader = {"status": "passed" if matched else "failed",
                  "reasons": [] if matched else ["response_mismatch"]}
    samples = _samples(candidate_path, time.perf_counter_ns if clock is None else clock)
    return {"schema_version": 1, "grader": grader, "samples": samples}


def main():
    if len(sys.argv) != 3:
        return 2
    report = evaluate(sys.argv[1])
    output = Path(sys.argv[2])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
