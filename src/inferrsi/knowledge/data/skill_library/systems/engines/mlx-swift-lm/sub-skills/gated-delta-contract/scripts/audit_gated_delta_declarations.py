#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Screen caller-declared GDN shapes and the literal public kernel gate only.

Adapted from ml-explore/mlx-swift-lm GatedDelta.swift at
3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac (Copyright 2026 Apple Inc.).
No MLX import, recurrence, gradient, GPU execution or runtime selector emulation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_INPUT_BYTES = 65536
MAX_INTEGER = (1 << 63) - 1
DTYPE_BYTES = {"float16": 2, "bfloat16": 2, "float32": 4}
AVAILABILITY = ("available", "unavailable", "unknown")
FIELDS = {
    "schema_version", "q_shape", "k_shape", "v_shape", "a_shape", "b_shape",
    "a_log_shape", "dt_bias_shape", "input_dtype", "state", "mask_shape",
    "use_kernel", "training", "unmasked_kernel_availability", "masked_kernel_availability",
}


def positive(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_INTEGER:
        raise ValueError("shape entries must be positive bounded integers, not booleans")
    return value


def shape(value: object, rank: int) -> list[int]:
    if not isinstance(value, list) or len(value) != rank:
        raise ValueError("shape rank does not match the documented helper domain")
    return [positive(item) for item in value]


def product(*values: int) -> int:
    total = 1
    for value in values:
        total *= value
        if total > MAX_INTEGER:
            raise ValueError("declared payload arithmetic exceeds the helper bound")
    return total


def dtype(value: object) -> str:
    if not isinstance(value, str) or value not in DTYPE_BYTES:
        raise ValueError("dtype must be a documented floating declaration")
    return value


def audit(plan: object) -> dict:
    """Validate a deliberately narrow declaration schema, never actual tensors."""
    if not isinstance(plan, dict) or set(plan) != FIELDS:
        raise ValueError("requires exactly the documented declaration keys")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    for name in ("use_kernel", "training"):
        if type(plan[name]) is not bool:
            raise ValueError("control declarations must be booleans")
    for name in ("unmasked_kernel_availability", "masked_kernel_availability"):
        if not isinstance(plan[name], str) or plan[name] not in AVAILABILITY:
            raise ValueError("kernel availability must be available, unavailable or unknown")
    q = shape(plan["q_shape"], 4)
    k = shape(plan["k_shape"], 4)
    v = shape(plan["v_shape"], 4)
    batch, tokens, key_heads, key_dim = q
    value_heads, value_dim = v[2:]
    if k != q or v[:2] != q[:2]:
        raise ValueError("declared Q/K or V batch/time geometry does not agree")
    if value_heads % key_heads:
        raise ValueError("declared value heads must be divisible by key heads")
    expected_gate = [batch, tokens, value_heads]
    if shape(plan["a_shape"], 3) != expected_gate:
        raise ValueError("declared A shape does not match the helper contract")
    if shape(plan["b_shape"], 3) != expected_gate:
        raise ValueError("declared B gate shape does not match the helper contract")
    for name in ("a_log_shape", "dt_bias_shape"):
        if shape(plan[name], 1) != [value_heads]:
            raise ValueError("declared per-head parameter shape does not agree")
    input_dtype = dtype(plan["input_dtype"])
    expected_state = [batch, value_heads, value_dim, key_dim]
    supplied_state = plan["state"]
    state_conversion = "default_zero_float32"
    if supplied_state is not None:
        if not isinstance(supplied_state, dict) or set(supplied_state) != {"shape", "dtype"}:
            raise ValueError("state descriptor requires exactly shape and dtype")
        if shape(supplied_state["shape"], 4) != expected_state:
            raise ValueError("declared state geometry does not agree")
        state_dtype = dtype(supplied_state["dtype"])
        state_conversion = "retained_float32" if state_dtype == "float32" else "cast_to_float32"
    mask = plan["mask_shape"]
    if mask is not None and shape(mask, 2) != [batch, tokens]:
        raise ValueError("helper mask domain is one declared batch/time mask")

    reasons = []
    if not plan["use_kernel"]:
        reasons.append("use_kernel_false")
    if key_dim % 32:
        reasons.append("key_dimension_has_simd_tail")
    if plan["unmasked_kernel_availability"] == "unavailable":
        reasons.append("declared_unmasked_kernel_unavailable")
    if reasons:
        public_gate = "false"
        branch = "ops_fallback_by_declared_public_gate"
    elif plan["unmasked_kernel_availability"] == "unknown":
        public_gate = "undetermined"
        branch = "unmasked_availability_not_established"
    else:
        public_gate = "true"
        if mask is None:
            branch = "unmasked_kernel_candidate_by_declarations"
        elif plan["masked_kernel_availability"] == "unavailable":
            branch = "selected_masked_kernel_nil_fatal_branch_by_declarations"
        elif plan["masked_kernel_availability"] == "unknown":
            branch = "masked_kernel_availability_not_established"
        else:
            branch = "masked_kernel_candidate_by_declarations"
    return {
        "schema_version": 1,
        "status": "declarations_screened_only",
        "literal_public_gate": public_gate,
        "declared_branch": branch,
        "gate_false_reasons": reasons,
        "key_dimension_tail_mod32": key_dim % 32,
        "value_heads_per_key_head": value_heads // key_heads,
        "expected_output_shape": [batch, tokens, value_heads, value_dim],
        "expected_carried_state_shape": expected_state,
        "effective_carried_state_dtype": "float32",
        "state_conversion": state_conversion,
        "one_carried_state_payload_bytes": product(batch, value_heads, value_dim, key_dim, 4),
        "state_payload_scope": (
            "One recurrent tensor only; excludes convolution state, checkpoints, "
            "offset/padding/length metadata, other caches, copies and memory pressure."
        ),
        "one_output_payload_bytes": product(
            batch, tokens, value_heads, value_dim, DTYPE_BYTES[input_dtype]
        ),
        "training_caller_warning": (
            "model callers pass use_kernel=false for training; custom kernel has no VJP"
            if plan["training"] and plan["use_kernel"] else None
        ),
        "masked_output_parity": (
            "source_asymmetry_unexecuted" if mask is not None else "not_assessed"
        ),
        "native_verification": "not_run",
        "compiler_check": "not_run",
        "actual_dispatch": "not_verified",
        "numerical_correctness": "not_verified",
        "stride_provider_contract": "not_verified",
        "physical_fit": "not_verified",
    }


def example() -> dict:
    return {
        "schema_version": 1,
        "q_shape": [1, 40, 2, 32], "k_shape": [1, 40, 2, 32],
        "v_shape": [1, 40, 4, 16], "a_shape": [1, 40, 4], "b_shape": [1, 40, 4],
        "a_log_shape": [4], "dt_bias_shape": [4], "input_dtype": "bfloat16",
        "state": None, "mask_shape": None, "use_kernel": True, "training": False,
        "unmasked_kernel_availability": "unknown", "masked_kernel_availability": "unknown",
    }


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
    parser.add_argument("input", nargs="?", help="regular JSON file, or -/omitted for stdin")
    parser.add_argument("--example", action="store_true", help="print synthetic input only")
    args = parser.parse_args()
    if args.example:
        if args.input is not None:
            parser.error("--example takes no input")
        print(json.dumps(example(), indent=2))
        return 0
    try:
        if args.input and args.input != "-":
            target = Path(args.input)
            if not target.is_file():
                raise ValueError("input must be a regular file")
            with target.open("rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input exceeds 64 KiB")
        plan = json.loads(raw, object_pairs_hook=unique_object, parse_constant=nonfinite)
        result = audit(plan)
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            "Invalid declarations; use --example and the bundled helper contract.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
