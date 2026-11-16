# SPDX-License-Identifier: Apache-2.0
"""Enumerate pinned mistral.rs warmup boundaries; never execute/qualify Metal.

Adaptation of EricLBuehler/mistral.rs paged_decode_warmup_shapes at
9459891e7697238225885518119682ac8209a612; see the bundled inventory reference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 16 * 1024
MAX_USIZE = (1 << 64) - 1
_KEYS = {"schema_version", "max_batch", "max_context"}
# Source implementation boundaries, not empirical or portable acceptance gates.
_CONTEXT_LIMITS = (256, 768, 4096, 288, 320, 512, 1024, 1024, 512, 512)
_PROFILE_BATCHES = (1, 4, 4, 8, 8)


class PlanError(ValueError):
    """The plan does not satisfy the bounded inventory schema."""


def example() -> dict[str, int]:
    """Return a fresh source-boundary example; not an engine workload promise."""
    return {"schema_version": 1, "max_batch": 32, "max_context": 32768}


def inventory(plan: dict[str, Any]) -> dict[str, Any]:
    """Return only the source enumeration on a declared unsigned-64-bit domain."""
    if type(plan) is not dict or set(plan) != _KEYS:
        raise PlanError("plan must contain exactly the three schema keys")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise PlanError("schema_version must be integer 1")
    for name in ("max_batch", "max_context"):
        if type(plan[name]) is not int or not 1 <= plan[name] <= MAX_USIZE:
            raise PlanError("maxima must be positive unsigned-64-bit integers")

    max_batch, max_context = plan["max_batch"], plan["max_context"]
    contexts = [1, max_context, *_CONTEXT_LIMITS]
    contexts.extend(min(value + 1, MAX_USIZE) for value in contexts.copy())
    contexts = sorted({value for value in contexts if value <= max_context})
    batches = [1, max_batch]
    batches.extend(value for limit in _PROFILE_BATCHES for value in (limit, limit + 1))
    batches = sorted({value for value in batches if value <= max_batch})
    shapes = [{"batch": b, "max_context": c} for b in batches for c in contexts]
    return {
        "schema_version": 1,
        "status": "source_boundary_inventory_only",
        "native_verification": "not_run",
        "runtime_eligibility": "not_verified",
        "max_batch": max_batch,
        "max_context": max_context,
        "batches": batches,
        "contexts": contexts,
        "shapes": shapes,
        "count": len(shapes),
    }


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlanError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> Any:
    raise PlanError("nonfinite JSON value")


def _read(path: str) -> Any:
    try:
        if path == "-":
            data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        else:
            target = Path(path)
            if not target.is_file():
                raise PlanError("input must be a regular file")
            with target.open("rb") as stream:
                data = stream.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise PlanError("input could not be read") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise PlanError("input exceeds 16 KiB limit")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PlanError("input must be valid finite JSON without duplicate keys") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="UTF-8 JSON file or - for stdin")
    parser.add_argument("--example", action="store_true", help="emit the example inventory")
    args = parser.parse_args(argv)
    if args.example and args.input != "-":
        parser.error("--example cannot be combined with a file")
    try:
        result = inventory(example() if args.example else _read(args.input))
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
