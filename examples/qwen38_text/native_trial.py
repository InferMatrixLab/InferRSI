"""Bounded native text teacher-forcing smoke; no performance/engine acceptance claim."""

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from . import trial
    from .profiles import FP8_MODEL_ID, MODEL_IDS, precision, validate_native_loading
    from .provenance import capture_sources, import_native
else:
    import trial
    from profiles import FP8_MODEL_ID, MODEL_IDS, precision, validate_native_loading
    from provenance import capture_sources, import_native


NATIVE_POLICY = {"implementation": "native_torch", "full_attention": "eager",
                 "deltanet": "torch", "cuda_graph": False, "tensor_parallel_size": 1}


def run(args):
    model_id = getattr(args, "model_id", trial.MODEL_ID)
    manifest_hash = trial.verify_manifest(
        args.model_path, args.manifest, args.model_revision, model_id,
    )
    cases, workload_hash = trial.load_workload(args.workload, model_id)
    config = json.loads(trial.model_file(args.model_path, "config.json").read_bytes())
    vocab_size = config["text_config"]["vocab_size"]
    if type(vocab_size) is not int or vocab_size <= 0:
        raise ValueError("Expected positive vocabulary size")
    if args.output.exists():
        raise ValueError("Refusing to overwrite existing trial result")
    import numpy as np
    import torch
    import transformers
    from transformers import AutoTokenizer

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("Native trial requires exactly one visible CUDA GPU")
    if not torch.cuda.is_bf16_supported() or torch.cuda.get_device_name(0) != args.device_model:
        raise ValueError("Native trial GPU/precision differs from requested target")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path, local_files_only=True, trust_remote_code=False,
    )
    tokens = [trial.tokenize_case(tokenizer, case) for case in cases]
    load_checkpoint, request_runner = import_native(args.engine_repo)
    model, loading = load_checkpoint(args.model_path, device="cuda:0")
    validate_native_loading(loading, model_id)
    if model_id == FP8_MODEL_ID:
        # Inspect actual tensors, not just the loader's precision label.
        count = 0
        for module in model.modules():
            if (type(module).__module__ == "nanovllm.qwen38.quant"
                    and type(module).__name__ == "FP8Linear"):
                count += 1
                if (module.weight.dtype != torch.float8_e4m3fn
                        or module.weight_scale_inv.dtype != torch.float32):
                    raise ValueError("Native FP8 linear was dequantized")
        if count != loading["fp8_linear_modules"]:
            raise ValueError("Native FP8 module coverage differs from loading report")
    model.eval()
    sources = capture_sources(args.engine_repo, excluded_run_dir=args.output.parents[2])
    model_module = type(model).__module__
    if model_module not in sources["engine"]["imports"]:
        raise ValueError("Native model class did not originate in the engine checkout")
    max_context = max(len(prompt) + len(continuation) for prompt, continuation in tokens)
    engine = request_runner(
        model, tokenizer, max_context_tokens=max_context, max_active_requests=1,
        vocab_size=vocab_size, device="cuda:0",
    )
    result = {
        "schema_version": 1, "qualification_scope": "native_text_smoke",
        "implementation": "nanovllm_qwen38", "model_id": model_id,
        "model_revision": args.model_revision, "manifest_sha256": manifest_hash,
        "workload_sha256": workload_hash,
        "dtype": "fp8" if model_id == FP8_MODEL_ID else "bfloat16",
        "precision": precision(model_id), "device_type": "cuda",
        "device_count": 1, "device_model": torch.cuda.get_device_name(0),
        "vocab_size": vocab_size, "tokenization": "raw_text_no_special_tokens",
        "kernel_policy": ({**NATIVE_POLICY, "fp8_linear": "triton_block_fp8"}
                          if model_id == FP8_MODEL_ID else NATIVE_POLICY),
        "source_provenance": sources,
        "native_model_module": model_module, "loading": loading,
        "versions": {"torch": torch.__version__, "transformers": transformers.__version__,
                     "numpy": np.__version__, "cuda": torch.version.cuda}, "cases": [],
    }

    if model_id == FP8_MODEL_ID:
        from importlib.metadata import version
        result["versions"].update(kernels=version("kernels"), triton=version("triton"))

    def collect(prompt, continuation):
        rows = engine.trace_teacher_forced(prompt, continuation)
        if engine.active_request_ids:
            raise ValueError("Native trace retained request state")
        return [row.float().cpu().numpy() for row in rows]

    def finalize(record):
        # Capture lazy kernel imports after actual execution, before serializing evidence.
        record["source_provenance"] = capture_sources(
            args.engine_repo, excluded_run_dir=args.output.parents[2],
        )
        if model_id == FP8_MODEL_ID:
            calls = [getattr(module, "native_fp8_calls", 0) for module in model.modules()
                     if type(module).__module__ == "nanovllm.qwen38.quant"
                     and type(module).__name__ == "FP8Linear"]
            if (len(calls) != loading["fp8_linear_modules"]
                    or not all(type(value) is int and value > 0 for value in calls)):
                raise ValueError("Native FP8 linears did not execute completely")
            record["fp8_execution"] = {"modules": len(calls), "total_calls": sum(calls)}

    return trial.write_traces(result, args.output, cases, tokens, collect, finalize)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model-path", "manifest", "workload", "engine-repo", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--model-id", choices=MODEL_IDS, default=trial.MODEL_ID)
    parser.add_argument("--device-model", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        print(f"Native trial incomplete ({type(error).__name__}); no qualification verdict",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
