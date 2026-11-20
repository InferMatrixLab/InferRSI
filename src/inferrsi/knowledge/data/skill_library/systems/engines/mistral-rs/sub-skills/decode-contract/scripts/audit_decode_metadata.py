#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check declared paged-decode metadata, not tensors or actual Metal dispatch.

Selected source contracts are distilled from mistralrs-paged-attn's Metal
backend. No Rust/Metal imports, allocations, model access or GPU emulation.
Usage: python audit_decode_metadata.py --example
       python audit_decode_metadata.py metadata.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

INT_MAX = (1 << 31) - 1
FIELDS = {
    "schema_version", "query_shape", "key_shape", "value_shape", "query_dtype",
    "cache_dtype", "context_lens", "max_context_len", "block_table_shape",
    "k_scale", "v_scale", "sliding_window", "has_alibi", "has_sinks", "softcapping",
}
DTYPE_BYTES = {"f16": 2, "bf16": 2, "f32": 4, "f8e4m3": 1}
HEADS = {64, 80, 96, 112, 128, 192, 256, 512}
SPECIAL_HEADS = {64, 96, 128, 192, 256}


def integer(value, name):
    if type(value) is not int or not 1 <= value <= INT_MAX:
        raise ValueError(f"{name} requires a positive signed-32-bit declaration")
    return value


def shape(value, rank, name):
    if not isinstance(value, list) or len(value) not in rank:
        raise ValueError(f"{name} has unsupported rank")
    return [integer(item, name) for item in value]


def audit(plan: object) -> dict:
    if not isinstance(plan, dict) or set(plan) != FIELDS:
        raise ValueError("requires exactly the documented metadata keys")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    batch, heads, dim = shape(plan["query_shape"], (3,), "query_shape")
    key = shape(plan["key_shape"], (4, 5), "key_shape")
    value = shape(plan["value_shape"], (4,), "value_shape")
    table_batch, table_width = shape(plan["block_table_shape"], (2,), "block_table_shape")
    maximum = integer(plan["max_context_len"], "max_context_len")
    lengths = plan["context_lens"]
    if not isinstance(lengths, list) or not 1 <= len(lengths) <= 1024:
        raise ValueError("requires 1..1024 declared context lengths")
    for length in lengths:
        integer(length, "context_lens")
    for field in ("has_alibi", "has_sinks"):
        if type(plan[field]) is not bool:
            raise ValueError(f"{field} requires a boolean")
    window = plan["sliding_window"]
    if window is not None:
        integer(window, "sliding_window")
    softcap = plan["softcapping"]
    if (isinstance(softcap, bool) or not isinstance(softcap, (int, float))
            or softcap <= 0 or (isinstance(softcap, float) and not math.isfinite(softcap))):
        raise ValueError("softcapping requires a finite positive number; 1 means disabled")
    query_dtype, cache_dtype = plan["query_dtype"], plan["cache_dtype"]
    if not isinstance(query_dtype, str) or not isinstance(cache_dtype, str):
        raise ValueError("dtype declarations must be strings")
    if query_dtype not in ("f16", "bf16", "f32") or cache_dtype not in DTYPE_BYTES:
        raise ValueError("unsupported helper dtype declaration")
    hnd = len(key) == 4
    if hnd:
        blocks, kv_heads, block, cache_dim = key
        packed_x = 1
        expected_value = key
    else:
        blocks, kv_heads, packed_dim, block, packed_x = key
        cache_dim = packed_dim * packed_x
        expected_value = [blocks, kv_heads, cache_dim, block]
    issues = []
    if dim not in HEADS or cache_dim != dim or heads % kv_heads:
        issues.append("query_cache_head_geometry_mismatch_or_unsupported_head_dimension")
    if value != expected_value:
        issues.append("value_cache_shape_does_not_match_key_layout")
    if block != 32:
        issues.append("helper_domain_requires_block32_other_native_specializations_not_screened")
    if table_batch != batch or len(lengths) != batch:
        issues.append("sequence_metadata_count_mismatch")
    if max(lengths) > maximum or table_width < (maximum + block - 1) // block:
        issues.append("declared_context_or_table_capacity_mismatch")
    if window is not None and not hnd:
        issues.append("sliding_decode_requires_hnd_cache")
    scales = []
    for name in ("k_scale", "v_scale"):
        item = plan[name]
        if item is not None and (not isinstance(item, dict)
                                 or set(item) != {"dtype", "elements"}):
            raise ValueError("scale descriptors require dtype and elements")
        scales.append(item is not None and item["dtype"] == "f32"
                      and type(item["elements"]) is int and item["elements"] == 1)
    if cache_dtype == "f8e4m3":
        if not all(scales):
            issues.append("fp8_cache_requires_two_explicit_scalar_f32_scales")
    elif plan["k_scale"] is not None or plan["v_scale"] is not None:
        issues.append("non_fp8_cache_must_not_supply_scales")
    ratio = heads // kv_heads if heads % kv_heads == 0 else None
    blockers = []
    gates = (
        (query_dtype in ("f16", "bf16") and cache_dtype == query_dtype, "dtype_pair"),
        (plan["k_scale"] is None and plan["v_scale"] is None, "scales"),
        (not plan["has_alibi"] and not plan["has_sinks"], "alibi_or_sinks"),
        (softcap == 1.0, "softcapping"),
        (block == 32 and (hnd or packed_x == 8), "block_or_packing"),
        (ratio is not None and 1 <= ratio <= 8, "gqa_ratio"),
        (dim in SPECIAL_HEADS or (hnd and dim == 512 and ratio is not None and ratio <= 4),
         "specialized_head_domain"),
    )
    for allowed, reason in gates:
        if not allowed:
            blockers.append(reason)
    return {
        "status": "declared_contract_conflict" if issues else "declared_metadata_screened_only",
        "layout": "hnd" if hnd else "legacy-packed", "issues": issues,
        "specialization_predicate_candidate": not issues and not blockers,
        "specialization_blockers": blockers,
        "declared_cache_payload_bytes": 2 * blocks * kv_heads * block * cache_dim
                                        * DTYPE_BYTES[cache_dtype],
        "native_verification": "not_run", "physical_fit": "not_verified",
        "scope": "declarations only; no tensor bytes/strides/table IDs/device/loaded pipeline, "
                 "actual dispatch, scratch capacity, numerical or model validation",
    }


def example():
    return {
        "schema_version": 1, "query_shape": [1, 8, 128],
        "key_shape": [16, 2, 32, 128], "value_shape": [16, 2, 32, 128],
        "query_dtype": "bf16", "cache_dtype": "bf16", "context_lens": [257],
        "max_context_len": 512, "block_table_shape": [1, 16],
        "k_scale": None, "v_scale": None, "sliding_window": None,
        "has_alibi": False, "has_sinks": False, "softcapping": 1.0,
    }


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON file, or - for stdin")
    parser.add_argument("--example", action="store_true")
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
                raw = stream.read(65537)
        else:
            raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("input exceeds 64 KiB")
        result = audit(json.loads(raw, object_pairs_hook=unique_object))
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        print("Invalid metadata; use --example and the bundled contract.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
