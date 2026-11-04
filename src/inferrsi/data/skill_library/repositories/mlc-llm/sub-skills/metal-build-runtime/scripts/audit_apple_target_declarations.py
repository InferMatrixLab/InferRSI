#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Screen selected MLC Apple target/export declarations, never compile or probe.

Literal preset/prefix/builder rules adapted from mlc-ai/mlc-llm auto_target.py
at 8978ea9aec626d64096aaa92fbc89bda2e3ea802 (MLC LLM Contributors).
No MLC/TVM import, host SDK query, binary inspection or runtime simulation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_INPUT_BYTES = 16384
HINTS = {"iphone", "iphone:generic", "macabi", "macabi:generic", "metal:x86-64", "metal:generic"}
FIELDS = {"schema_version", "target_hint", "output_suffix", "host_hint", "prefix_hint",
          "model_name", "quantization", "macabi_arch"}


def identifier(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) is None:
        raise ValueError("requires a bounded opaque identifier")
    return value


def audit(plan: object) -> dict:
    if type(plan) is not dict or set(plan) != FIELDS:
        raise ValueError("requires exactly the documented fields")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    hint, suffix = plan["target_hint"], plan["output_suffix"]
    if not isinstance(hint, str) or hint not in HINTS:
        raise ValueError("unsupported helper target hint")
    if not isinstance(suffix, str) or re.fullmatch(r"\.[A-Za-z0-9_]{1,16}", suffix) is None:
        raise ValueError("requires only a bounded output suffix, not a path")
    host = plan["host_hint"]
    if not isinstance(host, str) or re.fullmatch(r"[A-Za-z0-9_.+-]{1,160}", host) is None:
        raise ValueError("requires auto or an opaque bounded host triple declaration")
    prefix = plan["prefix_hint"]
    if not isinstance(prefix, str) or re.fullmatch(r"[A-Za-z0-9_-]{0,160}", prefix) is None:
        raise ValueError("requires auto, empty or a bounded prefix declaration")
    model, quant = identifier(plan["model_name"]), identifier(plan["quantization"])
    arch = plan["macabi_arch"]
    if arch is not None and (not isinstance(arch, str) or len(arch) > 64):
        raise ValueError("macabi_arch requires a bounded string or null")
    arch = (arch or "").strip() or "arm64"
    effective_arch = arch if arch in ("arm64", "x86_64") else "arm64"
    normalized_hint = hint + ":generic" if hint in ("iphone", "macabi") else hint
    if prefix == "auto" and hint.startswith(("iphone", "macabi")):
        resolved_prefix = f"{model}_{quant}_".replace("-", "_")
    elif hint in ("iphone", "macabi"):
        resolved_prefix = prefix
    else:
        resolved_prefix = ""
    issues, warnings = [], []
    if normalized_hint in ("iphone:generic", "macabi:generic"):
        builder, system = "iphone_static_tar", True
        sdk = "iphoneos" if normalized_hint == "iphone:generic" else "macosx"
        preset_host = ("arm64-apple-darwin" if normalized_hint == "iphone:generic" else
                       effective_arch + "-apple-ios18.0-macabi")
        if suffix != ".tar":
            issues.append("selected_static_builder_requires_tar_suffix")
        export_arch = None
    elif hint == "metal:x86-64":
        builder, system, sdk = "metal_x86_64_dylib", False, "macosx"
        preset_host, export_arch = None, "x86_64"
        if suffix != ".dylib":
            issues.append("selected_x86_64_builder_requires_dylib_suffix")
    else:
        builder, sdk, preset_host, export_arch = "default_suffix_based", None, None, None
        system = suffix in (".tar", ".lib")
        if suffix not in (".tar", ".lib", ".so", ".dylib", ".dll"):
            warnings.append("default_builder_unknown_suffix_assumes_shared")
    if system and not resolved_prefix:
        warnings.append("static_prefix_missing_source_warns_not_rejects")
    if not system and resolved_prefix:
        warnings.append("shared_prefix_has_no_ir_attribute_effect")
    if prefix not in ("", "auto") and hint in ("iphone:generic", "macabi:generic"):
        warnings.append("literal_colon_hint_discards_explicit_prefix")
    if normalized_hint == "macabi:generic" and arch not in ("arm64", "x86_64"):
        warnings.append("invalid_macabi_arch_falls_back_to_arm64")
    return {
        "schema_version": 1,
        "status": "declared_builder_conflict" if issues else "target_declarations_screened_only",
        "normalized_target_hint": normalized_hint,
        "declared_target_kind": "metal",
        "selected_source_builder": builder,
        "system_library_declaration": system,
        "metal_compile_sdk_declaration": sdk,
        "export_arch_declaration": export_arch,
        "preset_host_triple": preset_host,
        "host_hint_effect": (
            "unused_preset_has_host" if preset_host else "requires_separate_host_target"
        ),
        "nonpreset_host_hint_declaration": None if preset_host else host,
        "resolved_prefix_literal": resolved_prefix,
        "prefix_ir_attribute_applied_by_declarations": system and bool(resolved_prefix),
        "issues": issues,
        "warnings": warnings,
        "compiler_check": "not_run",
        "native_verification": "not_run",
        "sdk_availability": "not_verified",
        "actual_artifact_abi_exports_and_format": "not_inspected",
        "runtime_eligibility": "not_verified",
        "physical_fit": "not_verified",
        "scope": "Selected source string rules only; no compiler callback registration, "
                 "host autodetection, SDK, artifact or device inspected.",
    }


def example() -> dict:
    return {"schema_version": 1, "target_hint": "iphone:generic", "output_suffix": ".tar",
            "host_hint": "auto", "prefix_hint": "auto", "model_name": "demo-model",
            "quantization": "q4f16_1", "macabi_arch": None}


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def nonfinite(_):
    raise ValueError("nonfinite JSON declaration")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "Invalid command line; use --help.\n")


def main() -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("input", nargs="?", help="regular JSON file or -/omitted stdin")
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
            raise ValueError("input exceeds 16 KiB")
        result = audit(json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                                  parse_constant=nonfinite))
    except (OSError, ValueError, UnicodeError, RecursionError):
        print("Invalid target declarations; use --example and the bundled contract.",
              file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
