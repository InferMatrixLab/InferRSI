# Serving-state contracts

This is a bounded static read of DwarfStar at
`ee7e8405232c8971000cc7ba2b945b00bf6d20d3`. The numbered source readset below
identifies evidence, not files the reader must reopen to use this procedure.
No accelerator, real-model session or service-performance result is implied.

## API and lifecycle surface

The installed `ds4-server` binary selects its backend through its build; `-m`
selects the loaded GGUF. A Flash/PRO compatibility alias in an API request does
not load a different model. The default listener is loopback port 8000.

| Request | Purpose |
| --- | --- |
| `GET /v1/models` | Identify the loaded model surface |
| `POST /v1/chat/completions` | OpenAI-style chat |
| `POST /v1/responses` | Responses-style requests and continuations |
| `POST /v1/completions` | Text completions |
| `POST /v1/messages` | Anthropic-style messages |

For an already-running authorized service, this is a small text-only Chat body
that can be constructed offline before any network request:

```json
{
  "model": "deepseek-v4-flash",
  "messages": [{"role": "user", "content": "Explain prefix reuse briefly."}],
  "stream": false,
  "temperature": 0,
  "max_tokens": 32
}
```

Chat, Responses and Anthropic interfaces support SSE and tools. Reasoning is
separate from visible text in each interface's own shape. At this source
snapshot DeepSeek thinking is normally enabled; `reasoning_effort: "max"`
selects Think Max only if context permits, whereas `"xhigh"` means normal
thinking. Keep the effective setting fixed when investigating a cache change.

Image requests require a matching loaded vision encoder. OpenAI Chat/Responses
accept inline PNG/JPEG data URIs; Anthropic accepts base64 image sources.
Remote URLs and server-side paths are rejected. The documented limits are 16
images and a 64 MiB HTTP body. Preserve image order. These are this snapshot's
interface constraints, not universal acceptance or security certification.

## Three distinct cache identities

| Layer | Match and ownership | Consequence of mismatch |
| --- | --- | --- |
| Live slot | A valid checkpoint's exact tokens plus model-specific backend state; image-conditioned states also need historical image identities | Sync resets/rebuilds rather than extending an invalid history |
| Disk lookup | Rendered-byte-prefix hash plus model, saved-context and optional same-quant checks | A miss is legitimate even when a human sees equivalent text |
| Disk payload | Exact saved tokens and versioned/model-specific graph state; optional tool/visible-text trailers | Load validates the payload; a byte-key hit alone cannot establish restore success |

The disk search rejects a different model ID, an entry whose saved context is
larger than the current context, entries below its minimum token policy, and
different quantization when `--kv-cache-reject-different-quant` is set. Payload
load additionally checks version, layout, row counts and capacity as applicable.
Do not generalize these implementation checks into compatibility with arbitrary
checkpoints that happen to share a model ID or bit width.

After a successful byte-prefix hit, the effective prompt starts with the exact
saved token history and tokenizes only the rendered-text suffix. Retokenizing
the entire visible prefix can produce a different BPE spelling and detach the
new token vector from the restored backend state. A copied cache filename or
matching visible text is not proof of token equality or valid graph state.
The suffix uses the rendered-chat tokenizer, not plain-text BPE, because it may
start with role or thinking markers. Preserve that distinction in adaptations.

With `--kv-disk-dir <CACHE_DIR> --kv-disk-space-mb <BUDGET_MB>`, disk cache is an
additional persistence layer; it does not replace each slot's live state.
Cache contents include prompts and model state. Treat the directory as private,
retain a redacted failure record, and stop the server before any separately
authorized clearing. Do not delete a cache just to hide a failed load.

## Vision gate: identity before reuse

1. A routing probe first rejects invalid checkpoints and historical image
   fingerprint/embedding-row-count mismatches. This fingerprint-prefix probe
   deliberately ignores positions and can admit appended request images.
2. That is only a probe. The materialized live continuation must still satisfy
   text/token history and span constraints. Rebased positions require an
   independently matched continuation, such as the live tool-call binding;
   image identity alone does not authenticate the text history.
3. The strict session predicate checks historical token positions, row counts
   and fingerprints. New images start at or beyond the retained token frontier.
   Reordering, dropping or changing a historical image is not prefix extension.
4. Vision-conditioned live state must not be written into the text-keyed disk
   cache. After a restart, do not promise restoration of image-conditioned KV
   merely because the visible transcript and cache directory remain.

A minimal falsifier is two histories with identical visible text but one changed
historical image fingerprint: a live reuse route must not accept the old state.
The source's model-free identity tests express that predicate; only a real
backend/model check can establish correct multimodal output and restoration.

## Exact tool replay and backend-frontier repair

For DeepSeek, generated DSML tool blocks are retained behind tool-call IDs.
The replay map is bounded by `--tool-memory-max-ids`; a retained disk trailer may
restore mappings across restart. Mapping restore is model-scoped. All calls
within one message must resolve to the same retained block to attach its exact
sampled text. IDs missing from the map, or IDs resolving to mixed blocks, use
canonical rendering rather than fabricated exact replay.

`--disable-exact-dsml-tool-replay` is a diagnostic comparison, not a remedy for
lost model state. The live tool binding is not durable remote conversation
storage. A tool-result-only request with no replayable prefix may fail; keep
complete history when the client/server contract requires reconstructing it.

Canonicalization must not rewrite only the token vector behind the live end.
DeepSeek's state includes raw/compressed KV, indexer rows and compressor
frontiers; safe replacement needs the whole corresponding frontier. The
rewrite API reports rebuild-needed without changing the session when that
frontier is unavailable. The server can then use a valid older disk prefix or
full replay. It avoids text-only canonicalization for image requests to preserve
the correctly image-conditioned sampled frontier.

General rewind is also model-specific. A Qwen verify snapshot may restore
certain recent frontiers; otherwise its recurrent state resets for replay.
Absent a valid saved frontier, truncating DeepSeek tokens invalidates the
checkpoint. A stale `checkpoint_valid` bit or token-count-only repair is unsafe.

## Batching, fairness and distributed restoration

`--batched-session <SLOTS>` preallocates independent states and queues excess
requests; active requests are not evicted. Supported paths share prefill
workspace, not the slot's recurrent state, KV or request history. Context and
slot count must be budgeted together. Long prefills yield to active decoders in
bounded intervals; `--mixed-prefill-quantum` is the diagnostic control.

Execution is model/backend specific: ordered fallback runs rows separately.
In this snapshot single-GPU CUDA, Metal GLM 5.2, and Metal SSD-streamed V4.1
are documented examples of ordered fallback. Native grouped paths exist only
for supported layouts. Image-conditioned V4.1 requests use ordered fallback.
Do not label every scheduled slot a native GPU batch.

Most session-batched paths use ordinary target decoding. The documented
exception is Qwen3.8 on Metal with `--mtp`; nonzero-temperature exact-sampling
requests use ordinary batches there. Do not stack speculative and multi-slot
claims without checking the actual selected path.

TP payload restore retains the exact saved tokens but rebuilds both ranks
through mirrored sync; a local file cannot directly restore a remote GPU.
Pipeline restore follows its own layer-state route. Physical peers, protocol
failure handling and model correctness still need actual target execution.

## Bounded source readset

- `docs/SERVER.md`, lines 5–149: endpoints, settings, slots, images, persistence
  and tool history.
- `ds4.h`, lines 430–485: sync/rewrite return contracts and vision predicates.
- `ds4.c`, lines 61171–61280: per-session state ownership;
  64250–64367: payload checks and TP token rebuild;
  76345–76460: prefix and image identity predicates;
  76537–76721: sync/vision validation and failure handling;
  76733–76845: selected Qwen/CPU prefix and interruption behavior;
  77826–77894: rewrite/frontier contract and checked return behavior;
  87383–87449: rewind validity.
- `ds4_kvstore.h`, lines 11–98, and `ds4_kvstore.c`, lines 673–704 and 1196–1325:
  byte-key, compatibility, payload and exact-token-plus-suffix construction.
- `ds4_server.c`, lines 10440–10472, 10653–10777, 11094–11133,
  11260–11285, 11430–11455, 11593–11670 and 12992–13075:
  live bindings, exact replay, disk map restore, vision save guards and
  route/materialization/canonicalization boundaries.
- `tests/test_session_state.c`, lines 1–160: synthetic image identity and
  invalidation assertions, inspected only; not a native GPU execution result.
