#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit declared MLC compile/runtime limit inputs; never estimate device fit.

Selected clamp/minimum rules from mlc-ai/mlc-llm cpp/serve/config.cc at
8978ea9aec626d64096aaa92fbc89bda2e3ea802 (MLC LLM Contributors).
No MLC/TVM import, native config parsing, allocation, compiler or GPU simulation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_INPUT_BYTES = 65536
MAX_FINITE = (1 << 63) - 2
FIELDS = {"schema_version", "models"}
MODEL_FIELDS = {"name", "compiled_context", "runtime_context", "compiled_prefill",
                "runtime_prefill", "compiled_batch", "runtime_sliding_window",
                "workspace_prefill_from_compiled_config"}
SENTINEL_FIELDS = {"compiled_context", "runtime_context", "compiled_prefill",
                   "runtime_prefill", "runtime_sliding_window"}


def number(value: object, *, sentinel: bool = False) -> int:
    if type(value) is not int or not (1 <= value <= MAX_FINITE or sentinel and value == -1):
        raise ValueError("limit requires a positive bounded integer or documented -1 sentinel")
    return value


def clamp(runtime: int, compiled: int) -> int:
    return compiled if compiled != -1 and (runtime == -1 or runtime > compiled) else runtime


def finite_min(values: list[int]) -> int | None:
    finite = [value for value in values if value != -1]
    return min(finite) if finite else None


def audit(plan: object) -> dict:
    """Return selected source arithmetic on declarations, not an effective engine config."""
    if type(plan) is not dict or set(plan) != FIELDS:
        raise ValueError("requires exactly schema_version and models")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    models = plan["models"]
    if not isinstance(models, list) or not 1 <= len(models) <= 64:
        raise ValueError("requires 1..64 model declarations")
    rows, names = [], set()
    for model in models:
        if type(model) is not dict or set(model) != MODEL_FIELDS:
            raise ValueError("model requires exactly the documented fields")
        name = model["name"]
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name) is None:
            raise ValueError("name requires a bounded opaque identifier")
        if name in names:
            raise ValueError("model names must be unique")
        names.add(name)
        for key in MODEL_FIELDS - {"name"}:
            number(model[key], sentinel=key in SENTINEL_FIELDS)
        context = clamp(model["runtime_context"], model["compiled_context"])
        prefill = clamp(model["runtime_prefill"], model["compiled_prefill"])
        rows.append({
            "name": name,
            "compiled_context": model["compiled_context"],
            "clamped_runtime_context": context,
            "runtime_context_changed": context != model["runtime_context"],
            "compiled_prefill": model["compiled_prefill"],
            "clamped_runtime_prefill": prefill,
            "runtime_prefill_changed": prefill != model["runtime_prefill"],
            "compiled_batch": model["compiled_batch"],
            "runtime_sliding_window": model["runtime_sliding_window"],
            "workspace_prefill_from_compiled_config":
                model["workspace_prefill_from_compiled_config"],
        })
    aggregate = {
        "compiled_context_min": finite_min([row["compiled_context"] for row in rows]),
        "runtime_context_min": finite_min([row["clamped_runtime_context"] for row in rows]),
        "compiled_prefill_min": finite_min([row["compiled_prefill"] for row in rows]),
        "runtime_prefill_min": finite_min([row["clamped_runtime_prefill"] for row in rows]),
        "compiled_batch_min": min(row["compiled_batch"] for row in rows),
        "runtime_sliding_window_min": finite_min([row["runtime_sliding_window"] for row in rows]),
    }
    issues = []
    for field in ("compiled_prefill_min", "runtime_prefill_min"):
        if aggregate[field] is None:
            issues.append("source_requires_finite_positive_" + field)
    return {
        "schema_version": 1,
        "status": "declared_source_limit_conflict" if issues else "declared_limits_analyzed_only",
        "models": rows,
        "aggregate_limits": aggregate,
        "unbounded_context_representation": (
            "null means no finite bound in this selected source rule"
        ),
        "issues": issues,
        "native_verification": "not_run",
        "compiler_check": "not_run",
        "input_authentication": "not_verified",
        "effective_engine_configuration": "not_computed",
        "allocation_or_capacity_estimate": "not_computed",
        "physical_fit": "not_verified",
        "scope": "Selected clamp/min rules only; no native JSON parser, estimator, override "
                 "admission, cache, allocator, memory attribute or device inspected.",
    }


def example() -> dict:
    return {"schema_version": 1, "models": [
        {"name": "model-a", "compiled_context": 8192, "runtime_context": 16384,
         "compiled_prefill": 1024, "runtime_prefill": 2048, "compiled_batch": 16,
         "runtime_sliding_window": -1, "workspace_prefill_from_compiled_config": 1024},
        {"name": "model-b", "compiled_context": 4096, "runtime_context": -1,
         "compiled_prefill": 512, "runtime_prefill": 128, "compiled_batch": 8,
         "runtime_sliding_window": 2048, "workspace_prefill_from_compiled_config": 512},
    ]}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def nonfinite(_):
    raise ValueError("nonfinite JSON declaration")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "Invalid command line; use --help.\n")


def main() -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("input", nargs="?", help="regular UTF-8 JSON file, or -/omitted stdin")
    parser.add_argument("--example", action="store_true", help="print synthetic input only")
    args = parser.parse_args()
    if args.example:
        if args.input is not None:
            parser.error("--example takes no input")
        print(json.dumps(example(), indent=2))
        return 0
    try:
        if args.input and args.input != "-":
            path = Path(args.input)
            if not path.is_file():
                raise ValueError("input must be a regular file")
            with path.open("rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input exceeds 64 KiB")
        result = audit(json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                                  parse_constant=nonfinite))
    except (OSError, ValueError, UnicodeError, RecursionError):
        print("Invalid limits; use --example and the bundled helper contract.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
