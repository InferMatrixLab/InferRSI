# Source Notes: Ascend Model Adaptation

Evidence origin: Historical model-adapter documentation bundle `.agents/skills/vllm-ascend-model-adapter/references/`.

## Provenance and limits

- Repository: `vllm-project/vllm-ascend`.
- Immutable inspected commit: `bc8115ed7fdc7e500320b5de70742ef049b4c1a2` (resolves the historical prefix `bc8115ed` recorded in `src/inferrsi/data/skill_library/README.md#vllm-ascend-version-and-responsibility-routing` against upstream `vllm-project/vllm-ascend`).
- Documentation sources:
  - `fp8-on-npu-lessons.md`: FP8 paired weight loading, load-time dequantization to BF16, KV replication under Tensor Parallelism when `tp_size > num_key_value_heads`, and layer-reduction smoke testing.
  - `multimodal-ep-aclgraph-lessons.md`: Staged multimodal feature validation order, MoE-only EP/flashcomm1 applicability rules, and startup graph-mode verification.
- Scope: Model adapter onboarding and checkpoint format handling on Ascend NPU. This skill does not cover runtime ACLGraph execution dispatch (see `ascend-aclgraph-capture-replay`), TorchAir compiler configuration (see `ascend-graph-mode`), or lower-level device allocator behavior (see `torchnpu-device-memory-lifecycle`).

## Three-Tier Responsibility (InferRSI Routing Convention)

To organize knowledge boundaries and prevent duplicate definitions across skills, InferRSI adopts the following routing convention:
1. **Tier 1 — vLLM Generic Mechanism (`repositories/vllm/`)**:
   - PagedAttention block abstraction, KV cache indexing, scheduler preemption, worker RPC protocol.
   - Independent of Ascend or NPU specifics.
2. **Tier 2 — vLLM Ascend Plugin Features (`hardware/ascend/` & `hardware/host/`)**:
   - Model adapter checkpoint weight conversion, FP8 load-time dequantization into BF16, TP-aware GQA/MQA KV replication, ACLGraph runtime runner, and native host KV offload descriptor pooling.
3. **Tier 3 — Ascend / CANN / TorchNPU Bottom Constraints (`hardware/ascend/`)**:
   - Lower-level CANN runtime, `aclmdlExecute`, geExecutor, HCCL mesh scratch, TorchNPU caching allocator, and H2D/D2H copy streams.

## Inspected source facts

- **F1 (Onboarding Gate Sequence):** `--load-format dummy` checks operator coverage, imports, and shape signatures without weight loading. Real-weight loading validates tensor mapping, FP8 paired-tensor presence, and sharding. Single-text and multimodal endpoints must pass before capacity testing.
- **F2 (FP8 Load-time Dequantization):** NPU execution kernels typically lack native FP8 operator dispatch. Upstream notes record that FP8 weights must be dequantized to BF16 at load time using paired tensors (`<name>.weight` and `<name>.weight_scale_inv`). Missing scale keys in checkpoints trigger failure; they are not framework errors. The formula `weight_bf16 = weight_fp8.to(torch.bfloat16) * weight_scale_inv` is an operational implementation interpretation for reciprocal scales, not a verbatim upstream equation. Upstream notes do not specify a single universal scale granularity: for block-quantized checkpoints, shape handling and broadcasting/expansion are checkpoint-specific.
- **F3 (KV-Head Replication under TP):** When tensor parallelism size exceeds key-value heads (`tp_size > num_kv_heads`), KV heads must be replicated across ranks sharing them rather than sharded, avoiding dimension mismatches (e.g. 128 vs 64).
- **F4 (Multimodal Staged Feature Checks):** Text completion -> image+text completion -> graph mode logs (`Replaying aclgraph`) -> target context length / batch capacity. MoE-only features (EP, flashcomm1) are marked `N/A` for dense architectures.

## Operational interpretation

The procedure converts F1–F4 into a gated debugging checklist. It distinguishes verbatim source facts (F1–F4) from implementation interpretations (e.g. the specific multiplication formula for reciprocal FP8 scales, or generic scheduler bucketing interactions) and InferRSI routing conventions (the three-tier knowledge boundary). All recommendations remain candidates; no local hardware execution or empirical speedup is claimed.
