#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Screen dense uniform full-attention pool arithmetic; never allocate KV.

The arithmetic is adapted from vllm-metal's default_host_pool_bytes,
_auto_pool_limits and _bounded_pool. See the adjacent helper-contract reference
for the pinned provenance and deliberately narrower supported domain.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_INT = (1 << 63) - 1
MAX_INPUT_BYTES = 1 << 20
FIELDS = {
    "schema_version", "layout", "layers", "kv_heads", "head_dim", "dtype_bytes",
    "max_model_len", "block_size", "kv_budget_bytes", "blocks_per_chunk",
    "chunk_alignment_bytes", "budget_mode", "pool_mode", "pool_bytes",
    "auto_fit_length", "block_override",
}


def _integer(value: object, name: str, *, zero: bool = False) -> int:
    if type(value) is not int or not (0 if zero else 1) <= value <= MAX_INT:
        label = "nonnegative" if zero else "positive"
        raise ValueError(f"{name} must be a bounded {label} integer")
    return value


def _product(*values: int) -> int:
    result = 1
    for value in values:
        result *= value
        if result > MAX_INT:
            raise ValueError("derived byte count exceeds the supported range")
    return result


def screen(plan: object) -> dict:
    """Return declared-input arithmetic, not runtime eligibility or physical fit.

    Reject booleans-as-integers, unknown/missing keys, compressed/grouped layouts
    and ambiguous pool inputs. Values are caller declarations, not model facts.
    """
    if not isinstance(plan, dict) or set(plan) != FIELDS:
        raise ValueError("input must contain exactly the documented fields")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if plan["layout"] != "dense-uniform-full-attention":
        raise ValueError("only declared dense uniform full-attention arithmetic is supported")
    for name in ("auto_fit_length", "block_override"):
        if type(plan[name]) is not bool:
            raise ValueError(f"{name} must be a boolean")
    for name, choices in (
        ("budget_mode", ("automatic", "explicit-cache")),
        ("pool_mode", ("automatic", "explicit")),
    ):
        if plan[name] not in choices:
            raise ValueError(f"invalid {name}")
    dimensions = {
        name: _integer(plan[name], name)
        for name in ("layers", "kv_heads", "head_dim", "dtype_bytes", "max_model_len",
                     "block_size", "kv_budget_bytes", "blocks_per_chunk",
                     "chunk_alignment_bytes")
    }
    if dimensions["dtype_bytes"] not in (1, 2, 4, 8):
        raise ValueError("dtype_bytes must be 1, 2, 4 or 8 for this dense byte ledger")
    supplied_pool = plan["pool_bytes"]
    if plan["pool_mode"] == "automatic":
        if supplied_pool is not None:
            raise ValueError("automatic pool requires pool_bytes=null")
    else:
        supplied_pool = _integer(supplied_pool, "pool_bytes")
    block = dimensions["block_size"]
    length = dimensions["max_model_len"]
    budget = dimensions["kv_budget_bytes"]
    token_bytes = _product(2, dimensions["layers"], dimensions["kv_heads"],
                           dimensions["head_dim"], dimensions["dtype_bytes"])
    block_bytes = _product(token_bytes, block)
    rounded_tokens = ((length + block - 1) // block) * block
    default_pool = _product(2, rounded_tokens, token_bytes)
    raw_chunk = _product(block_bytes, dimensions["blocks_per_chunk"])
    alignment = dimensions["chunk_alignment_bytes"]
    chunk_bytes = ((raw_chunk + alignment - 1) // alignment) * alignment
    if chunk_bytes > MAX_INT:
        raise ValueError("aligned chunk exceeds the supported range")
    reserved_request = 0
    reserve_enabled = (
        plan["budget_mode"] == "automatic"
        and not plan["auto_fit_length"]
        and not plan["block_override"]
    )
    if reserve_enabled:
        reserved_request = _product((length + block - 1) // block + 1, block_bytes)
    if plan["pool_mode"] == "automatic":
        cap = budget // 4
        if reserve_enabled:
            cap = min(cap, budget - reserved_request)
        pool = min(max(default_pool, chunk_bytes), max(cap, chunk_bytes))
    else:
        cap = None  # A user-set pool is never silently capped.
        pool = supplied_pool
    assert isinstance(pool, int)
    remaining = budget - pool if plan["budget_mode"] == "automatic" else budget
    problems = []
    if pool < chunk_bytes:
        problems.append("pool_below_one_aligned_chunk")
    if remaining < 0:
        problems.append("host_pool_exceeds_automatic_budget")
    if reserved_request > budget:
        problems.append("one_request_exceeds_budget_even_without_offload")
    elif reserve_enabled and remaining < reserved_request:
        problems.append("offload_leaves_no_room_for_one_request_and_null_block")
    return {
        "schema_version": 1,
        "status": "arithmetic_conflict" if problems else "screened_declared_arithmetic_only",
        "native_verification": "not_run",
        "physical_fit": "not_verified",
        "runtime_eligibility": "not_verified",
        "per_token_bytes": token_bytes,
        "per_block_bytes": block_bytes,
        "rounded_request_tokens": rounded_tokens,
        "default_two_request_pool_bytes": default_pool,
        "aligned_chunk_bytes": chunk_bytes,
        "automatic_pool_cap_bytes": cap,
        "selected_pool_bytes": pool,
        "reserved_request_plus_null_block_bytes": reserved_request,
        "remaining_cache_budget_bytes": remaining,
        "physical_cache_plus_pool_capacity_bytes": max(0, remaining) + pool,
        "problems": problems,
        "limits": (
            "No allocation, commit probe, grouped/compressed layout, weights, "
            "workspace or OS pressure proof."
        ),
    }


def example() -> dict:
    return {
        "schema_version": 1, "layout": "dense-uniform-full-attention",
        "layers": 2, "kv_heads": 2, "head_dim": 64, "dtype_bytes": 2,
        "max_model_len": 17, "block_size": 16, "kv_budget_bytes": 1048576,
        "blocks_per_chunk": 1, "chunk_alignment_bytes": 4096,
        "budget_mode": "automatic", "pool_mode": "automatic", "pool_bytes": None,
        "auto_fit_length": False, "block_override": False,
    }


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON file; omit or use - for stdin")
    parser.add_argument("--example", action="store_true", help="print synthetic input only")
    args = parser.parse_args()
    if args.example:
        if args.input:
            parser.error("--example takes no input")
        print(json.dumps(example(), indent=2))
        return 0
    try:
        if args.input and args.input != "-":
            with Path(args.input).open("rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input exceeds the supported size")
        result = screen(json.loads(raw, object_pairs_hook=_object))
    except (OSError, ValueError, UnicodeError, RecursionError):
        print("Invalid input; use --example and the bundled helper contract.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
