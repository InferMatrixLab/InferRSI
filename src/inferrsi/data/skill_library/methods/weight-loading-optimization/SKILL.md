---
name: weight-loading-optimization
description: 'Optimize the serving-level weight load path from storage to device: judge the load path on four dimensions (source, format, placement, duplication), account startup fixed overhead separately from per-request cost with bytes-and-counts lines and hit-criteria warmup validation, verify sharded weight downloads against the safetensors index, apply device-side weight prefetch only on profiled memory-bound hot spots, and order CPU-tier offload candidates by change surface. Includes source-scoped disk-loading modes, pinned staging, synchronous checkpoint save semantics and fastsafetensors broadcast/scatter/coalesced delivery. Use when startup/loading latency dominates; route DCP asynchronous save performance and distributed recovery validity to their separate skills.

  '
---

# Weight Loading and Startup Fixed-Overhead Optimization

Status: candidate. Source-grounded from MindIE-SD `host-opt` +
`env-install/weights-prep` + `dit-perf-opt/resource-fallback-tiers` @ 8481d39b
(Apache-2.0), awesome-ascend-skills `model-infer-prefetch` +
`diffusers-ascend` memory-optimization @ 75ec89c (license UNKNOWN), and —
for loading modes and high-throughput mechanics — ggml-org/llama.cpp @
3e390af (MIT) and foundation-model-stack/fastsafetensors @ 219e256
(Apache-2.0).

## SearchSpace mapping

SSD / Storage row → Diagnose + Optimize + Verify cells (loading-path level).
Communication / Network row → Configure + Optimize + Verify for §9's
cross-rank collectives only; local staging, cloning and H2D remain storage /
memory work.

Second-level targets: model weight sharding/loading, startup latency,
weight prefetch, CPU-tier offload, loading-mode selection.

Related skills: `host-overhead-profiling` (request-time host overhead — this
skill covers the once-per-process side), `ascend-device-health` (card state
before launch), `os-process-placement` (process placement before measuring),
`kv-tier-management` (runtime KV offload — a different lifecycle concern),
`storage-io-measurement` (device/process-level I/O attribution and fio
methodology — the measurement layer beneath §7's phase timers).

---

## 1. Judge the load path on four dimensions

Before optimizing, locate the problem along these axes (MindIE-SD host-opt):

| Dimension | Options | Question |
|---|---|---|
| Source | network disk / local disk / memory cache | Where do the bytes come from? |
| Format | per-tensor reads vs single large file | Read granularity |
| Placement | host-first then to device vs direct device read | Extra hop or not |
| Duplication | multi-process / multi-instance each loading a copy | Redundant reads |

Optimization levers follow directly: fewer reads, fewer copies, parallelize
what remains, reuse what is already resident. Container/image cold-cache
first-read is a cost line of its own — record it separately.

## 2. Account startup fixed overhead separately

The accounting discipline (MindIE-SD host-overhead-account):

- **Fixed vs per-request split**: loading and warmup happen once per process;
  their denominator is startup wall-clock, never amortized into per-request
  e2e. Delivery/transfer work is per-request and accounted separately.
- **No timing point, no account**: if the profiler cannot see a host-side
  segment, add explicit timing points — an unmeasured segment does not exist
  in the ledger.
- **Every line carries**: start/end measurement points + byte count + access
  count + evidence. Bytes and counts distinguish "volume problem" (too many
  bytes) from "path problem" (too many round trips).
- **Warmup is validated by hit criteria, not total time**: cache-entry count,
  graph-hit counters, or expected log lines. Mismatched warmup shapes silently
  warm a different set of cache entries while total time looks fine.
- **Seven accounting errors to avoid** (from source): denominator drift;
  double counting; timing points inside async branches; comparing absolute
  values across windows (same-window A/B only); mixing fixed into per-request;
  trusting unmeasured segments; skipping the warmup hit check.
- Benchmark hygiene (InferRSI): report preparation/startup/readiness, warmups,
  and measured work as separate numbers.

## 3. Weight acquisition and verification

Sharded downloads (modelscope/HF-style) — operational rules:

- Parallelize with bounded workers (`--max-workers 16` style), select only
  needed shards (`--include '{subset}/**'`).
- `.incomplete` marker files mean in-flight shards, not corruption; wait or
  resume, do not re-download blindly.
- Verify completeness structurally: shard numbering has no gaps **and** the
  set matches `*.safetensors.index.json` `weight_map` keys. On mismatch,
  cross-check weight_map and fetch only the missing shards.
- Measure aggregate rate by `du -sh` differencing on a stable segment (not
  ramp-up); expect single-digit MB/s on slow networks — hours for ~134 GiB is
  normal, not a defect. Triage downloader logs as WARNING (transient) vs
  ERROR (real failure) to avoid false alarms.
- To test a load path without real bytes, generate structure-identical fake
  weights from `model_index.json`/configs (metadata-only download).

## 4. Device-side weight prefetch

Decision rules (cannbot `model-infer-prefetch`, `torch_npu.npu_prefetch`;
methodology transfers, the API is NPU-specific):

- **Only on profiled memory-bound hot spots** — never speculative.
- The **dependency window** (work overlapping the prefetch) must be
  non-memory-bound: use the window after a large MatMul completes, or any
  compute/communication segment whose output is available.
- `max_size` starts at **50% of the theoretical size**; after verified wins,
  step up 0.7 → 1.0 of theoretical. Never start at 1.0.
- Every prefetch sits behind an `enable_prefetch` switch, **default False**.
- Verify a single operator first; then extend position by position. Tuning
  order: position ↔ size, iteratively.
- **When to give up**: no safe dependency window → do not force prefetch.
  If the window regresses after enabling: shrink size or move position; if
  neither works, disable and record.
- Adjacent pattern (TRT-LLM): move periodic background bookkeeping and
  weight-movement off the critical stream; the same shape carries to
  KV-cache defrag/transfer and weight streaming.

## 5. CPU-tier offload ordering

When weights/activations do not fit device memory:

- **Order candidates by change surface** (smallest first): batch size →
  resolution → CFG/feature flags → CPU offload / layered offload →
  tensor parallel degree → activation checkpointing.
- **Construction-phase OOM is not an inference-phase OOM**: for construction
  OOM use meta-device construction then `to_empty` fill; tier-downs
  (resolution, CFG) do not help construction memory.
- **Offload benefit ceiling = the un-overlapped transfer share**: if transfer
  is already hidden behind compute, offload buys nothing; re-estimate after
  adopting each tier.
- Diffusers-on-NPU playbook by free VRAM (≥ 40 GB / 32–40 / < 32 / < 16):
  `enable_model_cpu_offload(device="npu:0")` (do **not** `pipe.to("npu")`
  first; requires `accelerate`); gains bounded by PCIe bandwidth;
  sequential per-layer offload only as the last resort.
- KV-cache host offload (TRT-LLM pattern): fold side caches into the unified
  paged KV manager to inherit host/secondary offload and block reuse;
  `host_cache_size` sizing; host-offloaded blocks are indexed by physical
  memory-pool index, not logical block ID; null Python views before the C++
  free.
- NPU serving shallow knob: `--swap-space 8` (CPU swap when NPU memory is
  full).

---

## 6. Loading modes: mmap / mlock / direct I/O / lazy (llama.cpp pattern)

For the division between loading, NUMA/thread placement and runtime-state diagnosis,
use the [llama.cpp owner map](../../repositories/llama-cpp/audit-llama-runtime-state/SKILL.md#choose-the-scope).
Source pins and static-inspection dates stay with their respective owners.

At the pinned revision (3e390af) loading is one unified flag,
`--load-mode {auto|none|mmap|mlock|mmap+mlock|dio}` (default `auto` = mmap
unless the device lacks `mmap_support`). The legacy standalone `--mlock` /
`--no-mmap` flags no longer exist — they are mode values now. Always record
the effective mode; the loader logs it (`load_mode = %s`).

| Mode | What it does | Trade-off |
|---|---|---|
| `auto` | mmap unless device lacks support | default |
| `none` | full read into RAM | slower load, may reduce pageouts; the only mode with exact load progress (mmap progress is unreliable on some platforms) |
| `mmap` | file-backed pages, on-demand fault | fastest startup, lowest committed RAM; OS may page the model out under pressure |
| `mlock` | force residency, no swap/compress | paging-stall avoidance at committed-RAM cost; gated by RLIMIT_MEMLOCK (`ulimit -l`; Apple `vm.user_wire_limit`; Windows working-set quota) |
| `mmap+mlock` | map then lock | resident + zero-copy start; largest RAM commitment |
| `dio` | direct I/O through a staging buffer | bypasses the page cache; avoids double-caching |

Mechanics that matter when choosing:

- **mmap prefetch tuning**: Linux path issues `POSIX_FADV_SEQUENTIAL`, adds
  `MAP_POPULATE` only when prefetching and no lazy ranges exist (populate
  would fault lazy ranges in), `POSIX_MADV_WILLNEED` for non-lazy ranges and
  `POSIX_MADV_RANDOM` for lazy ones.
- **NUMA disables eager populate**: when NUMA handling is active, the mmap
  path forces prefetch off and uses `MADV_RANDOM` over the whole mapping —
  placement and loading mode interact; do not tune them independently. Docs
  recommend dropping the page cache before the first NUMA-enabled run, and
  warn that kernel auto NUMA balancing (`/proc/sys/kernel/numa_balancing`)
  impairs performance.
- **mlock grows incrementally**: the locked extent tracks the highest loaded
  offset (`grow_to(offs + n_size)`), not the whole file up front; lazy
  tensors are deliberately excluded (locking would fault them fully in).
  First lock failure latches silently — a run can end partially locked with
  only a warning; check `ulimit -l` before relying on residency.
- **Lazy mode** (`--lazy-mode on|auto|off`, default auto = tensors > 4 GiB):
  read rows of huge tensors (per-layer embeddings) from disk on demand
  instead of keeping them resident — requires mmap; trades startup/RAM for
  disk re-reads on access.
- **Memory-fit probes force `--load-mode none`**: mmap-backed free-memory
  accounting is distorted; any "how much VRAM is free" measurement must
  bypass mmap.
- Host/GPU split flags route weights without reloading: `--cpu-moe` /
  `--n-cpu-moe` / `--n-cpu-ffn` keep expert/FFN weights in host buffers via
  tensor buffer-type overrides; `--moe-cache-mib` adds a GPU staging cache
  for CPU-kept experts; KV on device vs host toggles separately.

## 7. High-throughput loading mechanics (fastsafetensors pattern)

The complementary design point: **not** using mmap at all on the main path,
because per-tensor mmap faulting cannot saturate NVMe. Instead: parallel
async file→device copy, then lazy zero-copy tensor instantiation (DLPack
capsules over the device buffer with refcounted shared ownership). mmap
survives only as the unified-memory fallback (mmap → `pin_memory` →
`memcpyAsync`: kernel readahead + pinning in one path).

Bounce-buffer reader (the no-GDS path):

- Persistent worker pool per loader; each worker alternates **2 pinned host
  slots and 2 streams**, so `pread` on one slot overlaps H2D copy on the
  other.
- Block size = `ceil(bounce_budget / (threads × 2))`; default budget 16 MiB,
  default threads 16. Auto-tune heuristic: threads = physical cores of the
  GPU's NUMA node; budget = that node's total L2 cache size.
- Reader workers NUMA-bind to the GPU's node.
- O_DIRECT per filesystem policy: network filesystems and tmpfs/ramfs stay
  buffered (keep kernel readahead); O_DIRECT EINVAL retries once then warns.
- Windows serializes `pread` under a file mutex — expect lower reader
  parallelism there.

Direct-to-device (GDS/cuFile, CUDA/ROCm-bound): worker-split `cuFileRead`
into the device buffer; 4 KiB-aligned rounding with coalesced boundary
pages; in-device `memmove` repair for unaligned whole-file loads (blocking);
the GDS bounce cache is charged as fixed overhead from
`cuFileDriverGetProperties`; check `/dev/nvidia-fs0` before driver init
(half-configured hosts close fd 0); per-loader fallback to the bounce path.
CUDA ≥ 12.2 tolerates non-O_DIRECT descriptors.

Tensor-readiness overlap: publish tensor views while IO is in flight; a
consumer waits only on the completed DMA prefix covering its tensor (fenced
prefix for pread paths, 16 MiB blocks for unified memory). Accessing unread
bytes raises an error rather than returning garbage. Enabled only when the
alignment repair is not needed (it would race the DMA).

Partial reads and memory planning:

- Byte-range filtering: read only kept tensors' offsets, coalesced with a
  4 KiB merge gap; expert-parallel ranks filter to owned experts — unowned
  MoE bytes are never read.
- Sub-file chunking bounded by `max_batch_bytes`; a chunk must be at least
  the largest tensor.
- Static fit planner: `resident + depth × multiplier × budget + overhead ≤
  budget` at every moment; all inputs header-derived → deterministic plans,
  identical across ranks (lockstep without collectives); pipeline depth
  auto-clamps as residency grows; no runtime feedback — failures re-plan.

Measurement protocol for any load path (how fastsafetensors benchmarks):

- Phase timers reported separately: init / header registration / copy (io) /
  tensor instantiation (get). Never one elapsed number.
- Cold-cache runs via `posix_fadvise(POSIX_FADV_DONTNEED)` per file (or a
  global page-cache drop); `iostat 1` / dool CSV captured alongside.
- Baseline = stock loader (mmap + pageable copy) on identical files; flag to
  exclude driver init when measuring loader-only cost.
- Author-reported (not locally validated): bounce path 6.02 GB/s vs mmap
  1.28 GB/s (GPT-2 Medium, MI300X); 26.4 GB/s NVMe→GPU with GDS on 4 GPUs;
  vLLM startup 12.39 s → 4.74 s. The pipeline/chunking/overlap features have
  no perf harness at that revision — correctness tests only.

---

## 8. Checkpoint save/restore (fastsafetensors saver pattern)

What the save path actually supports at 219e256 (observed in `saver.py`,
`docs/overview.md` §"Saving checkpoints", and saver tests):

**Supported:**

- Synchronous, blocking, sharded safetensors writes (`ParallelSaver.save` /
  `save_entries`, or the `save_sharded` / `plan_shards` / `write_shards`
  function layer). Default 16 size-balanced shards
  (`{base}-00001-of-000NN.safetensors`), largest-first packing.
- Parallel per-tensor fill threads that block on all results before
  returning — parallel writes, synchronous completion. Custom `fill`
  encoders accept opaque sources and manage their own parallelism.
- Per-file atomic publish: each shard is written to a unique temp file,
  then `os.replace`d to its final path. A failed fill removes all temps —
  nothing is left at final paths.
- Disk-space preflight (`min_free_bytes`) before any file is created.
- fsync of file + mmap + directory is **opt-in** (`fsync=False` default;
  directory fsync skipped on Windows).
- Device tensors saved via host copy (detach → contiguous → flat); dtype
  preserved as-is (F4 packed layout supported). No dtype conversion happens
  inside the saver — downcast/quantize before entry or inside a custom
  fill.
- Reload is the existing loader: returned paths feed `ParallelLoader` /
  `fastsafe_open` directly (round-trip tested).
- Every shard header carries `fst.shard.index/count/set` (a per-write id)
  so a set can be validated later — but `validate_shard_set` is called by
  no production code and is not exported; set integrity is caller logic.

**Explicitly not supported / unknown — record as unknown, never assume:**

- Whole-set atomic publish — documented: "the set is not published
  atomically". A mid-rename failure can leave a mixed set (some finals
  published, temps gone); this path is untested and recovery is a caller
  obligation.
- Async checkpointing: no submit/wait split, no futures, no completion
  callbacks (unlike the loader's producer/consumer pipeline).
- Distributed / multi-rank save coordination: no rank or process-group
  logic exists.
- Crash durability: `fsync=True` flushes file/mmap/directory, but no
  crash behavior is documented or tested anywhere in the inspected files.
- GDS / direct-storage writing: not implemented — device tensors go
  through host copy.
- Concurrent saves to the same base: last rename wins per path; no
  locking (in-process threads only).

## 9. Choose distributed tensor delivery (fastsafetensors pattern)

Use this procedure when files have designated loading ranks and the consumer
needs replicated weights or tensor-parallel (TP) slices. TP means ranks hold
different slices of a model tensor. The source-scoped
[transfer contract and readset](references/fastsafetensors-transfer-readset.md)
bind these rules to `219e2561a41ede2d5d8eba611c248bb0effbf580` (Apache-2.0).
They describe implementation and proposed checks, not measured gains.

1. **Fix ownership and order before choosing a collective.** Give every rank
   the same file-to-loader-group-rank map, tensor names, shapes, dtypes and
   call order. The file owner reads the selected data into its device buffer;
   `FilesBufferOnDevice` then delivers it. Use ranks within the loader's
   process group, including for a subgroup whose members differ from world
   ranks. A file assignment is not the final model-shard assignment.
2. **Choose by the required output, not by file size.**

   | Required output | Entry and path at this source pin | Cost / condition |
   |---|---|---|
   | Complete tensor on every rank | `get_tensor(name)` → `get_sharded(name, -1)` → broadcast | Owner clones its tensor; receivers allocate a full tensor. Every rank retains a full copy. |
   | A slice along one tensor dimension | `get_sharded(name, dim)` → `shuffle` → scatter | Source forms contiguous slices; each rank allocates its slice. This is not direct reading of only that rank's shard bytes from storage. |
   | Whole tensors streamed through the pipeline | `ParallelLoader.iterate_weights()` → eligible coalesced runs, otherwise per-tensor broadcast | This iterator does not choose TP shard dimensions; apply the consumer's slicing contract separately if needed. |
   | Independent, rank-specific filtered reads | `ParallelLoader(all_local=True, tensor_filter=...)` | Uses a single-process loader group per rank; no cross-rank loader broadcast. Do not count these reads as network optimization. |

   Scatter uses `block = ceil(shape[dim] / group_size)` and rank `r`'s
   interval `[r * block, min((r + 1) * block, shape[dim]))`. Validate that this
   partition matches the model's expected shard layout. Uneven or empty
   slices need backend-specific qualification; the slicing calculation alone
   does not establish that a collective accepts unequal sizes. Start with a
   divisible dimension and supported dtype rather than promising arbitrary
   TP layouts or packed-dtype behavior.
3. **Consider coalescing for many adjacent replicated tensors.** At this pin
   it is enabled only for a multi-rank PyTorch loader, positive
   `broadcast_run_bytes` and `broadcast_run_tensors`, and
   `resident_tensor is None`. Defaults are 16 MiB and 64 tensors; either
   limit set to zero disables it. All ranks must use identical limits and
   planning inputs. Runs preserve checkpoint order and split at a different
   file/owner, byte gap, byte or count limit, incompatible dtype alignment,
   or empty tensor. An individual tensor larger than the byte limit travels
   alone; the setting does not split tensors or impose a hard peak-memory cap.
4. **Charge the local work and preserve completion.** The coalesced PyTorch
   path waits for every source range in the run, clones the contiguous span
   once into owned byte storage, broadcasts it once and rebuilds typed views
   sharing that storage. Receivers allocate the run too. This reduces collective
   calls where tensors can join; it does not eliminate payload bytes or the
   source clone. For CUDA/NCCL, `work.wait()` orders the current CUDA stream;
   it is not a CPU-blocking whole-device drain. CPU/Gloo completion follows
   that backend's wait contract; do not apply CUDA stream semantics to it.
   The iterator drains transient CUDA runs and its final CUDA stream before
   releasing the load buffers. Keep that completion path.
5. **Match retention to the consumer.** Default owning outputs survive buffer
   close, but a small retained view can keep an entire coalesced run alive.
   A `resident_tensor` predicate disables coalescing so selected resident
   tensors do not retain unrelated run storage. With
   `accumulate_resident=False`, relocate and release each yielded tensor
   before requesting the next; do not retain a dictionary of transient views.
   Close a partially consumed iterator before closing its loader. Borrowed
   tensors require a single-process loader group and completion before
   advance/close; they cannot be combined with this distributed path.

**Counter-signals:** one rank or Paddle does not select this coalesced
PyTorch path; rank-specific filters with a distributed loader are rejected;
different rank orders/plans can mismatch collectives. Gapped or mostly large
tensors may offer few joins, and retaining a run to keep one small tensor can
cost more memory than individual delivery. A faster H2D copy or a local clone
does not prove faster cross-rank communication or inter-node network use.

**Proposed verification before adoption:** compare coalescing disabled versus
enabled with identical checkpoint, rank mapping, backend, topology, dtype,
cache state, chunk/queue budgets and consumer retention. On every rank compare
key order, shape, dtype and tensor bytes with the reference; for scatter
compare the expected dimension slice, including a non-prefix subgroup. Cover
mixed dtypes/alignment, gaps, an empty tensor, an oversized singleton,
early iterator close and filtered-read rejection. Observe actual collective
count/payload, copy/wait time and peak live storage separately from file I/O;
check completion and buffer release after both exhaustion and early close.
Then measure complete startup under §2/§7's accounting protocol. These are
verification targets, not results from this distillation.

## Negative findings and remaining gaps

First-layer scan (8 local repos, 2026-10-15, scoped to inspected
sparse-checkout paths): no mmap/pinned/shard-parallel loading mechanics, no
checkpoint save/restore I/O, no disk-tier offload, no fio-class storage
benchmarking — recorded because the three big repos are skill-doc-only
checkouts; absence there is not absence upstream.

Wave-5/6 approved sources closed most of this: loading modes and mmap/mlock
placement decisions (llama.cpp), pinned-staging parallel-read mechanics and
a load-path measurement protocol (fastsafetensors), runtime KV-to-disk
tiering (LMCache → `kv-tier-management`), block-device measurement
methodology (fio/sysstat → `storage-io-measurement`), and checkpoint
save/restore semantics (§8 above). The fastsafetensors-specific save-performance
gap remains: its inspected saver supplied no perf harness, benchmarks or
documented tuning levers. Wave 7 adds separate candidates rather than extending
that source's support claims:

- `dcp-async-save-performance`: DCP-only staging/pause/buffer-lifetime decisions.
- `checkpoint-recovery-consistency`: DLRover and NVIDIA Resiliency Extension
  generation/replica/failure-domain contracts, not save-throughput evidence.

Measurement caveat (mindie-agent): disk read/write counters include cache
and pipes — they are **logical I/O, not physical disk writes**; without
dropping the OS file cache, a run is not a cold-start physical test.

## Known limitations

- MindIE-SD host-opt numbers (134 GiB / hours / single-digit MB/s) are
  author-observed on their network, not benchmarks.
- The prefetch escalation ladder (50% → 0.7 → 1.0) is source guidance, not
  a measured optimum.
- `model-infer-prefetch` API details (`torch_npu.npu_prefetch` signature,
  dependency wiring) are NPU-specific; consult the CANN docs of the target
  version.
- fastsafetensors mechanisms are CUDA/ROCm/Windows-bound — **no Ascend/NPU
  path exists in that repo**; the methodology (bounce buffering, readiness
  overlap, static planning, phase-timed measurement) transfers, the APIs do
  not. All its numbers are author-reported.
- llama.cpp loading modes are POSIX/Windows, CPU-centric mechanisms; their
  trade-offs are qualitatively documented with no numeric benchmarks in the
  docs, and NUMA handling is Linux-only. Never imply Ascend support.
- Flag surfaces move between revisions (llama.cpp replaced `--mlock` /
  `--no-mmap` with `--load-mode` values); re-verify entry paths against the
  pinned revision before relying on any flag name.

## 10. Separate preparation from serving

The [Flare preparation boundary](references/flare-preparation-boundary.md)
adds a source-scoped example of Python load/tune/compile/capture, a native
exporter and Rust serving. Record what is serialized, what must be rebuilt,
which live resource owners stay in the preparation process, and the independent
execution ABI/prepared-contract versions. Reject mismatches instead of editing
their tags. Keep preparation/export, package load/readiness and request timing
separate; changing language at the boundary does not by itself establish a gain.
For complete runtime KV/recurrent/convolution/tail state, follow that reference
to the Flare session owner. The addition remains candidate and empirical not_run.

## Verification checklist (before claiming a load-path win)

- [ ] Fixed overhead accounted separately from per-request cost
- [ ] Every accounting line has timing points + bytes + counts + evidence
- [ ] Warmup validated by hit criteria (cache entries / graph hits / logs)
- [ ] Before/after compared same-window, same affinity, same device state
- [ ] Loading mode recorded and identical across compared runs (mmap state
      changes cache temperature; fit probes bypass mmap)
- [ ] Load latency reported per phase (init / header / io / get), cold-cache
      protocol stated (fadvise or page-cache drop)
- [ ] Prefetch changes verified single-op first, switch defaults recorded
- [ ] Offload tier wins re-estimated against un-overlapped transfer share
