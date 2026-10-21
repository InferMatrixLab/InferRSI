"""GPU-only reference self-check: recomputation versus Transformers cache.

This trial does not implement or qualify the nano-vllm derived engine. Optional
GPU dependencies are imported only after input integrity checks.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath

if __package__:
    from .profiles import (
        BF16_MODEL_ID,
        FP8_MODEL_ID,
        MODEL_IDS,
        check_precision,
        precision,
        validate_config,
    )
else:
    from profiles import (
        BF16_MODEL_ID,
        FP8_MODEL_ID,
        MODEL_IDS,
        check_precision,
        precision,
        validate_config,
    )

MODEL_ID = BF16_MODEL_ID
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
METADATA = {
    "config.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "generation_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab.json",
    "merges.txt",
    "chat_template.jinja",
}
REQUIRED = {
    "config.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "model.safetensors.index.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_file(root: Path, name: str) -> Path:
    """Resolve only canonical relative names whose final target stays in root."""
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Invalid manifest file name")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
        raise ValueError("Manifest file name must be a canonical relative path")
    resolved = (root / name).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Manifest file escapes model directory or is not a file")
    return resolved


def verify_manifest(root: Path, manifest_path: Path, revision: str,
                    model_id: str = MODEL_ID) -> str:
    """Read and hash every frozen file; size/mtime are never integrity evidence."""
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not HEX40.fullmatch(revision):
        raise ValueError("Model revision must be a lowercase 40-character commit")
    if manifest.get("model_id") != model_id or manifest.get("revision") != revision:
        raise ValueError("Manifest model identity differs from requested identity")
    check_precision(manifest, model_id)
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("Manifest files must be nonempty")
    covered = set()
    for record in records:
        name, digest, size = record.get("path"), record.get("sha256"), record.get("size")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ValueError("Every manifest entry requires SHA-256")
        if type(size) is not int or size < 0 or name in covered:
            raise ValueError("Invalid size or duplicate manifest entry")
        path = model_file(root, name)
        if path.stat().st_size != size or sha256_file(path) != digest:
            raise ValueError("Model file integrity mismatch")
        covered.add(name)
    if not REQUIRED <= covered:
        raise ValueError("Manifest omits required model/tokenizer/index metadata")
    for name in METADATA:
        if (root / name).exists() and name not in covered:
            raise ValueError("Manifest omits present tokenizer or generation metadata")
    index = json.loads(model_file(root, "model.safetensors.index.json").read_bytes())
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ValueError("Weight index must contain a nonempty weight map")
    for name in weight_map.values():
        model_file(root, name)
        if not name.endswith(".safetensors") or name not in covered:
            raise ValueError("Manifest omits an indexed safetensors shard")
    config = json.loads(model_file(root, "config.json").read_bytes())
    validate_config(config, model_id)
    return hashlib.sha256(manifest_bytes).hexdigest()


def load_workload(path: Path, model_id: str = MODEL_ID) -> tuple[list[dict], str]:
    workload_bytes = path.read_bytes()
    workload = json.loads(workload_bytes)
    cases = workload.get("cases")
    if (
        workload.get("schema_version") != 1
        or workload.get("model_id") != model_id
        or not isinstance(cases, list)
        or not cases
    ):
        raise ValueError("Invalid or empty workload")
    check_precision(workload, model_id)
    seen = set()
    for case in cases:
        name = case.get("id")
        if (
            not isinstance(name, str)
            or not CASE_ID.fullmatch(name)
            or name in seen
            or not isinstance(case.get("prompt"), str)
            or not case["prompt"]
            or not isinstance(case.get("continuation"), str)
            or not case["continuation"]
            or type(case.get("max_steps")) is not int
            or case["max_steps"] <= 0
        ):
            raise ValueError("Invalid or duplicate workload case")
        seen.add(name)
    return cases, hashlib.sha256(workload_bytes).hexdigest()


def tokenize_case(tokenizer, case: dict) -> tuple[list[int], list[int]]:
    prompt = tokenizer.encode(case["prompt"], add_special_tokens=False)
    continuation = tokenizer.encode(case["continuation"], add_special_tokens=False)
    steps = case["max_steps"]
    if not prompt or len(continuation) < steps:
        raise ValueError("Empty tokenized prompt or insufficient teacher-forcing tokens")
    return prompt, continuation[:steps]


def collect_logits(model, torch, prompt: list[int], continuation: list[int], mode: str):
    """Each row predicts one fixed continuation token; never feed sampled tokens."""
    if mode not in {"full", "cached"}:
        raise ValueError("Unknown reference mode")
    rows = []
    cache = None
    with torch.inference_mode():
        for step in range(len(continuation)):
            ids = prompt + continuation[:step]
            if mode == "cached" and step:
                ids = continuation[step - 1 : step]
            inputs = torch.tensor([ids], dtype=torch.long, device="cuda:0")
            outputs = model(
                input_ids=inputs,
                use_cache=mode == "cached",
                past_key_values=cache,
                logits_to_keep=1,
                return_dict=True,
            )
            row = outputs.logits[0, -1].detach().float().cpu().numpy()
            rows.append(row)
            if mode == "cached":
                cache = outputs.past_key_values
                if cache is None:
                    raise ValueError("Cached mode did not return cache state")
    return rows


def kernel_policy() -> dict:
    """This reference deliberately fixes Torch fallback, not optional kernels."""
    optional = {
        name: importlib.util.find_spec(name) is not None for name in ("fla", "causal_conv1d")
    }
    if any(optional.values()):
        raise ValueError("Reference self-check requires optional DeltaNet kernels to be absent")
    return {"hub_kernels": False, "full_attention": "eager", "optional_modules": optional}


def run(args: argparse.Namespace) -> dict:
    scope = getattr(args, "qualification_scope", "reference_self_check")
    if scope not in {"reference_self_check", "native_text_smoke"}:
        raise ValueError("Unknown qualification scope")
    if scope == "native_text_smoke" and args.mode != "full":
        raise ValueError("Native smoke reference must use full-prefix recomputation")
    model_id = getattr(args, "model_id", MODEL_ID)
    manifest_hash = verify_manifest(args.model_path, args.manifest, args.model_revision, model_id)
    cases, workload_hash = load_workload(args.workload, model_id)
    config = json.loads(model_file(args.model_path, "config.json").read_bytes())
    vocab_size = config["text_config"]["vocab_size"]
    if type(vocab_size) is not int or vocab_size <= 0:
        raise ValueError("Expected positive text vocabulary size")
    if args.output.exists():
        raise ValueError("Refusing to overwrite an existing trial result")
    policy = kernel_policy()
    reference_kernel = None
    if model_id == FP8_MODEL_ID:
        if __package__:
            from .fp8_reference import prepare_reference_kernel
        else:
            from fp8_reference import prepare_reference_kernel
        reference_kernel = prepare_reference_kernel(
            args.fp8_kernel_revision, args.fp8_kernel_sha256,
        )
        policy = {**policy, "fp8_linear": "finegrained_fp8", "deepgemm": False}
    # CPU-only smoke checks must not import optional GPU packages.
    import numpy as np
    import torch
    import transformers
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("Trial requires exactly one visible CUDA GPU")
    if not torch.cuda.is_bf16_supported():
        raise ValueError("Visible CUDA GPU does not support BF16")
    if torch.cuda.get_device_name(0) != args.device_model:
        raise ValueError("Visible CUDA GPU differs from frozen device model")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    tokens = [tokenize_case(tokenizer, case) for case in cases]
    model, loading = Qwen3_5ForConditionalGeneration.from_pretrained(
        args.model_path,
        dtype=torch.bfloat16,
        device_map={"": "cuda:0"},
        local_files_only=True,
        trust_remote_code=False,
        use_safetensors=True,
        attn_implementation="eager",
        use_kernels=False,
        output_loading_info=True,
    )
    if any(loading.get(key) for key in ("missing_keys", "mismatched_keys", "error_msgs")):
        raise ValueError("Reference checkpoint did not load all required parameters")
    fp8_loading = None
    if model_id == FP8_MODEL_ID:
        if __package__:
            from .fp8_reference import inspect_reference_fp8
        else:
            from fp8_reference import inspect_reference_fp8
        from transformers.integrations.finegrained_fp8 import FP8Linear
        index = json.loads(model_file(args.model_path, "model.safetensors.index.json").read_bytes())
        expected_count = sum(name.startswith("model.language_model.layers.")
                             and name.endswith(".weight_scale_inv") for name in index["weight_map"])
        fp8_loading = inspect_reference_fp8(model, torch, FP8Linear, expected_count)
    model.eval()
    result = {
        "schema_version": 1,
        "qualification_scope": scope,
        "implementation": "transformers_" + args.mode,
        "model_id": model_id,
        "model_revision": args.model_revision,
        "manifest_sha256": manifest_hash,
        "workload_sha256": workload_hash,
        "dtype": "fp8" if model_id == FP8_MODEL_ID else "bfloat16",
        "precision": precision(model_id),
        "device_type": "cuda",
        "device_count": 1,
        "device_model": torch.cuda.get_device_name(0),
        "vocab_size": vocab_size,
        "tokenization": "raw_text_no_special_tokens",
        "kernel_policy": policy,
        "versions": {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
            "cuda": torch.version.cuda,
        },
        "cases": [],
    }
    if reference_kernel is not None:
        from importlib.metadata import version
        result["versions"].update(kernels=version("kernels"), triton=version("triton"))
        result["reference_kernel"] = reference_kernel
        result["fp8_loading"] = fp8_loading
    if scope == "native_text_smoke":
        if __package__:
            from .provenance import capture_sources
        else:
            from provenance import capture_sources
        result["source_provenance"] = capture_sources(excluded_run_dir=args.output.parents[2])
    return write_traces(
        result, args.output, cases, tokens,
        lambda prompt, continuation: collect_logits(model, torch, prompt, continuation, args.mode),
    )


def write_traces(result, output, cases, tokens, collect, finalize=None):
    """Write the shared full-vocabulary observation format for either implementation."""
    import numpy as np

    vocab_size = result["vocab_size"]
    output.parent.mkdir(parents=True, exist_ok=True)
    for case, (prompt, continuation) in zip(cases, tokens):
        rows = collect(prompt, continuation)
        logits = np.stack(rows)
        if logits.shape != (case["max_steps"], vocab_size) or not np.isfinite(logits).all():
            raise ValueError("Model produced invalid logits")
        logits_path = output.with_name(output.stem + "-" + case["id"] + ".npz")
        with logits_path.open("xb") as stream:
            np.savez(stream, logits=logits)
        result["cases"].append(
            {
                "id": case["id"],
                "input_ids": prompt,
                "continuation_ids": continuation,
                "logits_file": logits_path.name,
                "logits_sha256": sha256_file(logits_path),
                "greedy_ids": logits.argmax(axis=1).tolist(),
            }
        )
    if finalize is not None:
        finalize(result)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--model-id", choices=MODEL_IDS, default=MODEL_ID)
    parser.add_argument("--fp8-kernel-revision")
    parser.add_argument("--fp8-kernel-sha256")
    parser.add_argument("--device-model", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--mode", choices=("full", "cached"), required=True)
    parser.add_argument("--qualification-scope", default="reference_self_check",
                        choices=("reference_self_check", "native_text_smoke"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run(args)
    except Exception as error:
        # Exceptions from libraries/filesystems can contain personal runtime paths.
        print(
            f"Trial incomplete ({type(error).__name__}); no qualification verdict", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
