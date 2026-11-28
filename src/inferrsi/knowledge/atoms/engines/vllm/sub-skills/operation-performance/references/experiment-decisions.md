# Experiment decisions

## Symptom → hypothesis → bounded comparison

| Observation | First discriminating comparison | Watch and reject when |
|---|---|---|
| High TTFT with queue growth | Fixed traffic; vary admitted/batched work and long-prefill cap; separate queue from prefill time | More throughput worsens tail TTFT, starvation, or HTTP rejection rate |
| Poor ITL while long prompts arrive | Compare chunked-prefill budgets at identical mixed traffic | Smaller chunks lengthen prefill too far or scheduler overhead dominates |
| Repeated preemption | Compare lower active sequence/token limits, then memory budget/context requirements | Recompute and queueing negate capacity gain; preserve genuine maximum context requirement |
| Similar prompts still expensive | Compare cold and explicitly warm prefixes with identical tokenization/cache identity | Hit ratio stays low; output-dominated workload offers little prefill saving |
| Decode appears bandwidth-bound | Compare compatible speculation off/on, small draft-count sweep | Acceptance falls, draft/verify overhead rises, quality diverges or peak-load throughput drops |
| Model does not fit / distributed scaling stalls | Establish smallest valid topology; compare TP/PP then DP/EP according to model and interconnect | Communication/imbalance dominates; topology unsupported or device count miscomputed |
| Tail ITL impacted by prefill | Compare tuned co-located baseline with P/D and explicit transfer cost | Network/serialization/proxy/queueing cancels SLO benefit or failures increase |
| Launch/CPU overhead dominates | Compare selected compilation/graph modes with same backend and warm shapes | Startup, capture memory, recompilation or untested-shape failure exceeds budget |
| Memory-limited weights or KV | Compare compatible weight or KV quantization independently | Quality degradation, scale/layout mismatch, slower kernel or conversion overhead |

These are hypotheses, not universally beneficial settings. Preserve the same request corpus, model revision, tokenizer, generation settings and hardware allocation within a comparison. Do not shorten output lengths or silently lower max context to claim a speedup.

## Memory and cache controls

Current source declares `gpu_memory_utilization=0.92`, not a universal recommended value. It is per instance and is not a global reservation for all processes sharing the device. `kv_cache_memory_bytes`, when explicitly set, supersedes utilization for KV sizing; other allocations still matter. Record profiler/startup capacity and actual peak device memory. More KV capacity can reduce preemption but leave too little space for graphs, activations or other processes. [cache_config](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L102-L155) [cache_bytes](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L255-L272)

Separate weight memory, KV residency, temporary activations, graph buffers and communication buffers. A simple dense-attention estimate is a planning bound, not a capacity guarantee for MLA, sliding-window, hybrid/state-space groups, quantized scales, replication or backend padding. Use the actual per-group KV specification and profiled allocation. Prefix-cache wins depend on token-identical reusable prefixes; measure cold and warm separately. [kv_alloc](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/kv_cache_manager.py#L371-L470) [cache_match](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L74-L100)

## Parallelism and P/D

TP can reduce per-rank model work/memory but adds collectives. PP divides layers but introduces stage balance and pipeline effects. DP scales replicas/request capacity when resources permit. EP is relevant to MoE and adds dispatch/combine communication; expert distribution and routing skew matter. PCP/DCP are separate context axes with explicit constraints. Confirm support in the target model, backend and launcher before multiplying ranks or estimating memory. [parallel](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L139-L163) [ep](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L189-L233) [context_parallel](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L591-L629) [world_size](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L946-L965)

For P/D, hold model/tokenizer/dtype and KV layout compatibility fixed, account for transferred bytes and transfer latency, and test request correlation, cancellation, delayed frees, remote errors and chosen failure policy. The feature is experimental. Read the selected connector's own tests/docs before launching; an ExampleConnector run is not production transport validation. [pd](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/disagg_prefill.md#L1-L33) [kv_transfer](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/kv_transfer.py#L56-L91) [connector_finish](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L371-L408)

## Speculation, compilation, quantization

Speculation is a workload-dependent draft/verification tradeoff. Record accepted tokens per draft or acceptance length, draft time, verification time, end-to-end output rate and quality. Include low-load and saturated regimes. Synthetic acceptance can characterize cost under prescribed acceptance but is excluded from accuracy or real model speedup claims. [spec_docs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/speculative_decoding/README.md#L1-L62) [synthetic](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/speculative.py#L529-L549)

Use actual selected attention/quantization kernels as the experimental unit. Compilation and graphs can reduce host/launch work while changing startup, memory and shape sensitivity. Compare eager only when it answers a diagnostic question; it may disable several mechanisms, so explain confounding. Quantization must use supported model/checkpoint/backend combinations and an explicit numerical/task-quality tolerance. [attention](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/attention/selector.py#L105-L225) [graphs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/compilation.py#L610-L654) [quant_docs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/quantization/README.md#L25-L99)

## Recovery

OOM: identify weight-load, profiling, graph-capture or runtime stage; restore the last working setting and reduce the corresponding pressure. Repeated preemption: lower concurrent admitted work before assuming a larger token batch is better. Low prefix hits: check tokenization/template, adapters, multimodal hashes and salt. Transfer stall: inspect request ID, role, peer readiness, completion/free signals and policy. Unsupported kernel: inspect selector conditions and choose a supported path, retaining the failure rather than masking it. Unexpected output: stop performance comparison and validate the affected semantics first.
