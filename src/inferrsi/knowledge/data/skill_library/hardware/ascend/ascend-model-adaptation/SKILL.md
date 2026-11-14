---
name: ascend-model-adaptation
description: 'Patterns for porting LLM/VLM model adapters to Ascend NPU: FP8 checkpoint handling, KV replication with TP, multimodal feature validation order, graph mode startup, and feature-status reporting. Source-grounded from vllm-ascend production experience. Use when adapting a new model checkpoint to run on Ascend via vllm-ascend or a similar framework.

  '
---

# Ascend Model Adaptation

Status: candidate. Source-grounded from vllm-ascend @ bc8115ed,
`.agents/skills/vllm-ascend-model-adapter/references/`. Unverified locally
(no NPU). Verify against your CANN version and checkpoint format.

## Choose the versioned owner

This entry retains the historical model-adapter documentation pin `bc8115ed`. Use it for checkpoint onboarding, FP8 loading, KV-head replication and multimodal validation order. For the separately pinned runtime capture/replay contract, follow [ascend-aclgraph-capture-replay](../ascend-aclgraph-capture-replay/SKILL.md). Its wrapper evidence does not revalidate this entry or establish a compatible installed stack.

The [version and responsibility table](../../../README.md#vllm-ascend-version-and-responsibility-routing) preserves each source scope, existing evidence inventory and original inspection-date boundary.

## Debug order for a new checkpoint

Always follow this sequence. Each step gates the next.

1. Start with `--load-format dummy` — verifies the architecture path without
   real weights. Fast; exposes missing op support, shape errors, and import
   failures before spending time on weight loading.
2. Run with real weights — validates weight mapping and load-time stability.
   Exposes missing scale keys, wrong remap paths, and sharding mismatches that
   dummy runs do not catch.
3. Validate `/v1/models` endpoint, then one text request, then one multimodal
   request (if the model supports VL).

Do not sign off on a checkpoint with dummy-only evidence. Always report both
what dummy validated and what only real weights validated.
Source: `fp8-on-npu-lessons.md` § reporting-discipline.

## FP8 checkpoints on Ascend

FP8 execution kernels are typically not supported on Ascend NPU at the operator
level. The recommended path is to dequantize FP8 weights to BF16 during loading.

Pattern:
- For each quantized weight, look for paired tensors: `<name>.weight` and
  `<name>.weight_scale_inv`.
- Dequantize at load time: `weight = weight_fp8 * weight_scale_inv`.
- Keep strict unpaired scale/weight checks — a missing scale key causes silent
  corruption if not caught.

Common failure: the dummy run succeeds but real shard loading fails with a
missing FP8 scale key. This is a checkpoint issue, not a framework bug.
Source: `fp8-on-npu-lessons.md` § 1-2.

## KV replication with tensor parallelism

When `tp_size > num_key_value_heads` (GQA/MQA models), KV heads must be
replicated across TP ranks. This requires a distinct loading path.

Symptom: shape mismatch such as `128 vs 64` during model loading with TP.

Pattern:
- Detect KV-head replication explicitly: if `tp_size > num_kv_heads`, load each
  KV head into all ranks that share it rather than sharding it.
- Use a local norm/shard loader for replicated KV heads.
- Do not assume uniform divisibility for all head dimensions — check each
  attention weight tensor separately.
Source: `fp8-on-npu-lessons.md` § 4.

## ACLGraph (npugraph_ex) for inference

ACLGraph uses capture-and-replay to reduce host scheduling overhead. It is
beneficial for fixed-shape inference with high-frequency identical kernel calls.

Startup behavior with graph mode enabled:
- Startup latency is much higher than eager mode: compile warmup, graph capture
  rounds, and multimodal encoder profiling all happen at start.
- Do not treat slow startup as failure unless logs show hard errors.
- Expected log confirmation: `Replaying aclgraph` appears during inference.

For stability: prefer `HCCL_OP_EXPANSION_MODE=AIV` with graph mode enabled.
Use `--enforce-eager` only as a temporary isolation fallback during debugging,
not as a default serving configuration.
Source: `fp8-on-npu-lessons.md` § 5, `multimodal-ep-aclgraph-lessons.md` § 3.

## Multimodal feature validation order

For VL models, validate features in this order (each step's failure blocks the
remaining ones):

1. Single text request (`/v1/models` + `/v1/chat/completions`)
2. Single text+image request
3. Graph mode evidence (`Replaying aclgraph` in logs), if graph mode is expected
4. Capacity baseline: target context length + batch size
5. Concurrency expansion if needed

For MoE models only: also validate EP (Expert Parallelism) and flashcomm1.
For non-MoE models, mark EP/flashcomm1 as not applicable (N/A), not as failed.
Source: `multimodal-ep-aclgraph-lessons.md` § 1-2.

## Layer-reduction smoke tests

Reducing `num_hidden_layers` speeds up smoke tests but does not remove the ViT
or multimodal encoder structure. A model with reduced layers still exercises the
attention, feed-forward, and encoding paths.

Require at least one full-layer validation before final sign-off. Reduced-layer
results are valid as a fast gate, not as a production quality result.
Source: `multimodal-ep-aclgraph-lessons.md` § 5.

## Feature-status reporting

Use exactly four categories in reports. Never use ambiguous phrases like
"not tested" or "partially supported":

| Status | Meaning |
|--------|---------|
| ✅ supported and verified | Feature ran and produced correct output on this checkpoint |
| ❌ framework-level unsupported | Framework has no code path for this feature |
| ⚠️ checkpoint missing | Weights/config do not provide the feature even if the framework supports it |
| N/A | Not applicable (e.g., EP/flashcomm1 on a non-MoE model) |

Distinguish "theoretical max" (from model config `max_position_embeddings`) from
"practical max" (largest value that actually starts and serves on the current
hardware and TP/EP configuration). Report both explicitly.
Source: `multimodal-ep-aclgraph-lessons.md` § 4, 6.

## When graph mode is validated and works, document it as the default path

If ACLGraph is validated and expected in production, the runbook should document
it as the default serving path. Eager mode should appear only under
troubleshooting/fallback. Do not leave a validated graph mode as an optional
variant the operator must remember to enable.
Source: `multimodal-ep-aclgraph-lessons.md` § 7.
