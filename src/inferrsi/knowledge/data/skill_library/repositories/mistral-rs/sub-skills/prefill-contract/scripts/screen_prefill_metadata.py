#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Screen declared prefill metadata and source workspace arithmetic, not Metal.

Selected formulas/guards are adapted from mistral.rs paged_prefill.rs. This is
not its complete request validator, dispatch selector or numerical attention
implementation. No model, tensor, cache, device or compiler is inspected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_USIZE = (1 << 64) - 1
MAX_INPUT_BYTES = 1 << 20
MAX_SEQUENCES = 4096
MAX_RANGES = 16384
DTYPE_BYTES = {"f16": 2, "bf16": 2, "f32": 4}
FIELDS = {
    "schema_version", "num_heads", "num_kv_heads", "key_head_dim", "value_head_dim",
    "block_size", "query_dtype", "cache_dtype", "packed_queries", "packed_mask",
    "query_lens", "context_lens", "query_start_positions", "key_start_positions",
    "multimodal_ranges", "mask_key_offsets", "additive_mask_shape", "sliding_window",
    "window_right", "attention_chunk_size",
}


def integer(value: object, name: str, *, zero: bool = False) -> int:
    if type(value) is not int or not (0 if zero else 1) <= value <= MAX_USIZE:
        raise ValueError(f"{name} must be a bounded integer in the documented range")
    return value


def checked(value: int) -> int:
    if value > MAX_USIZE:
        raise ValueError("declared size or absolute position overflows 64-bit usize")
    return value


def product(*values: int) -> int:
    result = 1
    for value in values:
        result = checked(result * value)
    return result


def allocation(size: int) -> int:
    """Source reservation: next power of two, with a 16 KiB minimum."""
    rounded = 1 << (size - 1).bit_length() if size else 1
    return checked(max(16384, rounded))


def vector(value: object, name: str, count: int, *, zero: bool = False) -> list[int]:
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(f"{name} must match the declared sequence count")
    return [integer(item, name, zero=zero) for item in value]


def screen(plan: object) -> dict:
    """Return selected structural screening and byte formulas for caller facts."""
    if not isinstance(plan, dict) or set(plan) != FIELDS:
        raise ValueError("input must contain exactly the documented fields")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    for name in ("packed_queries", "packed_mask"):
        if type(plan[name]) is not bool:
            raise ValueError(f"{name} must be boolean")
    heads = integer(plan["num_heads"], "num_heads")
    kv_heads = integer(plan["num_kv_heads"], "num_kv_heads")
    if heads % kv_heads:
        raise ValueError("num_heads must be divisible by num_kv_heads")
    key_dim = integer(plan["key_head_dim"], "key_head_dim")
    value_dim = integer(plan["value_head_dim"], "value_head_dim")
    if max(key_dim, value_dim) > 4096:
        raise ValueError("declared head dimensions exceed the source shape bound")
    block_size = integer(plan["block_size"], "block_size")
    if not isinstance(plan["query_dtype"], str) or plan["query_dtype"] not in DTYPE_BYTES:
        raise ValueError("unsupported declared query_dtype")
    if plan["cache_dtype"] not in ("f16", "bf16", "f32", "f8e4m3"):
        raise ValueError("unsupported declared cache_dtype")
    query_lens = plan["query_lens"]
    if not isinstance(query_lens, list) or not 1 <= len(query_lens) <= MAX_SEQUENCES:
        raise ValueError("query_lens must be a nonempty bounded sequence list")
    batch = len(query_lens)
    query_lens = vector(query_lens, "query_lens", batch)
    context_lens = vector(plan["context_lens"], "context_lens", batch)
    query_starts = vector(plan["query_start_positions"], "query_start_positions", batch, zero=True)
    key_starts = vector(plan["key_start_positions"], "key_start_positions", batch, zero=True)
    windows = {}
    for name in ("sliding_window", "window_right", "attention_chunk_size"):
        windows[name] = None if plan[name] is None else integer(plan[name], name)
    ranges = plan["multimodal_ranges"]
    if not isinstance(ranges, list) or len(ranges) != batch:
        raise ValueError("multimodal_ranges must have one list per sequence")
    range_count = 0
    for row in ranges:
        if not isinstance(row, list):
            raise ValueError("each multimodal range row must be a list")
        range_count += len(row)
        if range_count > MAX_RANGES:
            raise ValueError("too many ranges for this bounded helper")
        for pair in row:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("each multimodal range must contain start and exclusive end")
            start, end = [integer(item, "range position", zero=True) for item in pair]
            if end <= start:
                raise ValueError("range end must exceed start")
    for row in range(batch):
        query_end = checked(query_starts[row] + query_lens[row])
        checked(key_starts[row] + context_lens[row])
        if windows["window_right"] is not None:
            checked(query_end + windows["window_right"])
    offsets = plan["mask_key_offsets"]
    if offsets is not None:
        offsets = vector(offsets, "mask_key_offsets", batch, zero=True)
    mask_lengths = [
        checked(length + (offsets[row] if offsets is not None else 0))
        for row, length in enumerate(context_lens)
    ]
    total_q = checked(sum(query_lens))
    total_mask_k = checked(sum(mask_lengths))
    max_q, max_k = max(query_lens), max(context_lens)
    expected_mask = (
        [1, heads, total_q, max(mask_lengths) if offsets is not None else total_mask_k]
        if plan["packed_mask"] else [batch, heads, max_q, max(mask_lengths)]
    )
    mask_shape = plan["additive_mask_shape"]
    if mask_shape is not None:
        if not isinstance(mask_shape, list) or not 2 <= len(mask_shape) <= 4:
            raise ValueError("additive_mask_shape must have rank 2, 3 or 4")
        mask_shape = [integer(item, "mask dimension") for item in mask_shape]
        padded = [1] * (4 - len(mask_shape)) + mask_shape
        for axis, (actual, expected) in enumerate(zip(padded, expected_mask)):
            if actual != 1 and (actual < expected if axis == 3 else actual != expected):
                raise ValueError("declared additive mask cannot meet source broadcast extents")
    dtype_bytes = DTYPE_BYTES[plan["query_dtype"]]
    rows = total_q if plan["packed_queries"] else product(batch, max_q)
    raw_output = product(rows, heads, value_dim, dtype_bytes)
    raw_query_copy = product(rows, heads, key_dim, dtype_bytes)
    raw_metadata = product(checked(product(batch, 9) + product(range_count, 2)), 8)
    output_allocation, metadata_allocation = allocation(raw_output), allocation(raw_metadata)
    return {
        "schema_version": 1,
        "status": "screened_caller_declarations_only",
        "native_verification": "not_run",
        "compiler_check": "not_run",
        "runtime_eligibility": "not_verified",
        "numerical_correctness": "not_verified",
        "expected_query_shape": [1 if plan["packed_queries"] else batch, heads,
                                 total_q if plan["packed_queries"] else max_q, key_dim],
        "storage_rows": rows,
        "output_raw_bytes": raw_output,
        "metadata_raw_bytes": raw_metadata,
        "output_allocation_bytes": output_allocation,
        "metadata_reservation_bytes": metadata_allocation,
        "workspace_formula_bytes": checked(output_allocation + metadata_allocation),
        "query_copy_if_needed_bytes_additional": allocation(raw_query_copy),
        "output_copy_if_needed_bytes_additional": output_allocation,
        "metadata_binding": "buffered" if raw_metadata > 4096 else "inline",
        "expected_mask_extents": expected_mask,
        "minimum_table_columns": (max_k + block_size - 1) // block_size,
        "limits": (
            "Excludes KV cache, caller mask, cache writes and extra copies; no tensors inspected."
        ),
    }


def example() -> dict:
    return {
        "schema_version": 1, "num_heads": 4, "num_kv_heads": 2,
        "key_head_dim": 64, "value_head_dim": 96, "block_size": 7,
        "query_dtype": "bf16", "cache_dtype": "bf16", "packed_queries": True,
        "packed_mask": True, "query_lens": [3, 5], "context_lens": [17, 65],
        "query_start_positions": [14, 149], "key_start_positions": [0, 96],
        "multimodal_ranges": [[], [[149, 154]]], "mask_key_offsets": None,
        "additive_mask_shape": [1, 4, 8, 82], "sliding_window": None,
        "window_right": None, "attention_chunk_size": None,
    }


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON file, or -/omitted for stdin")
    parser.add_argument("--example", action="store_true", help="print synthetic input only")
    args = parser.parse_args()
    if args.example:
        if args.input:
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
            raise ValueError("input exceeds supported size")
        result = screen(json.loads(raw, object_pairs_hook=unique_object))
    except (OSError, ValueError, UnicodeError, RecursionError):
        print("Invalid metadata; use --example and the bundled helper contract.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
