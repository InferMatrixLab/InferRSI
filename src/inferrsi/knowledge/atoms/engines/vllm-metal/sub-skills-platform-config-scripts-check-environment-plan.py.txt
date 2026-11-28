#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline selected-knob syntax check, adapted from vllm_metal/envs.py.

Read a JSON object of explicit string values, not the process environment.
No package imports, installation, host probing or engine execution occurs.
Usage: python check_environment_plan.py plan.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CHOICES = {
    "VLLM_METAL_BACKEND": ("mlx", ("mlx", "mps")),
    "VLLM_MLX_DEVICE": ("gpu", ("gpu", "cpu")),
    "VLLM_METAL_MULTIMODAL_MODE": ("auto", ("auto", "multimodal-native", "text-only")),
    "VLLM_METAL_MM_PREFIX_PATH": (None, ("kernel", "recompute")),
    "VLLM_METAL_TQ_PREFILL": ("auto", ("auto", "0", "1")),
}
SWITCHES = {
    "VLLM_METAL_GDN_LAZY_KERNELS": True,
    "VLLM_METAL_DECODE_PIPELINE": True,
    "VLLM_METAL_COMPILED_MLP": False,
    "VLLM_METAL_NATIVE_SAMPLING": True,
    "VLLM_METAL_MLA_KERNEL": False,
    "VLLM_METAL_DISABLE_NAX": False,
    "VLLM_METAL_DISABLE_GQA_DECODE": False,
    "VLLM_METAL_SPEC_VERIFY_WINDOW": False,
    "VLLM_METAL_BUILD_FROM_SOURCE": False,
    "VLLM_METAL_KV_COMMIT_PROBE": True,
}
INTEGERS = {
    "VLLM_METAL_SPEC_INGEST_CHUNK": (1024, 0, None),
    "VLLM_METAL_RING_BASE_PORT": (32323, 1024, 65535),
}


def check(values: dict) -> dict:
    """Validate the supported syntax subset; do not infer feature compatibility."""
    if not isinstance(values, dict):
        raise ValueError("plan must be a JSON object")
    supported = set(CHOICES) | set(SWITCHES) | set(INTEGERS) | {
        "VLLM_METAL_TQ_PREFILL_MAX_MIB"
    }
    if set(values) - supported:
        raise ValueError("unsupported keys; pass only the documented selected knobs")
    if any(not isinstance(value, str) for value in values.values()):
        raise ValueError("explicit values must be strings, as in an environment")
    parsed, errors, warnings = {}, [], []
    for name, (default, choices) in CHOICES.items():
        raw = values.get(name, default)
        if raw is not None and raw not in choices:
            errors.append({"name": name, "reason": "invalid choice"})
        else:
            parsed[name] = raw
    for name, default in SWITCHES.items():
        raw = values.get(name)
        parsed[name] = default if raw is None else raw == "1"
        if raw not in (None, "0", "1"):
            warnings.append({"name": name, "reason": "only literal 1 enables this switch"})
    for name, (default, minimum, maximum) in INTEGERS.items():
        try:
            number = int(values.get(name, str(default)))
            if number < minimum or (maximum is not None and number > maximum):
                raise ValueError
            parsed[name] = number
        except ValueError:
            errors.append({"name": name, "reason": "integer outside accepted syntax/range"})
    name = "VLLM_METAL_TQ_PREFILL_MAX_MIB"
    raw = values.get(name, "auto")
    try:
        number = raw if raw == "auto" else int(raw)
        if number != "auto" and number < 0:
            raise ValueError
        parsed[name] = number
    except ValueError:
        errors.append({"name": name, "reason": "requires auto or a nonnegative MiB integer"})
    return {
        "status": "syntax_rejected" if errors else "syntax_screened_only",
        "parsed": parsed, "errors": errors, "warnings": warnings,
        "native_verification": "not_run", "feature_compatibility": "not_verified",
        "scope": "selected syntax only; no ambient environment read or engine qualification",
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
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("input exceeds 64 KiB")
        result = check(json.loads(raw, object_pairs_hook=unique_object))
    except (OSError, ValueError, TypeError, RecursionError):
        parser.error("invalid bounded environment plan; see the documented input schema")
    print(json.dumps(result, indent=2, allow_nan=False))
    if result["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
