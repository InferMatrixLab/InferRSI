"""Bounded native text teacher-forcing smoke; no performance/engine acceptance claim."""

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from . import trial
    from .provenance import capture_sources, import_native
else:
    import trial
    from provenance import capture_sources, import_native


NATIVE_POLICY = {"implementation": "native_torch", "full_attention": "eager",
                 "deltanet": "torch", "cuda_graph": False, "tensor_parallel_size": 1}


def run(args):
    manifest_hash = trial.verify_manifest(args.model_path, args.manifest, args.model_revision)
    cases, workload_hash = trial.load_workload(args.workload)
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
    if (loading.get("scope") != "text_only" or loading.get("dtype") != "bfloat16"
            or type(loading.get("loaded_parameters")) is not int
            or loading["loaded_parameters"] <= 0):
        raise ValueError("Native checkpoint loader did not establish BF16 text coverage")
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
        "implementation": "nanovllm_qwen38", "model_id": trial.MODEL_ID,
        "model_revision": args.model_revision, "manifest_sha256": manifest_hash,
        "workload_sha256": workload_hash, "dtype": "bfloat16", "device_type": "cuda",
        "device_count": 1, "device_model": torch.cuda.get_device_name(0),
        "vocab_size": vocab_size, "tokenization": "raw_text_no_special_tokens",
        "kernel_policy": NATIVE_POLICY, "source_provenance": sources,
        "native_model_module": model_module, "loading": loading,
        "versions": {"torch": torch.__version__, "transformers": transformers.__version__,
                     "numpy": np.__version__, "cuda": torch.version.cuda}, "cases": [],
    }

    def collect(prompt, continuation):
        rows = engine.trace_teacher_forced(prompt, continuation)
        if engine.active_request_ids:
            raise ValueError("Native trace retained request state")
        return [row.float().cpu().numpy() for row in rows]

    return trial.write_traces(result, args.output, cases, tokens, collect)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model-path", "manifest", "workload", "engine-repo", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
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
