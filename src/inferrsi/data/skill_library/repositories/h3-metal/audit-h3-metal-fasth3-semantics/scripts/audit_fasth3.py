"""Offline selected-rule audit of caller declarations, never an engine validator.

Standard library only. No network, subprocess, source checkout, model access,
ambient environment discovery or output files. JSON arrives on stdin.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter

PARAMETERS = {
    "steps": 4,
    "dit_layers": 50,
    "denoise_reuse": 1,
    "core_reuse": 1,
    "token_reduction": 0,
    "ssd_streaming": 0,
}
ENVIRONMENT = {
    "H3_TOKEN_REDUCTION",
    "H3_DISABLE_TOKEN_REDUCTION",
    "H3_TOKEN_REDUCTION_BLOCKS",
    "H3_TOKEN_REDUCTION_EARLY",
    "H3_TOKEN_REDUCTION_SCALE",
    "H3_DISABLE_FASTH3_SPARSE",
    "H3_REUSE_STEPS",
}


def _object(value: object, name: str, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) - keys:
        raise ValueError(f"{name} must be an object with only: {', '.join(sorted(keys))}")
    return value


def _integer(value: object, name: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def layout(latent: dict, segments: list) -> dict:
    """Selected tile arithmetic, not a replacement for native packed-layout checks."""
    latent = _object(latent, "latent_shape", {"t", "h", "w"})
    if set(latent) != {"t", "h", "w"}:
        raise ValueError("latent_shape requires t, h and w")
    t, h, w = (_integer(latent[k], f"latent_shape.{k}", 1, 512) for k in ("t", "h", "w"))
    if h % 2 or w % 2:
        raise ValueError("latent h and w must be even for the (1,2,2) patch grid")
    if not isinstance(segments, list) or len(segments) > 64:
        raise ValueError("prefix_segments must be a list of at most 64 segments")
    merged = []
    for segment in segments:
        segment = _object(segment, "prefix segment", {"kind", "rows"})
        if set(segment) != {"kind", "rows"}:
            raise ValueError("each prefix segment requires kind and rows")
        kind = segment["kind"]
        if kind not in ("text", "cond", "audio"):
            raise ValueError("prefix kind must be text, cond or audio; ordered refs unsupported")
        rows = _integer(segment["rows"], "prefix rows", 1, 65536)
        if merged and merged[-1][0] == kind:
            merged[-1][1] += rows
        else:
            merged.append([kind, rows])
    ht, wt = h // 2, w // 2
    video_rows = t * ht * wt
    prefix_rows = sum(rows for _, rows in merged)
    if video_rows + prefix_rows > 1_000_000:
        raise ValueError("selected offline layout budget exceeded (1000000 rows)")
    prefix_counts = [min(64, rows - start) for _, rows in merged for start in range(0, rows, 64)]
    # Product of the real edge lengths is the tile's actual row count.
    video_counts = [
        min(4, t - ti) * min(4, ht - hi) * min(4, wt - wi)
        for ti in range(0, t, 4)
        for hi in range(0, ht, 4)
        for wi in range(0, wt, 4)
    ]
    video_tiles = len(video_counts)
    topk = max(1, min(math.ceil((1.0 - 0.9) * video_tiles), video_tiles))
    return {
        "patch_grid": [t, ht, wt],
        "prefix_rows": prefix_rows,
        "video_rows": video_rows,
        "prefix_tile_counts": prefix_counts,
        "video_tiles": video_tiles,
        "total_tiles": len(prefix_counts) + video_tiles,
        "video_tile_row_histogram": {str(k): v for k, v in sorted(Counter(video_counts).items())},
        "video_tile_rows_sum": sum(video_counts),
        "topk_double": topk,
        "video_query_key_tiles": len(prefix_counts) + topk,
        "prefix_query_key_tiles": len(prefix_counts) + video_tiles,
    }


def mapping_probes() -> dict:
    q, k, v = ([f"{kind}{i}" for i in range(4)] for kind in ("q", "k", "v"))
    interleaved = [
        x for head in range(2) for part in (q, k, v) for x in part[head * 2 : head * 2 + 2]
    ]
    return {
        "evidence": "fixed label-only counterexamples; no tensors or numeric parity",
        "qkv_head_interleaved": interleaved,
        "qkv_wrong_global_concat": q + k + v,
        "fc1_source": ["a", "b", "c", "d"],
        "fc1_swapped": ["c", "d", "a", "b"],
    }


def example() -> dict:
    return {
        "fasth3": True,
        "requested": {
            "steps": 20,
            "dit_layers": 45,
            "denoise_reuse": 2,
            "core_reuse": 2,
            "token_reduction": 1,
            "ssd_streaming": 1,
        },
        "reference_count": 0,
        "requested_frames": 49,
        "environment": {"H3_DISABLE_FASTH3_SPARSE": "0", "H3_REUSE_STEPS": "0,2,4"},
        "sparse_pipeline_available": None,
        "latent_shape": {"t": 17, "h": 28, "w": 48},
        "prefix_segments": [{"kind": "text", "rows": 6}, {"kind": "audio", "rows": 186}],
    }


def audit(document: object) -> dict:
    data = _object(
        document,
        "input",
        {
            "fasth3",
            "requested",
            "reference_count",
            "requested_frames",
            "environment",
            "sparse_pipeline_available",
            "latent_shape",
            "prefix_segments",
        },
    )
    if type(data.get("fasth3")) is not bool:
        raise ValueError("fasth3 must be an explicit boolean")
    requested = _object(data.get("requested", {}), "requested", set(PARAMETERS))
    for key, value in requested.items():
        _integer(value, f"requested.{key}", 0, 1000)
    environment = _object(data.get("environment", {}), "environment", ENVIRONMENT)
    if not all(isinstance(value, str) for value in environment.values()):
        raise ValueError("environment values must be strings; omit absent keys")
    references = _integer(data.get("reference_count", 0), "reference_count", 0, 12)
    pipeline = data.get("sparse_pipeline_available")
    if pipeline is not None and type(pipeline) is not bool:
        raise ValueError("sparse_pipeline_available must be boolean or null")
    frames = data.get("requested_frames")
    temporal = None
    if frames is not None:
        frames = _integer(frames, "requested_frames", 5, 362)
        aligned = 5 + ((frames - 5 + 16) // 17) * 17
        temporal = {
            "requested_frames": frames,
            "aligned_frames": aligned,
            "video_latent_t": ((aligned - 5) // 17) * 5 + 2,
        }
    if ("latent_shape" in data) != ("prefix_segments" in data):
        raise ValueError("latent_shape and prefix_segments must be supplied together")
    tile_result = (
        layout(data["latent_shape"], data["prefix_segments"]) if "latent_shape" in data else None
    )
    issues = []
    fast = data["fasth3"]
    effective = dict(requested)
    path = "not_audited_original_h3"
    if fast:
        effective.update(PARAMETERS)
        if references:
            issues.append("ordered_ref2va_references_rejected")
        token_enable = environment.get("H3_TOKEN_REDUCTION", "") not in ("", "0")
        if token_enable:
            issues.append("ambient_token_reduction_conflicts_with_fasth3")
            if "H3_DISABLE_TOKEN_REDUCTION" in environment:
                issues.append(
                    "reduction_forward_disabled_by_key_presence_but_configuration_still_enabled"
                )
        if "H3_DISABLE_FASTH3_SPARSE" in environment:
            path = "dense_fine_plus_gated_coarse"
        elif pipeline is False:
            path = "dense_fine_plus_gated_coarse"
        elif pipeline is True:
            path = "sparse_fine_plus_gated_coarse_if_native_constraints_hold"
        else:
            path = "unknown_sparse_pipeline_availability"
    if temporal and tile_result and data["latent_shape"]["t"] != temporal["video_latent_t"]:
        issues.append("declared_latent_t_differs_from_aligned_frame_arithmetic")
    return {
        "audit_kind": "offline_selected_declaration_rules",
        "requested": requested,
        "effective_parameters": effective,
        "parameter_overrides": {
            key: {"requested": value, "effective": effective[key]}
            for key, value in requested.items()
            if effective[key] != value
        },
        "environment_declared": environment,
        "issues": issues,
        "temporal": temporal,
        "attention_path": path,
        "layout": tile_result,
        "reuse_steps_effect": "ignored_by_normalized_reuse_1" if fast else "not_audited",
        "mapping_probes": mapping_probes() if fast else None,
        "native_execution": "not_run",
        "quality": "not_run",
        "performance": "not_run",
        "limits": [
            "caller declarations are not observations or checkpoint validation",
            "not a complete h3_valid_params or environment validator",
            "no backend, conversion, dtype, payload, numerical parity or memory-fit evidence",
        ],
    }


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse normally echoes unrecognized caller strings to stderr.
        raise ValueError("invalid_arguments")


def _diagnostic(code: str) -> int:
    print(json.dumps({"error": code, "native_execution": "not_run"}), file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=__doc__, prog="audit_fasth3.py")
    parser.add_argument(
        "--example", action="store_true", help="print a synthetic input, do not audit"
    )
    try:
        args = parser.parse_args(argv)
    except (ValueError, RecursionError):
        return _diagnostic("invalid_arguments")
    try:
        if args.example:
            result = example()
        else:
            raw = sys.stdin.read(65537)
            if len(raw) > 65536:
                raise ValueError("input exceeds the offline 65536-character budget")
            result = audit(json.loads(raw, object_pairs_hook=_unique_keys))
    except (ValueError, TypeError, RecursionError):
        # Never echo malformed input, caller keys, exception text or file paths.
        return _diagnostic("invalid_input")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _unique_keys(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
