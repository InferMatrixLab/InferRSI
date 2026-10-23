---
name: kv-tier-management
description: 'Manage runtime KV cache tiers (GPU → CPU RAM → local disk) for LLM serving: decide when KV is stored, retained, prefetched, or evicted; size the concurrency-versus-RAM-pressure trade-off with an explicit in-flight admission dial; order RAM-release levers; and measure with token-level L1/L2 hit rates and prefetch-pressure counters. Use when configuring KV offload for a serving stack. Covers runtime KV offload only — model startup/loading, checkpoint save/restore, and block-device profiling are separate concerns (see weight-loading-optimization).

  '
---

# KV Cache Tier Management

Status: candidate. Source-grounded from LMCache/LMCache multiprocess (MP) mode
@ c3b875a (Apache-2.0): `docs/source/mp/` (l2_storage, configuration,
multi_l1, lazy_offload, metrics), `lmcache/v1/distributed/` (store/prefetch/
eviction controllers, l2_adapters). MP-mode semantics only — single-process
`LMCACHE_*` knobs differ and must not be mixed. GDS/DAX/NVMe-passthrough
paths are CUDA/ROCm/NIXL-bound; policies transfer, hardware paths do not
imply Ascend support.

## SearchSpace mapping

RAM / Host + SSD / Storage rows → Configure + Optimize cells.

Second-level targets: runtime KV offload (distinct from model
startup/loading), CPU RAM tier sizing, local-disk KV tier, prefetch
admission.

Related skills: `weight-loading-optimization` (startup/load path — different
lifecycle stage), `host-memory-management` (pinned memory / NUMA allocation
mechanics), `os-process-placement` (process placement),
`storage-io-measurement` (per-device/per-process I/O attribution for L2
adapter traffic; two-layer evidence gate for any storage-side claim).

---

## Tier hierarchy (as implemented)

| Tier | What it is | Options |
|---|---|---|
| L0 | GPU KV cache of the inference engine | engine-owned |
| L1 (fast) | CPU pinned DRAM by default | or Device-DAX slab; or NVMe slab via GPUDirect Storage (disables the DRAM tier) |
| L2 (persistent) | Pluggable adapter cascade, ordered by configuration | local: nixl_store(_dynamic), fs, raw_block, dax; remote (s3, redis, mooncake, 3fs) are also just L2 adapters |

Data flow: L0 → L1 (two-phase reserve/finish writes) → L2 (async
replication). L1 is authoritative; L2 lag is tolerated. On lookup miss:
L2 → L1 staging (invisible to readers until landed) → L0.

## Store policies — what L1 keeps after replication

| Policy | Behavior | Use when |
|---|---|---|
| `default` | L1 keeps the key after a successful L2 store | DRAM reuse expected |
| `skip_l1` (buffer-only) | deletes every stored key from L1 on success — L1 becomes a pure write buffer | L1 RAM scarce, reuse comes from L2; pair with `--eviction-policy noop` to drop LRU tracking overhead |

Store failures are best-effort with no retry: the key stays in L1 and only a
warning is logged. There is **no write-through mode** (synchronous L2 commit)
in this revision. Deletion from L1 runs only on successful store.

## Retention duality for prefetched keys

| Policy | After the L1→GPU retrieve | Use when |
|---|---|---|
| `default` | prefetched keys are temporary — deleted after use | one-shot lookups |
| `retain` | loaded keys stay in L1 permanently | shared system-prompt chunks reused across requests |

All-or-none per policy (no per-key retention knob); retained keys raise L1
usage and accelerate L1 eviction.

## Prefetch: three triggers and the pressure dial

1. **On lookup miss** (default): per scheduled request; atomic
   existence-check + L2 lock survives the lookup→load window; only the
   contiguous prefix hit is loaded by default (`full` fetch is rejected for
   sliding-window key groups).
2. **Eager** (`lmcache.mp.eager_prefetch`): submit when the request enters
   the engine's waiting queue — L2→L1 staging overlaps scheduler queue wait.
3. **Warm** (HTTP `POST /cache/prefetches`): caller-supplied keys loaded
   resident-retained-unpinned; nothing pinned means an unpolled job holds no
   L1 hostage. No prefix truncation — over-requesting inflates pressure.

**The concurrency-vs-RAM dial**: `--l2-prefetch-max-in-flight` (default 8)
is the only admission knob — higher increases L2→L1 throughput **and**
in-flight L1 bytes. It is count-based; a byte-aware dynamic admission
controller is an explicit upstream TODO. Pressure is metered directly:
`l1_alloc_failure{during=l2_prefetch}` and `l2_prefetch_failure{reason=l1_oom}`.

## Eviction

**L1**: background thread, 1 s loop; at usage ≥ trigger watermark (0.8
default) evict per policy down by eviction ratio (0.2 default); locked keys
skipped and retried next cycle; keys tracked **from reservation** (abandoned
write reservations remain evictable); recency only from explicit access
events. Policies: LRU / ARC / IsolatedLRU / noop (noop legitimate only in
buffer-only mode).

Caveat: docs describe the ratio as a *memory* fraction but LRU/ARC compute a
*key-count* fraction (`target_count = len(order) × ratio`); the two coincide
only for uniform chunk sizes. IsolatedLRU has quota/allowlist semantics per
`cache_salt` — an unregistered salt gets limit 0 and is wiped at the next
cycle.

**L2**: opt-in per adapter (eviction sub-config); each adapter gets its own
policy/watermarks — same-type adapters may differ. Destination is DISCARD
only (no L2→lower demotion in this revision). `fs` has **no eviction at all**
— an unbounded directory unless externally managed. `s3`/`hfbucket` need an
explicit capacity or eviction stays disabled.

## When to store at the source (lazy offload)

Connector-side buffering drained by policy, not at compute time
(vLLM + prefix caching required; disabled by default):

- `EVICTION_AWARE` (default): release a store when the GPU blocks holding
  its data approach the engine's eviction head — KV about to be lost is
  offloaded; KV staying resident is not. Horizon `_horizon_steps` 2.5:
  larger stores earlier (fewer losses) but may offload hot content and
  increase lower-tier pressure.
- `FIFO`: drain on a finished-request count.
- Block-hash re-verification before offload: reused blocks are skipped, so
  stale KV is never cached (miss → recompute; correctness unaffected).

## Multi-L1 composition (RAM-pressure valve)

Repeatable L1 managers (DRAM / DAX / GDS), each with own capacity +
eviction + store controller; writes try managers in argument order and only
`OUT_OF_MEMORY` moves to the next; per-key owner fixed at prefetch; adapter
`affinity_tag` binds each L2 adapter's store+reload to one host-backed L1.
Levers: lazy allocation (init 20 GiB, grow on demand), hugepages, mlock
(ROCm-only), per-manager TTLs. Limitation: allocation stays atomic per
batch — a batch can fail even when combined free space would suffice; no
cross-L1 dedup or migration.

## Local L2 adapter selection

| Adapter | Capacity/eviction | Persistence | Notes |
|---|---|---|---|
| `fs` (aiofiles) | none — unbounded | one raw file per key, atomic rename | optional read-ahead, O_DIRECT |
| `nixl_store` | slot pool; eviction frees slots | no | primary production path |
| `nixl_store_dynamic` | byte-based usage + capacity gate | persist/recover: empty index on start, miss→disk fallthrough, lazy rebuild | 2-level hash tree; layout switch orphans old files |
| `raw_block` (Rust) | fixed slots on raw device/file | on-device metadata checkpoint | io_uring / NVMe passthrough (`/dev/ng*`); zero-copy fixed buffers cost RLIMIT_MEMLOCK (≥20 GiB); NVMe FDP placement by salt |

Per-adapter serde (e.g. fp8) halves byte volume for disk/remote adapters;
unsupported under a GDS L1 (no L1 memory buffer exposed).

## What gets stored at all

Prompt tokens only by default — replayed fixed prompts do not create new
entries from sampled output; `save_decode_cache` opts in generated tokens
(for resumable/streaming) and is a **different setting** from the
single-process connector's same-named flag. Key identity includes
`cache_salt` (tenancy/bucketing) and layout decorations.

## Concurrency model (why MP mode exists)

One cache-server process per node serving multiple engine pods: no GIL
contention or Python overhead on the inference path; L1 RAM shared across
pods, scaled independently of engine processes. Blocking RPCs run on a CPU
pool plus a client-affinity GPU pool (same engine instance → same thread,
eliminating GPU transfer lock contention). Store, prefetch, eviction are
each single background threads on eventfd poll loops. Per-object read/write
TTL locks (600 s write / 300 s read) prevent deadlocks from crashed clients.

## RAM-release levers, ranked

1. Buffer-only: `skip_l1` + `noop` eviction (lowest resident set)
2. Temporary prefetch retention (default policy)
3. Lower watermark / ratio tuning
4. Multi-L1 overflow to DAX/GDS for capacity without more DRAM
5. Per-adapter serde (fp8) to halve L2 bytes
6. Lazy L1 allocation to defer RAM commitment

## Measurement

- Token-level hit rate with L1/L2 split (`lookup_hit_l1` + `lookup_hit_l2` =
  `lookup_hit`; contiguous prefix only).
- Prefetch pressure: `l1_alloc_failure{during=l2_prefetch}`,
  `l2_prefetch_failure{reason=l1_oom|not_found}`, pending-queue size,
  in-flight gauge.
- Store lag: submitted vs finished store counters.
- Eviction loop ticks with usage/watermark/triggered per cycle.
- Multi-L1: usage bytes and ratios are per `l1_tag` — sum bytes across
  tags, never sum ratios.
- No author-reported performance/hit-rate figures exist in the read docs;
  benchmark tooling exists in-repo but was out of approved scope.

## Known limitations (from source)

- No write-through mode; store failures silently tolerated by design.
- No L2 demotion (DISCARD only); MP move/pin/compress APIs unwritten
  ("coming soon").
- Prefetch admission is count-based (byte-aware is TODO).
- Eviction ratio: doc says memory-fraction, code does key-count.
- Mode mixing: `lmcache.ttl` / `lmcache.tag.*` / `lmcache.skip_save` are
  metadata-only in MP but interpreted differently by the in-process
  connector; single-process `max_local_cpu_size` (5 GB default) is unrelated
  to MP `--l1-size-gb`.
- GDS L1 requires cuFile/hipFile ≥ 7.2/muFile/uGDS and disables the DRAM
  tier; raw_block NVMe passthrough needs `/dev/ng*` char nodes; DAX L2 is
  volatile across restarts (index rebuilt empty).

## Verification checklist (before claiming a KV-tier win)

- [ ] Hit rate reported token-level with L1/L2 split, not object counts
- [ ] Prefetch pressure counters checked (no `l1_oom` storm at the chosen
      in-flight value)
- [ ] Eviction semantics confirmed against actual chunk-size uniformity
- [ ] Store-policy / retention-policy choices recorded with their rationale
- [ ] Mode (MP vs single-process) recorded alongside every knob value
- [ ] Adapter capacity/eviction config recorded (especially `fs` unbounded)
