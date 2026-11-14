# Architecture and memory

Read for scheduling, KV pressure, prefix reuse, chunking, or speculation. Evidence IDs link to [the pinned source map](source-map.md). This reference describes the checked snapshot; it does not promise compatibility at another revision.

## Follow one request

| Boundary | What to inspect | Observation and invariant |
|---|---|---|
| HTTP/Engine → TokenizerManager | `entrypoints/engine.py`, `managers/tokenizer_manager.py` | Request identity, token IDs, sampling, multimodal expansion; keep prompt/tokenizer revision stable. Engine describes the three-process flow. [E01](source-map.md#e01) |
| Scheduler admission | `event_loop_normal`, `event_loop_overlap`, `get_next_batch_to_run`, `schedule_policy.PrefillAdder` | Queue wait versus admitted requests; available token budget and prefill chunks. Overlap processes a prior result around current GPU work, so object lifetime and barriers matter. [E02](source-map.md#e02), [E03](source-map.md#e03) |
| Forward construction | `TpModelWorker.forward_batch_generation` | `ScheduleBatch` becomes `ForwardBatch`, includes HiCache consumer ordering, and enters `ModelRunner.forward`. A scheduling structure is not a GPU tensor layout. [E04](source-map.md#e04) |
| Model/backend | `ModelRunner._forward_raw` | Distinguish graph replay, attention planning, extend/decode/verify/split modes. A backend must support the actual mode and layout. [E05](source-map.md#e05) |
| Result/finish | Scheduler result handling → DetokenizerManager → TokenizerManager | Streaming text and finish reasons; release request locks/slots at the correct completion boundary, including abort/retraction. [E01](source-map.md#e01), [E02](source-map.md#e02) |

For a tail-latency incident, locate time spent in this path before changing batch size. A long queue, a long prefill, and a stalled KV transfer need different interventions. This is a diagnostic procedure, not a claim of the current bottleneck.

## Memory is several layers

The source separates `allocation.py` (batch allocation), `allocator/` (free slots), `pool/` (physical KV/SSM tensors), `hybrid_cache/` (layer-to-pool routing), `pool_host/` (host copies), and `storage/` (L3 bytes). Radix cache decides what to retain; it is not the allocator. Construction uses `kv_cache_configurator.py` and `kv_cache_builder.py`. [E06](source-map.md#e06)

Estimate dense KV bytes as a planning bound: tokens × layers × local KV heads × head dimension × 2(K,V) × element bytes, then account for actual sharding/replication, page padding, metadata, workspaces and graph pools. This derived estimate is not the allocator's sizing formula; MLA, quantized KV, SWA and Mamba need their actual layouts. Read the selected pool and builder before setting a capacity limit.

Plain RadixCache matches the longest page-aligned prefix. `RadixKey.extra_key` creates an additional namespace; equal token IDs with different extra keys do not share. Active lock references move nodes between protected and evictable accounting, and eviction frees physical segments. Preserve page alignment, split-node metadata, lock balance, and namespace identity. [E07](source-map.md#e07), [E08](source-map.md#e08)

UnifiedRadixCache separates a logical tree/core and components from controller I/O. Full, SWA and Mamba components carry separate device/host state and locks. A valid prefix boundary requires every relevant component validator to pass; Mamba state may need copy-on-write and SWA validity depends on its window. The current component/controller source is authoritative when older prose says “HiRadixTree.” [E09](source-map.md#e09)

## HiCache

L1 GPU and L2 host cache belong to an inference instance. Increasing host size does not pool other nodes' RAM. L3 enables cross-instance reuse only if the selected backend, namespace and storage configuration provide shared scope. Local matching finds reusable prefixes, host/storage data must be restored before consumption, and backup/prefetch policy trades transfer work against recomputation. [E09](source-map.md#e09), [E10](source-map.md#e10)

Existing controls include `--enable-hierarchical-cache`, `--hicache-ratio`, `--hicache-size`, `--hicache-host-memory-mode`, `--hicache-write-policy`, and `--hicache-storage-backend`. Explicit host size overrides the ratio. `buffer_only` uses host memory as staging and requires storage. Host capacity is per rank/process topology; inspect actual resolved capacity and cgroup constraints before raising it. [E11](source-map.md#e11)

Check separately: prefix match length, device/host/storage hit, prefetch wait, transfer bytes/time, host capacity, and protected versus evictable space. A higher hit rate can still increase TTFT if transfer or waiting costs exceed saved prefill work. That is an experiment hypothesis to test on the chosen workload.

## Admission, chunking and speculation

| Existing control | Source meaning | Tradeoff to measure |
|---|---|---|
| `--mem-fraction-static` | Weights plus KV static allocation fraction | KV capacity versus activation/workspace/graph headroom |
| `--max-running-requests` | Concurrent admitted request limit | Saturation versus queueing and KV pressure |
| `--chunked-prefill-size` | Maximum tokens in a prefill chunk; `-1` disables chunking | Long-prefill interruption versus additional scheduling/launch work |
| `--max-prefill-tokens` | Prefill batch token bound with the source's context-length rule | Prefill efficiency, workspace use, and decode delay |
| `--schedule-policy` | Policy selected from source choices | Prefix locality, fairness, and queue latency |

These meanings come from declarations, not universal recommended values. Default/resolved values vary with model, backend and topology. The scheduler excludes unfinished chunks from normal prefill-to-running merges. Check final-chunk and abort handling explicitly. [E12](source-map.md#e12), [E03](source-map.md#e03)

Speculation has an algorithm, compatible draft/target state, draft steps/token budget, and a verification path. `--speculative-algorithm`, `--speculative-draft-model-path`, `--speculative-num-steps`, `--speculative-eagle-topk`, and `--speculative-num-draft-tokens` are distinct controls. Algorithm-specific fields and compatibility hooks matter; the names do not imply a generic interchangeable draft. [E13](source-map.md#e13)

Measure accepted tokens per target verification, acceptance distribution, draft work, verify cost, graph coverage and memory, then end-to-end latency/throughput. High acceptance alone does not establish a speedup. Validate baseline equivalence under intended sampling and cache-hit/chunked cases; research changes to acceptance/verification require an explicit correctness argument.

## Recovery matrix

| Symptom | Next discriminating check | Recovery |
|---|---|---|
| OOM at launch/capture | Weights, static KV, graph/workspace peak, topology | Lower the relevant budget, restore supported baseline; retain launch logs |
| OOM/retraction only under load | Concurrent long contexts, protected pages, admission | Reduce admitted work, test cleanup and pressure; do not disable invariant checks |
| Cache hit corrupts output | Namespace/token IDs, partial page, component state, lock lifetime | Compare cold/hit logits; minimize restore/evict sequence before performance tests |
| HiCache has hits but slow TTFT | L2/L3 transfer and prefetch wait versus saved compute | Compare the same trace with cache policy fixed or disabled; preserve backend errors |
| Chunk/speculation regression | Boundary states and verify/reject cleanup | Return to unchunked/non-spec baseline, then re-enable one dimension |

Use [tuning and validation](tuning-and-validation.md) for the actual gates.
