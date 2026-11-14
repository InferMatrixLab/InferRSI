# Serving, cache and release workflows

Use for constructing local-only commands and tracing validity/lifetime owners.
This is a distilled procedure; original source scripts are provenance rather
than runtime dependencies of this skill.

## Local-only startup planning

Inspect `lithos-metal serve --help` first. A separately authorized local run can
use the following shape, with existing compatible model assets and writable
derived-cache locations:

```bash
lithos-metal serve --model <MODEL_DIR> --no-draft --local-files-only --pack <PACK_CACHE_DIR>
```

`--no-draft` intentionally selects a target-only control. For existing compatible
DSpark assets, replace it with `--draft <DRAFT_DIR> --draft-pack <DRAFT_PACK_DIR>`;
record target/draft revisions and precision. Do not infer automatic pairing for
an unknown or renamed local copy. `--local-files-only` prevents Hub fetching but
does not validate missing assets or suppress pack writes, native compilation,
allocation or warmup. A missing local path must not be silently interpreted as
permission to download. Add no model-download command to a diagnostic task.

The server default binds loopback; retain that boundary unless exposure is
separately authorized. Chat Completions, Responses, Anthropic Messages and
Ollama adapters share generation, but protocol support is bounded: Responses
is stateless and tools execute in the client. Ordinary concurrent generation
is rejected with 429; Ollama chat requests wait in FIFO order. `/health` is
liveness and may report lifecycle state, while `/v1/models` reports an alias.
Neither endpoint verifies output quality or performance.

## Pack identity and publication

`resolve_checkpoint` checks local config and weight shards or resolves a Hub
snapshot with the requested revision/local-only policy. `checkpoint_identity`
records resolved path, config/index hashes, and shard names/sizes/mtime. It
rejects missing shards and unsafe shard paths. It does **not** hash every weight
byte, so a frozen model-integrity manifest is a separate qualification input.

`ensure_pack` keys automatic storage by cache version, checkpoint identity,
capacity, layout, backend, target/draft role and quantization. Draft-head
ownership also affects the key. A per-key lock coordinates builders; a temporary
directory is validated and atomically renamed only after checking the checkpoint
did not change during packing. Explicit manually selected packs are validated
but may lack full automatic cache identity; do not invent one.

`validate_pack` checks supported manifest version, payload size, sufficient
capacity, quantization/Markov preservation, optional identity equality, expected
slab shapes/formats and tensor ranges. This is structural/config validation,
not a cryptographic hash of the entire packed payload or model output check.

## Exact checkpoint contents and identity

`PrefixCache` copies declared model/drafter entries whose buffers have role
`state`, plus StepState. Position-major target K/V and draft `k_ctx/v_ctx` retain
only live prefix rows; convolution/recurrent entries retain complete checkpoint
slots, including parity encoded by StepState. Worker/barrier flags are excluded
because they are program state rather than sequence history. Intermediate
prefill snapshots contain committed prompt state, not pending draft decisions.

The host tier evicts before copying to bound its declared buffer-byte budget.
It retains at most two newest useful checkpoints, favoring a shared stable
prefix when refreshing continuation. Those implementation counts are not
universal tuning recommendations. Snapshot cost can exceed replay benefit on
short prompts; `min_tokens` and actual copy/replay costs matter.

With a store, a longer strict prefix on disk can be loaded, verified and promoted
over the memory match. Reused evictions can spill; `flush` attempts every host
copy and reports whether all are present after bounded waiting. `clear` only
drops host snapshots, not disk files.

`Session.prefix_identity` includes snapshot format/version/code digest, OS/device,
backend, target/draft manifests and payload size/mtime, module config, layout,
state entries, prefill/numerical choices and caller extras. Serving supplies
recipes and tokenizer/template bytes as extras. Capacity is omitted from the
position-major state shapes to permit compatible capacities; restore still
checks allocations and exact state-buffer names/StepState size. Payload
size/mtime is not payload-byte authentication.

## Disk tier and failure recovery

`PrefixStore` uses one file per entry: magic/header, token IDs, StepState and
named state blobs with aligned offsets and SHA-256. It holds an exclusive owner
lock, validates private directory ownership/permissions and uses a bounded
writer queue. Writes use a temporary file, fsync, atomic replacement and
directory fsync. LRU quota eviction excludes pinned readers/writers. These
implementation measures do not by themselves demonstrate recovery under every
filesystem or power-loss scenario.

Load verifies identity, exact tokens, schema/size/ranges and every blob digest.
Corruption or I/O failure drops the entry and returns a cache miss. Restore
checks all buffers before writes. A disk checkpoint that no longer fits raises
`StalePrefix`, is dropped from both tiers, and generation retries prefill with
a miss or shorter prefix. Do not hand-copy partial state into live buffers.

## Session and idle ownership

`Backend.select_session` keys CPU sessions by greedy-vs-sampling and recipe.
One sampling program handles parameter updates; pipelines are shared on the
same device. Adoption settles prior mapping work, reuses compatible roles/sizes,
preserves only identical weight-file windows, and clears non-KV state. Old KV
rows are invalidated logically and overwritten before use. Only the selected
session keeps GPU buffers, while exact-prefix cache ownership is shared.

Idle lifecycle counts requests from arrival through waiting, generation and
stream completion/cancellation. Load/unload uses the GPU lock and rechecks
pending requests after waiting. A failed load releases partial allocation and
returns `model_load_failed`; arrivals sharing that failed attempt do not each
start another load, while a later request may retry.

Unload releases engines/allocations and attempts bounded prefix flush before
clearing host copies. CPU programs/pipelines/tokenizer and OS pack-file cache can
survive. An unavailable/busy disk tier leaves memory-only operation. A warning
about unfinished prefix persistence is not a completed durable write.

## Proposed checks

Use tiny mock HTTP/state tests for validation/admission/streaming, temporary
prefix files for identity/corruption/locks/quota, and a fake clock/lock for idle
ordering. Then compare actual uncached, memory-hit, disk-hit and post-reload
continuations and persistent state. Distinguish checkpoint copy/read/reset,
prefill, decoder and complete HTTP times; only the full claimed workload can
justify service performance wording.
