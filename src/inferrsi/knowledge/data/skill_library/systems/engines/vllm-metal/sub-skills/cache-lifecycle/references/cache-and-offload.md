# Cache and offload ownership

This is a bounded source distillation, not an executed native result. The
[configuration guide](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/configuration.md#kv-cache-memory-settings),
[offload guide](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/kv_offloading.md)
and code links below identify the retained source snapshot. Source reports of
particular model sizes or retry-free concurrency are not portable acceptance
bars or new local measurements.

## Separate capacity from residency

The automatic budget starts from `int(metal_limit * fraction) - model_memory -
overhead`. Profiling, TurboQuant prefill workspace and expert-streaming reserves
matter before cache allocation. With automatic sizing, the offload host pool
comes out of that KV budget. With positive `kv_cache_memory_bytes`, the cache
bytes replace automatic sizing; weights, overhead and host offload are
additional physical memory, and raising `gpu_memory_utilization` does not enlarge
this explicit cache. `num_gpu_blocks_override` separately takes precedence over
byte-derived block counts; it is not permission to bypass physical pressure.
See [planner lines 1198–1301](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/cache_policy.py#L1198-L1301).

The paged pool may be allocated without eagerly zero-filling all attention
pages when vLLM's layout permits it; mixed-precision/Mamba zeroing requirements
remain. This avoids committing idle capacity up front, not pinning or reserving
RAM. MLX's wired limit does not pin the torch allocation imported by MLX. Pages
can be compressed/swapped, and faults may cost latency without an allocation
exception. Two processes planning against the same free memory can overclaim.
Grouped sliding-window layers can retire old blocks and improve capacity
without improving generation speed.

The source commit probe transiently touches up to 512 MiB and distinguishes
compression/swap displacement from merely having free memory below a lazy cap.
Only actual displacement above its tolerance causes the arithmetic cap to
shrink: available-before minus reserve and future allocations. Already allocated
weights/profiling buffers must not be subtracted from available-before twice.
The host pool and future workspace must not be forgotten merely because they
have not been committed yet. The source probe and its source-specific constants
are diagnostic policy, not a general campaign memory-admission guarantee. See
[pure cap logic lines 349–380](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/cache_policy.py#L349-L380).

## Offload eligibility is a staged check

| Layer | Supported contract / rejected combinations |
| --- | --- |
| Configuration hook | Native offload backend only; simple-KV-offload mode refused; another connector plus offload size refused; PP/DP and executor other than `uni` refused; pooling/MLA and DFlash/DSpark target/draft groups refused |
| Worker cache registration | Exactly one `FullAttentionSpec` group, not `MLAAttentionSpec`; any `draft_layers.` member refused; non-full/sliding/hybrid groups do not pass |
| Runtime storage | `KVCacheStorage` plus `MetalTieringOffloadingSpec`; a worker already bound to another storage cannot be reused |
| Secondary tier | `fs` routes to the Metal filesystem tier; arbitrary/`obj` tiers are not supported on macOS through this path |

Sources: [config hook](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/config.py#L82-L231),
[registration guard](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/connector.py#L30-L77),
[tier spec](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/spec.py#L31-L101).
No single config object or generic CPU import proves all of these layers passed.
The offload documentation also excludes speech-to-text. This route is not MoE
weight streaming; do not confuse an expert-weight cache with KV history.

The hook rewrites the connector/spec to Metal, forces `kv_role=kv_both` so
scheduler deferred-block-free protection remains enabled, then clears the
translated offload-size flag to disarm upstream translation. This does not
create a new scheduler: scheduler-side behavior is inherited from vLLM and must
be qualified against the matched vLLM revision.

## Automatic pool geometry

For uniform full attention, the default pool is two max-length requests:

`2 * round_up(max_model_len, block_size) * (2 * layers * kv_heads * head_dim * dtype_bytes)`.

The outer two counts requests; the inner two counts K and V. The source uses
dense dtype bytes for this default even when a compressed layout can hold more
blocks. This is not a general compressed-page formula. One aligned chunk is the
floor. The automatic pool is capped at a quarter of the pre-pool KV budget,
unless the chunk floor is larger. With ordinary automatic cache sizing, it also
leaves room for `ceil(max_model_len/block_size) + 1` cache blocks, including the
null block. That request reservation is not applied to original auto-fit length,
block override or explicit-cache-byte paths. A user-set host pool is never
silently capped. Under paging, an automatic pool may shrink again so the cache
and pool share the newly observed room. See
[default formula](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/config.py#L58-L79),
[pool caps/floors](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/cache_policy.py#L1303-L1415).

## Transfer lifetime

The region is anonymous lazy RAM, shared only inside the one process through an
engine-ID registry; it is not `/dev/shm`, an SSD file or an inter-process/shared-
network pool. Scheduler and worker views must have matching chunk geometry and
must alias the same buffer. The worker verifies its NumPy view is zero-copy and
that its carved bytes differ from chunk size only by alignment padding.

`submit_store` and `submit_load` complete transfers synchronously and append a
completion record; `wait` is consequently a no-op. This does not mean every disk
tier job or model operation is synchronous. Stores evaluate gathered pages
before copying them into host chunks. Loads copy host rows then use native
`scatter_rows`, followed by evaluation of cache pages, so the write reaches the
real cache after pending native writes, including stale zeroing. Index-assigning
an MLX page view would not satisfy the same contract. Loads reject duplicate GPU
destinations because native parallel writes would race. IDs, group size,
mid-chunk offset and host chunk coverage are checked before the transfer. See
[worker](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/worker.py#L93-L246)
and [shared region](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/shared_region.py#L1-L155).

## Sleep, wake and persistence

Level-1 sleep discards KV; weights stay in place on unified memory. Level 2 is
unsupported in this source snapshot. Dense/hybrid MLX sleep is supported, but
standalone MLA and speculation other than n-gram are excluded. Wake recreates
cache with empty prefix state. When offloading is configured, vLLM resets its
connector first, emptying the host index before page release. Region views stay
valid but their contents are lost. Page release is best-effort; reuse on wake
must succeed because writes to pages not reclaimed can be dropped. Disk-tier
prefixes can still be restored after wake. Do not equate an empty host index
with deletion of private disk blocks. See
[sleep guide](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/configuration.md#sleep-mode)
and [page lifecycle](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/shared_region.py#L114-L155).

Disk filenames use prefix-content hashes. SHA-256 variants have stable seed;
xxhash variants need a stable process seed for reuse across restarts. The store
is keyed by model name and dtype, not actual weight bytes; replacing a checkpoint
under the same name requires a separate authorized namespace/cleanup decision.
TurboQuant K/V layouts get an additional signature so differing compressed
layouts do not share file paths. This does not authenticate weight identity.

The cap is per process, not a distributed store quota. Oldest stored/restored
files are evicted, but in-flight job files are pinned; a cap is not proof that
instantaneous bytes can never exceed it when all candidates are pinned. Failed
deletes remain indexed for truthful accounting and retry. Partial failed stores
count files actually written, and short-read deletions update accounting and
cached lookup hits. See
[filesystem tier](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/fs_tier.py#L87-L375).

New roots are created private; existing foreign-owned directories are refused,
while an owned but overly permissive existing directory is warned about rather
than silently chmodded. `.noindex` excludes Spotlight, not backups. Prompt
content can be recovered from KV blocks; do not publish, inspect unrelated
contents, or assume hash filenames anonymize the state. Backup exclusion and
deletion are separate mutating actions requiring authority.

## Discriminating native evidence

The retained source test definitions distinguish useful falsifiers:

- [Budget cases](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/tests/test_kv_offload_budget.py#L153-L211)
  separate request-alone shortage from a request that fits only without a host
  chunk; [explicit-byte cases](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/tests/test_kv_offload_budget.py#L604-L661)
  preserve host/workspace accounting and reject silent trimming of explicit KV.
- [Backing allocation and pending-write cases](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/tests/test_kv_offload_worker.py#L114-L171)
  read back through torch as well as MLX so a detached view cannot masquerade as
  restored backing storage; they deliberately leave zeroing unevaluated before
  the load and check that the original bytes survive.
- [Sleep/reuse cases](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/tests/test_kv_offload_tiering.py#L107-L203)
  distinguish best-effort release from fatal reuse failure and actual same-view
  roundtrip after wake. The [index reset case](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/tests/test_kv_offload_tiering.py#L297-L312)
  checks a previously present host key becomes a miss before released pages can
  be read.

These are inspected assertions, not local test successes. They require matched
dependencies and, for native storage/page operations, the actual supported Apple
backend. The bundled helper cannot substitute for them; later native evidence
must report exact test definitions, runtime/build and real executed bytes.
