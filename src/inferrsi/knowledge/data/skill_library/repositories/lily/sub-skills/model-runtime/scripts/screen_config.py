#!/usr/bin/env python3
"""Screen selected Lily config predicates, never complete model compatibility.

Adapted into Python from perplexityai/pplx-garden/lily/src/config.rs:122-182
at 1ed972ed3f0bd5616c997c9507c25616c63394fc (Apache-2.0; retain owner notices).
Sequence screening follows serve.rs:148-150 and attention.rs:10.
Changes: selected JSON predicates only, explicit unchecked scope and CLI JSON;
no serde/Rust equivalence, weight reads, tokenizer, model import or device use.
Example: python screen_config.py --config public-config.json --max-seq 4096
"""

import argparse
import json
from pathlib import Path

EXPECTED = {
    "hidden_size": 2048, "num_hidden_layers": 40, "vocab_size": 248320,
    "num_experts": 256, "num_experts_per_tok": 8, "moe_intermediate_size": 512,
    "shared_expert_intermediate_size": 512, "num_attention_heads": 16,
    "num_key_value_heads": 2, "head_dim": 256, "linear_num_key_heads": 16,
    "linear_num_value_heads": 32, "linear_key_head_dim": 128,
    "linear_value_head_dim": 128, "linear_conv_kernel_dim": 4,
}
UNCHECKED = [
    "remaining required Rust/serde fields, EOS, RMS epsilon and RoPE validity",
    "tensor names, shapes, per-role Q8 exceptions, dtypes, packing and payload bytes",
    "tokenizer/template and actual request token budget",
    "Rust1.92 compilation, Metal shaders/device execution, memory fit and quality",
]


def screen_config(config, max_seq=None):
    """Return selected-rule findings; successful screening is not native acceptance."""
    errors = []
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    if config.get("model_type") != "qwen3_5_moe":
        errors.append("model_type must be qwen3_5_moe")
    text = config.get("text_config")
    if not isinstance(text, dict):
        raise ValueError("text_config must be a JSON object")
    for name, expected in EXPECTED.items():
        if type(text.get(name)) is not int or text[name] != expected:
            errors.append(f"text_config.{name} must equal {expected}")
    for name, expected in (("attn_output_gate", True), ("tie_word_embeddings", False)):
        if text.get(name) is not expected:
            errors.append(f"text_config.{name} must be {str(expected).lower()}")
    layers = ["full_attention" if i % 4 == 3 else "linear_attention" for i in range(40)]
    if text.get("layer_types") != layers:
        errors.append(
            "layer_types must repeat three linear_attention then full_attention, 40 total"
        )
    quant = config.get("quantization")
    if not isinstance(quant, dict):
        errors.append("top-level quantization object is required")
    elif (quant.get("mode") not in (None, "affine")
          or type(quant.get("bits")) is not int or quant["bits"] != 4
          or type(quant.get("group_size")) is not int or quant["group_size"] != 64):
        errors.append("quantization must be affine bits=4 group_size=64")
    declared = text.get("max_position_embeddings", 0)
    effective = None
    if type(declared) is not int or declared < 0:
        errors.append("max_position_embeddings must be a nonnegative integer if supplied")
    elif max_seq is not None:
        if type(max_seq) is not int or max_seq < 2:
            errors.append("requested max_seq must be an integer at least 2")
        else:
            effective = min(max_seq, declared) if declared else max_seq
            if not 2 <= effective <= 262144:
                errors.append("effective max_seq must be 2..262144 after checkpoint clamp")
    return {"status": "failed_selected_rules" if errors else "passed_selected_rules",
            "screen_only": True, "native_validation": "not_run", "errors": errors,
            "effective_sequence_ceiling": effective, "unchecked": UNCHECKED}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--max-seq", type=int)
    args = parser.parse_args(argv)
    try:
        result = screen_config(json.loads(args.config.read_text(encoding="utf-8")), args.max_seq)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
