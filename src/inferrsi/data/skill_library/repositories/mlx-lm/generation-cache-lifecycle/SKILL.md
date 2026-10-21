---
name: generation-cache-lifecycle
description: Trace MLX-LM prefill, generation batching, prompt-cache reuse and cooperative stopping when request state, cache rows or retained prefixes become inconsistent.
---

# Trace MLX-LM generation and cache lifecycle

Use for mixed-length batches, prefix-cache reuse, unexpected retained state, stop/removal behavior or mismatches between single generation and the server. Do not use for MLX platform discovery, generic GPU memory allocation, model training, or unverified serving-performance claims.

This is a source-derived candidate with runtime validation not_run. Read the [pinned source map](references/source-map.md), [generation/batch path](references/generation-batch.md) and [cache/stop contract](references/cache-stop.md). MLX owns array execution; MLX-LM owns request identity, cache policy, batching and token termination. The two repositories have independent source pins and unverified combined compatibility.

## Inputs

Record MLX-LM and MLX revisions/builds, backend/device, exact model/tokenizer/adapter/draft-model bytes or revisions, entry point, tokenized prompts, cache classes, batch/prefill limits, per-request samplers/processors/stop sequences, seed and KV quantization settings. For a failure, keep a bounded sequence of request IDs, stage changes, token/cache lengths, completion reason and the next request's result.

## Procedure

1. **Resolve the entry path.** Distinguish `generate_step`, `stream_generate`, `BatchGenerator` and server dispatch. Server batching additionally requires the model to be batchable, no request seed, and no KV quantization; the library class does not remove those gates (G1/G5).
2. **Follow prefill and decode.** Cache creation may defer to a model's `make_cache`; otherwise the factory chooses ordinary or rotating caches. Prefill chunks explicitly evaluate cache state. Decode schedules the next token asynchronously before yielding the current token; preserve the stream and read boundary when interpreting time or cache progress (G1/C1).
3. **Keep rows aligned.** Track UID through pending, prompt-processing and generation stages. On completion/removal, filter cache rows, tokens, samplers, processors, lengths, stop matchers and pending outputs using the same row selection. Include `_currently_processing` when removing prompt-stage requests (G2/G3).
4. **Check reusable-prefix identity.** Trace the server's model key and token prefix into `LRUPromptCache`. Reuse returns copies; trimming depends on the cache type. Record exact tokenization and model/adapter/draft identity rather than treating a text string or cache-file path as a sufficient key (C2/C3).
5. **Trace stop through cleanup.** Handler cleanup sets a context flag. The batch loop observes it and removes the UID; this is cooperative application-level removal, not immediate cancellation of already queued MLX work. Keep normal EOS/length, text-stop, disconnect and shutdown paths separate. Single-request and distributed stop behavior differ (G4/G5).
6. **Validate the relevant boundary.** Use the [validation plan](references/validation.md): mixed lengths, prompt-stage removal, generation-stage removal, survivor completion, prefix reuse/copy isolation and the next request. Do not silently fetch model weights or launch a server to satisfy a source-derived claim.

## Output and stop conditions

Return an entry-path decision, UID/stage/cache-row table, prefix key and cache-class assumptions, terminal/cleanup path, and exact passed/failed/not-run evidence. Stop at the first unsupported contract or missing required fixture/backend and retain a targeted verification plan. Do not infer a paged allocator, radix sharing or instantaneous prefill interruption from the existence of batching or a stop flag.
