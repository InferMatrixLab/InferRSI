#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Adapted from MLC LLM Contributors' artifact_manifest.py (2023-2025),
# mlc-ai/mlc-llm commit 8978ea9aec626d64096aaa92fbc89bda2e3ea802.
# Changed: dependency-free declaration schema, bounded validation, fixed diagnostics,
# metadata findings, and a deliberately narrower byte-aligned dtype/shape domain.
"""Audit normalized artifact declarations; no MLC/TVM imports or artifact reads.

Use --example for a synthetic input, then pass JSON on stdin or one regular file.
This helper computes metadata hashes and parameter bytes, not engine qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys

SOURCE_COMMIT = "8978ea9aec626d64096aaa92fbc89bda2e3ea802"
MAX_INPUT_BYTES = 65536
MAX_INTEGER = 2**63 - 1
DTYPE_BYTES = {"float16": 2, "float32": 4, "uint32": 4}
ROLE_PAIRS = (("prefill_tokens", "decode_tokens"), ("prefill_embeds", "decode_embeds"))


class DeclarationError(ValueError):
    """The declaration is outside the helper's strict supported input domain."""


def _require(condition: bool) -> None:
    if not condition:
        raise DeclarationError("invalid artifact declaration")


def _keys(value: object, required: set[str], optional: set[str] | None = None) -> dict:
    _require(type(value) is dict)
    _require(required <= value.keys() <= required | (optional or set()))
    return value


def _name(value: object) -> str:
    _require(type(value) is str and 1 <= len(value) <= 128)
    _require(all(char.isprintable() for char in value))
    return value


def _integer(value: object, *, minimum: int = 1) -> int:
    _require(type(value) is int and minimum <= value <= MAX_INTEGER)
    return value


def _list(value: object, maximum: int, minimum: int = 0) -> list:
    _require(type(value) is list and minimum <= len(value) <= maximum)
    return value


def _mapping(value: object, maximum: int, minimum: int = 0) -> dict:
    _require(type(value) is dict and minimum <= len(value) <= maximum)
    for key in value:
        _name(key)
    return value


def _bounded_json_tree(value: object) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        _require(depth <= 12 and nodes <= 4096)
        if type(item) is dict:
            _require(all(type(key) is str for key in item))
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            _require(len(item) <= 256)
        else:
            _require(item is None or type(item) in (int, bool))
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, OverflowError) as error:
        raise DeclarationError("invalid artifact declaration") from error
    _require(len(encoded) <= MAX_INPUT_BYTES)


def _processor(value: object) -> None:
    if type(value) is str:
        _name(value)
        return
    _require(type(value) is dict)
    if value.get("kind") == "audio_decode":
        audio = _keys(value, {
            "kind", "format", "sample_rate_hz", "channels", "min_samples", "max_samples"
        })
        _require(audio["format"] == "pcm_f32")
        _require(type(audio["channels"]) is int and audio["channels"] == 1)
        _integer(audio["sample_rate_hz"])
        _require(_integer(audio["min_samples"]) <= _integer(audio["max_samples"]))
    else:
        image = _keys(value, {"kind", "format", "layout", "resize", "num_embeddings"})
        _require(image["kind"] == "image_decode" and image["format"] == "rgb_u8")
        _require(image["layout"] == "nhwc")
        resize = _keys(image["resize"], {"mode", "height", "width"})
        _require(resize["mode"] in ("stretch", "center_crop"))
        _integer(resize["height"])
        _integer(resize["width"])
        _integer(image["num_embeddings"])


def _tasks(value: object) -> dict:
    tasks = _mapping(value, 16, 1)
    for task in tasks.values():
        task = _keys(task, {"executor", "inputs", "output"})
        _name(task["executor"])
        _name(task["output"])
        for item in _mapping(task["inputs"], 16, 1).values():
            item = _keys(item, {"processor"}, {"adapter", "prompt"})
            _processor(item["processor"])
            _require(("adapter" in item) == ("prompt" in item))
            if "adapter" in item:
                _name(item["adapter"])
                prompt = _keys(item["prompt"], {
                    "prefix_token_ids", "placeholder_token_id", "suffix_token_ids"
                })
                _integer(prompt["placeholder_token_id"], minimum=0)
                for field in ("prefix_token_ids", "suffix_token_ids"):
                    for token in _list(prompt[field], 128):
                        _integer(token, minimum=0)
    return tasks


def _programs(value: object) -> tuple[dict, list[str]]:
    programs = _mapping(value, 16, 1)
    findings = []
    for program in programs.values():
        program = _keys(program, {"kind", "exports", "adapters"}, {"adapter_dtypes"})
        _name(program["kind"])
        exports = _mapping(program["exports"], 32, 1)
        adapters = _mapping(program["adapters"], 16)
        for symbol in (*exports.values(), *adapters.values()):
            _name(symbol)
        if "adapter_dtypes" in program:
            for name, dtype in _mapping(program["adapter_dtypes"], 16, 1).items():
                _require(type(dtype) is str and dtype in DTYPE_BYTES)
                if name not in adapters:
                    findings.append("adapter_dtype_references_missing_adapter")
        if program["kind"] == "token_generation":
            if not {"embed_tokens", "create_kv_cache"} <= exports.keys():
                findings.append("token_generation_missing_required_role")
            declared = [pair for pair in ROLE_PAIRS if any(role in exports for role in pair)]
            if not declared or not all(role in exports for pair in declared for role in pair):
                findings.append("token_generation_incomplete_role_pair")
    return programs, findings


def _product(left: int, right: int) -> int:
    _require(right == 0 or left <= MAX_INTEGER // right)
    return left * right


def _parameters(value: object, symbolic_sizes: object) -> tuple[list, int, int]:
    sizes = _mapping(symbolic_sizes, 32)
    for size in sizes.values():
        _integer(size)
    parameters = _list(value, 128)
    records = []
    names = set()
    total = maximum = 0
    for parameter in parameters:
        parameter = _keys(parameter, {"name", "shape", "dtype"})
        name = _name(parameter["name"])
        _require(name not in names)
        names.add(name)
        dtype = parameter["dtype"]
        _require(type(dtype) is str and dtype in DTYPE_BYTES)
        shape = _list(parameter["shape"], 8)
        elements = 1
        for dimension in shape:
            if type(dimension) is str:
                _name(dimension)
                _require(dimension in sizes)
                concrete = sizes[dimension]
            else:
                concrete = _integer(dimension)
            elements = _product(elements, concrete)
        byte_size = _product(elements, DTYPE_BYTES[dtype])
        _require(total <= MAX_INTEGER - byte_size)
        total += byte_size
        maximum = max(maximum, byte_size)
        records.append({"name": name, "shape": shape, "dtype": dtype})
    return sorted(records, key=lambda item: item["name"]), maximum, total


def _hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    _require(type(value) is str and value.startswith("sha256:") and len(value) == 71)
    _require(all(char in "0123456789abcdef" for char in value[7:]))
    return value


def audit(plan: object) -> dict:
    """Compute restricted normalized-declaration hashes and fixed-code findings.

    Malformed/unsupported input raises DeclarationError, a ValueError subclass.
    Well-formed contradictory metadata returns metadata_consistent=False; it is
    never evidence that a compiled program or its weights were inspected.
    """
    _bounded_json_tree(plan)
    plan = _keys(plan, {
        "schema_version", "tasks", "programs", "parameters", "symbolic_sizes",
        "required_features", "declared_ids"
    })
    _require(type(plan["schema_version"]) is int and plan["schema_version"] == 1)
    tasks = _tasks(plan["tasks"])
    programs, findings = _programs(plan["programs"])
    parameters, maximum, total = _parameters(plan["parameters"], plan["symbolic_sizes"])
    features = _list(plan["required_features"], 32)
    for feature in features:
        _name(feature)
    for task in tasks.values():
        program = programs.get(task["executor"])
        if program is None:
            findings.append("task_references_missing_executor")
            continue
        for item in task["inputs"].values():
            if "adapter" in item and item["adapter"] not in program["adapters"]:
                findings.append("task_references_missing_adapter")
    interface_id = _hash({"tasks": tasks})
    parameter_schema_id = _hash(parameters)
    declared = plan["declared_ids"]
    id_fields = {
        "package_interface_id": interface_id,
        "compiled_interface_id": interface_id,
        "package_parameter_schema_id": parameter_schema_id,
        "compiled_parameter_schema_id": parameter_schema_id,
    }
    if declared is not None:
        declared = _keys(declared, set(id_fields))
        for field, expected in id_fields.items():
            if _digest(declared[field]) != expected:
                findings.append(field + "_mismatch")
    return {
        "schema_version": 1,
        "source_repository": "mlc-ai/mlc-llm",
        "source_commit": SOURCE_COMMIT,
        "scope": "caller_declared_normalized_metadata_only",
        "interface_id": interface_id,
        "parameter_schema_id": parameter_schema_id,
        "declared_id_comparison": "not_supplied" if declared is None else "performed",
        "metadata_consistent": not findings,
        "findings": sorted(set(findings)),
        "task_count": len(tasks),
        "program_count": len(programs),
        "parameter_count": len(parameters),
        "resources": {
            "max_storage_buffer_binding_size": maximum,
            "estimated_device_memory_bytes": total,
            "unique_required_feature_count": len(set(features)),
            "scope": "parameter_storage_only_excludes_kv_and_runtime_allocations",
        },
        "weight_bytes": "not_read",
        "exports_and_abi": "not_verified",
        "device_features_and_memory_fit": "not_assessed",
        "compiler_check": "not_run",
        "native_execution": "not_run",
    }


def example() -> dict:
    """Return fresh synthetic metadata, not a real model or compiled artifact."""
    return {
        "schema_version": 1,
        "tasks": {"chat.completions": {
            "executor": "generation", "inputs": {"text": {"processor": "tokenizer"}},
            "output": "text",
        }},
        "programs": {"generation": {
            "kind": "token_generation",
            "exports": {
                "embed_tokens": "embed", "create_kv_cache": "create_tir_paged_kv_cache",
                "prefill_embeds": "prefill", "decode_embeds": "decode",
            },
            "adapters": {},
        }},
        "parameters": [
            {"name": "b", "shape": [5], "dtype": "uint32"},
            {"name": "a", "shape": [2, 3], "dtype": "float16"},
        ],
        "symbolic_sizes": {}, "required_features": ["shader-f16", "shader-f16"],
        "declared_ids": None,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "invalid arguments; use --help\n")


def _no_duplicates(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise DeclarationError("invalid JSON constant")


def _read_input(path: str | None) -> bytes:
    if path is None or path == "-":
        return sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode))
        return stream.read(MAX_INPUT_BYTES + 1)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("input_file", nargs="?", help="one regular JSON file, or - for stdin")
    parser.add_argument("--example", action="store_true", help="print synthetic input only")
    args = parser.parse_args(argv)
    if args.example:
        if args.input_file is not None:
            parser.error("conflicting input")
        print(json.dumps(example(), indent=2, ensure_ascii=False))
        return 0
    try:
        raw = _read_input(args.input_file)
        _require(len(raw) <= MAX_INPUT_BYTES)
        plan = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
                          parse_constant=_reject_constant)
        result = audit(plan)
    except (OSError, ValueError, RecursionError, OverflowError):
        print("invalid artifact declaration or input; use --help", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
