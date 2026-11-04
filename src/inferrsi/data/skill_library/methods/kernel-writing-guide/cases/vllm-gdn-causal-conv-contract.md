# vLLM GDN causal-convolution contract

Use this reference before qualifying a Gated DeltaNet (GDN) operator for reuse
outside its serving engine. The concrete caller here is vLLM's Qwen3-Next
`linear_attention` layer on its CUDA-facing Python path. The source snapshot is
[vllm-project/vllm @ 537a79f0fc5ba564d2bef43d54915b2f80f9f77d](https://github.com/vllm-project/vllm/tree/537a79f0fc5ba564d2bef43d54915b2f80f9f77d),
tree `d573bc73908ae9cf2e1254710483ae3467d12343`, inspected
2026-10-27. This is a source-derived candidate. Native kernels, model execution,
hardware compatibility, numerical results, performance and agent efficacy have
not been evaluated.

## Establish the caller before choosing an operator

Qwen3NextModel constructs each decoder with its configured `layer_type`.
A `linear_attention` decoder constructs `QwenGatedDeltaNetAttention` with
`gqa_interleaved_layout=True`; its forward calls that layer. A
`full_attention` decoder constructs the separate attention implementation.
Do not extend the GDN contract to every layer of this hybrid model. [A]

The CUDA-facing GDN forward projects hidden states into QKV/Z and B/A, unpacks
the interleaved Qwen3-Next layout, then invokes
`torch.ops.vllm.qwen_gdn_attention_core`. The registered Python custom op resolves
the layer from the forward context and calls `_forward_core`; output projection
remains outside it. The layer imports `causal_conv1d_fn` and
`causal_conv1d_update` from
`vllm.model_executor.layers.mamba.ops.causal_conv1d`. These are in-tree Triton
wrappers, not proof that a standalone package with similar symbol names is
installed or API-compatible. [B, C]

The core reads layer-specific `GDNAttentionMetadata`. Missing metadata enters
prefill warmup and returns; that profiling branch does not demonstrate request
execution. A replacement must preserve the selected model layout, metadata,
state mutation and output contract, not merely its Python function name. [B]

## Resolve phase and effective backend separately

The prefill selector returns both requested and effective backend. It reads
`additional_config["gdn_prefill_backend"]`, defaulting to `auto`. In its CUDA
branch, the source selects FlashInfer for requested `auto`/`flashinfer` when
the platform predicate is SM90, or SM10.x/SM12.x with key-head dimension 128
and CUDA runtime major at least 13. CuteDSL is opt-in and the inspected predicate
also requires SM10.x, dimension 128 and runtime major at least 13.
Other CUDA cases return `triton`; an explicit unsupported FlashInfer/CuteDSL
request emits a fallback warning. These are resolver predicates, not a tested
hardware or installation matrix. [B]

The selected prefill recurrence wraps external `flashinfer.gdn_prefill`, the
in-tree CuteDSL implementation, or vendored FLA as appropriate. The FlashInfer
adapter normalizes Q/K when requested, removes the leading batch dimension,
makes inputs contiguous, converts state/gating to FP32, converts cumulative
lengths to int64, exponentiates the gate, and restores the output batch dimension.
This adapter is not a general API-equivalence proof for those implementations.
Their underlying recurrence kernels are outside this readset. [B]

Prefill selection does not select the ordinary decode convolution. Record the
convolution and recurrence choices as separate columns:

| Metadata condition in the inspected core | Convolution | Recurrence and output handling |
|---|---|---|
| Non-speculative batch with any prefill rows | Transpose token-major QKV to `[channels, total_tokens]`; call in-tree `causal_conv1d_fn` with cumulative lengths, cache-row indices and initial-state mask | Run the selected chunk recurrence for prefill rows; gather/clear initial recurrent state and write final state back |
| Mixed non-speculative decode + prefill | The same varlen forward convolution processes the complete non-speculative portion | Peel the decode-first prefix into recurrent update; rebase prefill cumulative lengths and slice prefill state rows; stitch decode outputs before prefill outputs |
| Decode-only, no speculative mask, packed-recurrent flag enabled | In-tree `causal_conv1d_update` on actual token rows | Vendored FLA packed recurrent decode consumes packed QKV and the same state-row indices |
| Ordinary decode-only without that fast path | In-tree `causal_conv1d_update` | Vendored FLA gating/delta-rule recurrent update, with final state written in place |
| Speculative rows in the standard core | Varlen `causal_conv1d_update` receives the first state column, accepted-token counts, speculative cumulative lengths and maximum query length | Recurrent update receives the speculative state-index matrix and accepted-token counts; token-index maps restore output order |

The packed-recurrent flag defaults to enabled in the inspected environment
definition; the source guard still requires no speculative mask, zero prefills
and at least one decode. The metadata builder classifies a real first one-token
chunk as prefill when its prefill flag and lack of prior state require
initialization. Query length one alone is insufficient. With speculative rows
present, the builder reclassifies non-speculative decode rows into prefill work,
preserving their prior-state mask. [B, D, G]

Do not impose a separate-convolution policy on every backend. This model's
interleaved layout makes the fused CUDA MTP decode eligibility check fail.
The default choice then falls back to Triton; an explicitly requested
`VLLM_GDN_DECODE_KERNEL=cuda` raises on the unsupported configuration.
For other eligible callers, the fused path has additional dtype, shape,
gating, built-op and metadata guards. The XPU SYCL branch is explicitly a fused
whole-layer alternative that replaces convolution and decode as well as
prefill. ROCm/AITER, CPU and XPU implementations are not qualified here. [B, G]

## Preserve state ownership, initialization and progress

The layer's `kv_cache` container holds two different state tensors:
convolution history at index 0 and the GDN recurrent matrix at index 1.
Their shared container name does not make either tensor attention KV. [B, E]

Let `K` and `V` be key/value head dimensions, `Hk` and `Hv` their head
counts, `P` tensor-parallel size and `W` convolution width.
The shape calculator uses per-rank convolution channels
`(2*K*Hk + V*Hv)/P`, history length `W-1+num_spec`, and recurrent state
`[Hv/P, V, K]` per state row. Convolution storage can be SD
`[history, channels]` or DS `[channels, history]`; the core transposes SD
so the kernel sees channels before history. Record actual strides and dtype
when binding a replacement. These formulas describe the source contract and
do not validate an arbitrary checkpoint configuration. [B, E]

| Owner / field | Source-level contract |
|---|---|
| Engine block table → metadata builder | State row IDs come from common attention metadata, optionally aligned state indices. The helper returns the supplied table in `none` mode; aligned mode gathers the current block and speculative successors using sequence length and block size. Physical allocation, release and recycling are outside this readset. |
| Non-speculative state rows | The builder selects column 0 of the resolved table; mixed-batch prefill metadata selects the prefill tail. A batch position is not a permanent state-row ID. |
| `has_initial_state` | For work containing prefills, computed-context length greater than zero permits prior convolution history. First chunks use zero prior history. The core separately clears gathered recurrent state where the prefill prior-state mask is false. |
| Convolution update | The kernel mutates only the selected cache row and shifts/appends history. Its API has no `cache_seqlens` or persistent circular-cursor argument. In speculative mode it derives a read offset `num_accepted_tokens-1` and updates the sliding history window. |
| Packed token positions | `query_start_loc` describes cumulative offsets in this batch, not a persistent cache cursor. Speculative and non-speculative splits rebuild their cumulative lengths and retain token-index maps. |
| Null/padded rows | Metadata stages request-indexed rows and fills padded state IDs with `NULL_BLOCK_ID`; varlen update skips zero-length sequences, and convolution kernels skip null rows. Token padding and request counts are different quantities. |
| Recurrent state | Prefill gathers the indicated rows, zeroes rows without valid prior state, then writes returned final state to those rows. Decode updates use state indices and in-place final-state semantics. |

The layer consumes engine-owned row mappings; a standalone worker must establish
its own allocation, request-to-row mapping, reset and lifetime contract.
Do not import attention sink/window rules or another engine's cache cursor
semantics into these states. [B–F]

## Match the in-tree call schema

`causal_conv1d_fn` accepts `x`, `weight`, `bias`, `conv_states`,
`query_start_loc`, and optional `cache_indices`, `has_initial_state`,
activation, padding/null IDs, metadata and validation flag. Packed input is
`[channels, total_tokens]`; weights are `[channels, W]`. The inspected
caller supplies both state-row indices and the initial-state mask. [C]

`causal_conv1d_update` accepts `x`, `conv_state`, `weight`, optional bias,
activation, `conv_state_indices`, `num_accepted_tokens`,
`query_start_loc`, `max_query_len`, null ID, validation flag and `out`.
It supports `[batch, channels]`, `[batch, channels, tokens]`, or packed
`[total_tokens, channels]` with cumulative lengths. The wrapper converts
input to the convolution-state dtype. An omitted `out` aliases that converted
input; conversion can allocate, so original-input mutation is not unconditional.
The wrapper returns output converted back to the original input dtype. The state
tensor itself is updated in place. The standard caller does not pass `out`.
Return, dtype, stride and aliasing behavior must be checked against the
actual wrapper revision. [C]

## Evidence required for a bound operator

1. Identify the concrete worker/model implementation and immutable revision.
   A model label or checkpoint family alone does not identify an HF caller.
2. Trace that caller's projection/layout, imports, custom-op registration and
   actual phase metadata. Compare its full argument and mutation schema with
   the selected vLLM branch.
3. Record requested and effective backend, feature flags, built-op availability,
   actual state shapes/strides/dtypes, row IDs, prior-state masks, accepted-token
   counts and packed offsets. Package availability alone does not prove dispatch.
4. With separate execution authorization, capture the executing branch/operator
   and validate outputs plus both state tensors against an independent reference.
   Cover first/resumed chunks, mixed phases, reordered rows, padding and accepted
   speculative prefixes where supported.
5. Only after correctness, measure on the same model, inputs, hardware and
   complete execution path. Separate kernel time from service latency/throughput.

The [source-contract cases](vllm-gdn-source-contract.md) define four
representative checks. They are source-grounded prompts and rubrics, not
executed model evaluations. No HF binding, standalone Dao/FlashInfer/FLA
implementation equivalence, target-hardware qualification or gain follows
from this reference.

## Source ledger and attribution

Every link uses the same full source commit above. Only the named paths and
mechanisms are in scope; an imported implementation is not silently included.

| Key | Pinned source | Inspected purpose |
|---|---|---|
| A | [qwen3_next.py, 472–519](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/models/qwen3_next.py#L472-L519), [558–585](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/models/qwen3_next.py#L558-L585), [633–736](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/models/qwen3_next.py#L633-L736) | Concrete model/layer construction, interleaved layout and forward chain |
| B | [qwen_gdn_linear_attn.py](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py#L148-L463): imports 37–87, resolver/adapter 148–463, constructor/guards 544–800, forward 1134–1209, core 1556–1907, packed decode 1981–2031, fused guards 2147–2162 and 2198–2240, registration 2244–2288 | Caller, effective selection, separate conv/recurrence, state writes and adjacent fused-path exclusions |
| C | [causal_conv1d.py, 1–155](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/ops/causal_conv1d.py#L1-L155), [383–519](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/ops/causal_conv1d.py#L383-L519), [638–823](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/ops/causal_conv1d.py#L638-L823), [955–1128](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/ops/causal_conv1d.py#L955-L1128) | In-tree wrapper schema, row selection, zero history, accepted-token offset, writes and aliasing |
| D | [gdn_attn.py, 320–682](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/v1/attention/backends/gdn_attn.py#L320-L682) | Phase classification, mixed/spec splits, offsets, masks and padded metadata |
| E | [gdn/base.py](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/gdn/base.py), [mamba_utils.py, 25–50](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/mamba_utils.py#L25-L50), [164–168](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/mamba_utils.py#L164-L168), [272–293](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/mamba_utils.py#L272-L293) | State type, layout and model-derived shapes |
| F | [backends/utils.py, 1283–1357](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/v1/attention/backends/utils.py#L1283-L1357) | Block-table row resolution only; allocator implementation excluded |
| G | [envs.py, 1232–1243](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/envs.py#L1232-L1243) | Packed decode and MTP selector defaults |
| Test intent | [test_gdn_metadata_builder.py, 321–384](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/tests/v1/attention/test_gdn_metadata_builder.py#L321-L384); [test_causal_conv1d.py, 368–440](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/tests/kernels/mamba/test_causal_conv1d.py#L368-L440) | First/resumed one-token chunks, padding and ragged accepted-token updates; inspected test intent, not executed results |
| License | [root LICENSE](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/LICENSE); [conv header](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/model_executor/layers/mamba/ops/causal_conv1d.py#L1-L5); [vendored FLA LICENSE](https://github.com/vllm-project/vllm/blob/537a79f0fc5ba564d2bef43d54915b2f80f9f77d/vllm/third_party/flash_linear_attention/LICENSE) | Root Apache-2.0 and vLLM contributor notices; conv file additionally credits Tri Dao and its adaptation source. Vendored FLA has a separate MIT notice (2023–2025 Songlin Yang, Yu Zhang). No standalone dependency repository or implementation is imported here. |

This addition paraphrases the source contract and retains attribution; it does
not vendor upstream implementation. The owner's older TensorRT-LLM, AKG and
inferred NPU provenance remains subject to its existing historical limits.
