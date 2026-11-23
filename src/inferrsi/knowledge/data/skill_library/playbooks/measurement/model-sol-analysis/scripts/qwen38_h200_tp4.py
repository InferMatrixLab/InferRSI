"""Replay the fixed Qwen3.8-Flash-Next BF16 / H200 SXM TP4 paper analysis."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from model_sol import kv_cache_bytes, phase_floors
from qwen38_checkpoint import audit_headers, schema_digest

FACTS = Path(__file__).resolve().parents[1] / "references/qwen38-h200-tp4.json"
TP = 4
BF16 = 2
SOURCE = {"kind": "derived", "locator": "references/qwen38-h200-tp4.md"}


def ngram_shard_shape(c):
    # vLLM builds one prime-sized vocabulary per n-gram head, pads the
    # concatenation, then maps the checkpoint shards onto ETP vocabulary owners.
    heads = (c["ngram_size"] - 1) * c["heads_per_ngram"]
    candidate = c["ngram_vocab_size_base"]
    rows = 0
    for _ in range(heads):
        while any(candidate % d == 0 for d in range(2, math.isqrt(candidate) + 1)):
            candidate += 1
        rows += candidate
        candidate += 1
    pad = c["make_ngram_vocab_size_divisible_by"]
    rows = (rows + pad - 1) // pad * pad
    return rows // c["split_ngram_parts"], c["ple_embed_dim"] // heads


class WeightLedger:
    """Logical checkpoint storage and TP placement before engine repacking."""

    def __init__(self):
        self.headers = {}
        self.rank_bytes = Counter()
        self.stored_bytes = 0

    def add(self, name, shape, group="auxiliary", *, axis=None, ways=TP, dtype="BF16", owner=None):
        if name in self.headers:
            raise ValueError(f"Duplicated inventory name: {name}")
        self.headers[name] = {"dtype": dtype, "shape": list(shape)}
        size = math.prod(shape) * {"BF16": BF16, "I64": 8}[dtype]
        self.stored_bytes += size
        if axis is not None:
            if shape[axis] % ways:
                raise ValueError(f"Cannot split {name} on axis {axis} into {ways}")
            size //= ways
        if owner is None or owner == 0:
            self.rank_bytes[group] += size


def text_weights(c):
    ledger = WeightLedger()
    h, streams, low = c["hidden_size"], c["hc_count"], c["hc_lowrank"]
    wide = h * streams
    e, m = c["num_experts"], c["moe_intermediate_size"]
    shared = c["shared_expert_intermediate_size"]
    d, q, kv = c["head_dim"], c["num_attention_heads"], c["num_key_value_heads"]
    vk = c["linear_num_value_heads"]
    v = vk * c["linear_value_head_dim"]
    k = c["linear_num_key_heads"] * c["linear_key_head_dim"]
    index_width = (c["indexer_n_heads"] + c["indexer_kv_heads"]) * c["indexer_head_dim"]

    def mixer(prefix, inject):
        ledger.add(prefix + "hc_norm.weight", (wide,))
        ledger.add(prefix + "input_mix_weight_down.weight", (low, wide), "residual")
        ledger.add(prefix + "input_mix_weight_up.weight", (wide, low), "residual")
        if inject:
            ledger.add(prefix + "block_inject_weight.weight", (streams, wide), "residual")

    root = "model.language_model."
    ledger.add("lm_head.weight", (c["vocab_size"], h), "logits", axis=0)
    ledger.add(root + "embed_tokens.weight", (c["vocab_size"], h), "embedding", axis=0)
    mixer(root + "hyper_connection_mixer.", False)
    for layer in range(c["num_hidden_layers"]):
        prefix = f"{root}layers.{layer}."
        mixer(prefix + "attn_hyper_connection.", True)
        mixer(prefix + "mlp_hyper_connection.", True)
        mlp = prefix + "mlp."
        ledger.add(mlp + "experts.gate_up_proj", (e, 2 * m, h), "routed", axis=1)
        ledger.add(mlp + "experts.down_proj", (e, h, m), "routed", axis=2)
        ledger.add(mlp + "gate.weight", (e, h), "router")
        ledger.add(mlp + "shared_expert_gate.weight", (1, h), "router")
        for proj in ("gate_proj", "up_proj"):
            ledger.add(mlp + "shared_expert." + proj + ".weight", (shared, h), "shared", axis=0)
        ledger.add(mlp + "shared_expert.down_proj.weight", (h, shared), "shared", axis=1)

        if (layer + 1) % c["full_attention_interval"] == 0:
            attn = prefix + "self_attn."
            ledger.add(attn + "q_proj.weight", (2 * q * d, h), "qsa", axis=0)
            for proj in ("k_proj", "v_proj"):
                # Two distinct KV heads across four ranks, two replicas per head.
                ledger.add(attn + proj + ".weight", (kv * d, h), "qsa", axis=0, ways=kv)
            ledger.add(attn + "o_proj.weight", (h, q * d), "qsa", axis=1)
            ledger.add(attn + "indexer.index_qk_proj.weight", (index_width, h), "qsa")
            for norm in ("q_norm", "k_norm"):
                ledger.add(attn + norm + ".weight", (d,))
            for norm in ("q_layernorm", "k_layernorm"):
                ledger.add(attn + "indexer." + norm + ".weight", (c["indexer_head_dim"],))
        else:
            attn = prefix + "linear_attn."
            for proj, dim in (("a", vk), ("b", vk), ("qkv", 2 * k + v), ("z", v)):
                ledger.add(attn + f"in_proj_{proj}.weight", (dim, h), "gdn", axis=0)
            ledger.add(attn + "out_proj.weight", (h, v), "gdn", axis=1)
            ledger.add(attn + "conv1d.weight", (2 * k + v, 1, c["linear_conv_kernel_dim"]), axis=0)
            ledger.add(attn + "norm.weight", (c["linear_value_head_dim"],))
            for vector in ("A_log", "dt_bias"):
                ledger.add(attn + vector, (vk,), axis=0)

        if layer + 1 in c["ple_layer_ids"]:
            ple = prefix + "ple."
            ledger.add(ple + "key_proj.weight", (wide, c["ple_embed_dim"]), "ple")
            ledger.add(ple + "value_proj.weight", (h, c["ple_embed_dim"]), "ple")
            ledger.add(ple + "conv1d.weight", (wide, 1, c["ple_conv_kernel_size"]))
            for norm in ("norm_conv", "norm_key", "norm_query"):
                ledger.add(ple + norm + ".weight", (wide,))
            emb = ple + "ple_embedding."
            heads = (c["ngram_size"] - 1) * c["heads_per_ngram"]
            ledger.add(emb + "layer_multipliers", (c["ngram_size"],), dtype="I64")
            for vector in ("ngram_heads_offsets", "ngram_heads_vocab_sizes"):
                ledger.add(emb + vector, (heads,), dtype="I64")
            shape = ngram_shard_shape(c)
            for shard in range(c["split_ngram_parts"]):
                ledger.add(emb + f"ngram_embedding.shard_{shard}.weight", shape, "ngram",
                           owner=shard // (c["split_ngram_parts"] // TP))
    return ledger


def cache_payload(c, context):
    layers = c["num_hidden_layers"]
    qsa = layers // c["full_attention_interval"]
    n_v, dv = c["linear_num_value_heads"], c["linear_value_head_dim"]
    dk = c["linear_key_head_dim"]
    conv = (2 * c["linear_num_key_heads"] * dk + n_v * dv) // TP
    ratio, index_dim = c["indexer_compress_ratio"], c["indexer_head_dim"]
    groups = [
        dict(name="QSA main K/V", layers=qsa, law="global",
             bytes_per_position=2 * c["head_dim"] * BF16),  # one local KV head
        dict(name="QSA index", layers=qsa, law="complete_groups", ratio=ratio,
             bytes_per_position=index_dim * BF16),
        # vLLM strips MRoPE in language-model-only mode. The ring stores keys.
        dict(name="QSA raw index ring", layers=qsa, law="constant",
             state_bytes=ratio * index_dim * BF16),
        dict(name="GDN recurrent matrix", layers=layers - qsa, law="constant",
             state_bytes=n_v // TP * dv * dk * 4),  # FP32 temporal state
        dict(name="GDN convolution", layers=layers - qsa, law="constant",
             state_bytes=conv * (c["linear_conv_kernel_dim"] - 1) * BF16),
        dict(name="PLE convolution", layers=len(c["ple_layer_ids"]), law="constant",
             state_bytes=c["hidden_size"] * c["hc_count"] * (c["ple_conv_kernel_size"] - 1)
             * c["ngram_size"] * BF16),
    ]
    result = kv_cache_bytes([dict(group, source=SOURCE) for group in groups], context)
    return {**{g["name"]: int(g["bytes"]) for g in result["groups"]},
            "total": int(result["total_bytes"])}


def phase_reference(facts, weights, phase, positions, distinct_experts):
    """Count useful work for the supplied query positions (1-based visible lengths)."""
    c, hardware = facts["text_config"], facts["hardware"]
    tokens = len(positions)
    ops = []

    def op(name, flops=0, hbm=0, tx=0):
        ops.append({"name": name, "source": SOURCE,
                    "demand": {"compute.bf16": flops, "memory.hbm": hbm, "link.nvlink_tx": tx}})

    for name in ("gdn", "qsa", "residual", "ple", "router", "shared", "routed", "logits"):
        elements = weights[name] // BF16
        active = unique = elements
        if name == "routed":
            per_expert = elements // c["num_experts"]
            active = per_expert * c["num_experts_per_tok"]
            unique = per_expert * distinct_experts
        rows = 1 if name == "logits" else tokens
        op(name + " matrices", 2 * active * rows, BF16 * unique)

    layers = c["num_hidden_layers"]
    qsa = layers // c["full_attention_interval"]
    ratio, budget = c["indexer_compress_ratio"], c["indexer_budget"]
    selected = sum(min(s // ratio * ratio, budget) + s % ratio for s in positions)
    kv_width = 2 * c["head_dim"] * BF16
    # QK and AV over selected token rows. Prefill historical KV rereads depend
    # on tiling. Decode streams the selected local KV rows once in this scenario.
    traffic = tokens * kv_width
    if phase == "decode":
        traffic += selected * kv_width
    op("QSA core", qsa * 4 * (c["num_attention_heads"] // TP) * c["head_dim"] * selected,
       qsa * traffic)

    # An ideal BF16 index score is one dot per query head and complete key
    # group. Count a single pass over compressed keys for the decode query.
    complete_groups = sum(s // ratio for s in positions)
    index_dim = c["indexer_head_dim"]
    op("QSA index scores", qsa * 2 * c["indexer_n_heads"] * index_dim * complete_groups,
       qsa * complete_groups * index_dim * BF16 if phase == "decode" else 0)

    # One final FP32 state write after prefill, or one read and write at decode.
    # The chunked prefill and recurrent kernel's internal traffic is unresolved.
    recurrent_bytes = ((layers - qsa) * (c["linear_num_value_heads"] // TP)
                       * c["linear_key_head_dim"] * c["linear_value_head_dim"] * 4)
    op("GDN recurrent state", hbm=recurrent_bytes * (2 if phase == "decode" else 1))

    # Two decoder hidden-state reductions per layer; ring send volume per rank.
    payload = tokens * c["hidden_size"] * BF16
    op("decoder TP reductions", tx=2 * layers * (2 * (TP - 1) * payload // TP))
    result = phase_floors({
        "phase": phase, "model_id": facts["model"], "hardware_id": hardware["hardware_id"],
        "layout": "TP4/ETP4, EP1, PP1, CP1, DP1", "tokens_per_step": tokens, "ops": ops,
        "assumptions": ["One sequence, unquantized weights, BF16 activations, main KV and index.",
                        "One HBM stream per distinct matrix per forward, ring, zero startup."],
    }, hardware)
    if result["analysis_status"] != "COMPUTED":
        raise ValueError(result["unknowns"])
    times = {key: value / hardware["rates"][key]["value"] for key, value in
             result["actual_resource_totals"].items()}
    time = result["datasheet_resource_time_s"]
    return {"visible_tokens": positions[-1], "distinct_experts_per_layer": distinct_experts,
            "demand_per_rank": result["actual_resource_totals"], "seconds_by_resource": times,
            "resource_max_s": time, "binding": result["datasheet_binding_resources"],
            "tokens_per_s_at_resource_max": tokens / time,
            "serial_group_s": result["serial_estimate_s"]}


def analyze(facts, prompt, output):
    c = facts["text_config"]
    if min(prompt, output) < 1 or prompt + output - 1 > c["max_position_embeddings"]:
        raise ValueError("Use positive lengths within the model context")
    ledger = text_weights(c)
    checkpoint = facts["checkpoint"]
    if (schema_digest(ledger.headers) != checkpoint["text_schema_sha256"]
            or len(ledger.headers) != checkpoint["text_tensors"]):
        raise ValueError("Derived text inventory differs from the pinned safetensors headers")

    top_k = c["num_experts_per_tok"]
    prefill = [phase_reference(facts, ledger.rank_bytes, "prefill", range(1, prompt + 1), unique)
               for unique in sorted({top_k, min(c["num_experts"], top_k * prompt)})]
    # Prefill emits the first output token. Each remaining token needs one forward.
    first_decode = last_decode = None
    decode_sum = 0.0
    for visible in range(prompt + 1, prompt + output):
        last_decode = phase_reference(facts, ledger.rank_bytes, "decode", [visible], top_k)
        if first_decode is None:
            first_decode = last_decode
        decode_sum += last_decode["resource_max_s"]
    decode_steps = output - 1
    weight_bytes = sum(ledger.rank_bytes.values())
    peak_cache = cache_payload(c, prompt + output - 1)
    nominal_capacity = facts["nominal_hbm_bytes_per_gpu"]
    if weight_bytes + peak_cache["total"] > nominal_capacity:
        raise ValueError("The logical weight and cache payload alone exceeds nominal HBM capacity")
    return {
        "basis": "datasheet, selected work and explicit traffic scenario",
        "whole_model": {"analysis_status": "INSUFFICIENT_EVIDENCE",
                        "qualified_bound_s": None, "measured_latency_s": None,
                        "unknowns": ["actual H200 clocks and fabric", "kernel dispatch and padding",
                                     "HBM reuse, intermediates, activation traffic and GDN math",
                                     "allocated memory, collective startup and scheduling"]},
        "model": facts["model"], "revision": facts["revision"], "engine": facts["engine"],
        "hardware": facts["hardware"]["hardware_id"], "tp": TP, "etp": TP, "ep": 1,
        "prompt_tokens": prompt, "output_tokens": output, "batch": 1, "mtp": False,
        "text_tensor_count": len(ledger.headers), "text_checkpoint_bytes": ledger.stored_bytes,
        "nominal_hbm_bytes_per_gpu": nominal_capacity, "allocated_fit": "unverified",
        "rank_logical_weight_bytes": weight_bytes,
        "rank_weight_bytes_by_family": dict(ledger.rank_bytes),
        "rank_cache_payload_bytes_after_prefill": cache_payload(c, prompt),
        "rank_cache_payload_bytes_last_forward": peak_cache,
        "prefill": prefill, "decode_steps": decode_steps,
        "first_decode": first_decode, "last_decode": last_decode,
        "mean_decode_resource_ms": 1000 * decode_sum / decode_steps if decode_steps else None,
        "decode_tokens_per_s_at_resource_max": decode_steps / decode_sum if decode_steps else None,
        "request_resource_s": [row["resource_max_s"] + decode_sum for row in prefill],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-tokens", type=int, default=8192)
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--verify-hub-headers", action="store_true",
                        help="Re-read the pinned public config, index and all shard headers")
    args = parser.parse_args()
    facts = json.loads(FACTS.read_bytes())
    result = analyze(facts, args.prompt_tokens, args.output_tokens)
    if args.verify_hub_headers:
        result["source_audit"] = audit_headers(facts, text_weights(facts["text_config"]).headers)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
