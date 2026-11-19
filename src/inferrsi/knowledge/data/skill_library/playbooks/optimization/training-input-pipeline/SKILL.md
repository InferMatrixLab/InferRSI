---
name: training-input-pipeline
description: 'Diagnose training input stalls and choose bounded queue, shard-cache and cache-ownership changes from DALI, Mosaic Streaming and FFCV. Preserve execution-mode gates, sample ordering and per-host memory budgets; separate remote downloads, local storage reads and host/device transfers.

  '
metadata:
  inferrsi: |
    {
      "tags": [
        "training",
        "input-pipeline",
        "prefetch",
        "dataset",
        "memory",
        "storage"
      ],
      "status": "candidate",
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "empirical_validation": "not_run",
      "applicability": {
        "scope": "Diagnosing training input stalls and choosing bounded queue, shard-cache and cache-ownership changes from DALI, Mosaic Streaming and FFCV, while preserving execution-mode gates, sample ordering and per-host memory budgets and separating remote downloads, local storage reads and host/device transfers",
        "prerequisites": "The pinned readset and its license constraints are read; reading authorizes no commands, cache manipulation or experiment",
        "input_contract": "Dataset format, sample-size distribution, workers and ranks per host, ordering/shuffle, local-cache state and executor mode; a per-host memory budget that includes checkpoint staging and runtime offload; timings that separate remote fetch, decompression/decoding, transformation, batch readiness and device transfer",
        "produced_artifact": "One proposed queue, shard-cache or cache-ownership change with its source-backed rule and boundary, the evidence proposed to confirm it, and a verification contract for a separately authorized comparison; no input-throughput, model-quality or hardware result",
        "failure_modes": [
          "Low accelerator utilization is taken to identify which producer stage is late",
          "Missing legacy DALI statistics are read as zero use, or the execution mode is switched silently to obtain them, which changes the comparison",
          "DALI run() returning is read as output-ready timing instead of the outputs() synchronization boundary",
          "Mosaic predownload is treated as a byte cap or request count, or per-worker sample targets are multiplied into an exact network-byte prediction",
          "Look-ahead is increased when the local cache cannot retain the working set, so evicted shards are downloaded again",
          "cache_limit is read as a bound on total process RAM, or the constructor minimum as an optimum or a guarantee against thrashing",
          "An FFCV memory map is taken as proof that its pages are resident"
        ],
        "refusal_point": "Rejects changes that violate sample coverage or the stated reproducibility contract even if batches arrive faster, does not report queue depth alone as a performance result, and draws no NPU acceleration claim from the CUDA-oriented DALI source"
      },
      "recommendations": [
        "Record dataset format, sample sizes, workers per host, ordering, cache state and executor mode before proposing one change.",
        "Increase Mosaic look-ahead only when readiness starvation is observed and cache headroom exists; otherwise address shard and working-set residency first.",
        "Check the exact DALI configuration surface before use, because the constructor and deserialization paths use different queue keys.",
        "In a later comparison, separate warm-cache throughput from cold retrieval and initialization, and report step time with input wait, host/HBM peaks and actual I/O."
      ],
      "limitations": [
        "Source-derived candidate; no local efficacy validation.",
        "Original typed source inventory is not normalized; retain source identities and limits in the procedure/readsets."
      ],
      "provenance_readsets": [
        "references/sources.md"
      ],
      "consumption_mode": "packaged"
    }
---

# Training Input Pipeline Decisions

Status: candidate. No input-throughput, model-quality or hardware run performed.
Sources and license constraints: [pinned readset](references/sources.md).
Reading this guidance authorizes no commands, cache manipulation or experiment.

## Resource mapping and first decision

- Accelerator → Observe, Configure, Optimize: DALI CPU/GPU pipeline exposure.
- RAM / Host → Observe, Diagnose, Configure, Optimize: buffers and cache pressure.
- SSD / Storage → Diagnose, Configure, Optimize: shard residency and local reads.
- Communication / Network → Configure, Optimize **only for Mosaic remote shard
  downloads**. DALI copies and FFCV mmap do not establish network coverage.
- OS / System → Configure, Optimize: FFCV OS-versus-process cache ownership,
  not scheduler-priority tuning.

Separate remote fetch, decompression/decoding, transformation, batch readiness
and device transfer. A low accelerator utilization number does not identify
which producer stage is late. Record dataset format, sample-size distribution,
workers/ranks per host, ordering/shuffle, local-cache state and executor mode
before proposing one change. The memory budget includes checkpoint staging and
runtime offload already competing with the input pipeline.

## B1 — DALI queue and output-buffer sizing

| Decision | Source-backed rule | Boundary |
|---|---|---|
| Hide uneven batch preparation | `exec_pipelined` overlaps CPU/GPU work; deeper `prefetch_queue_depth` increases buffering | More queue slots consume memory; startup queue fill differs from steady-state training |
| Size CPU and mixed/GPU queues independently | Constructor documents `{"cpu_size": x, "gpu_size": y}` | Requires `exec_async=True`, `exec_pipelined=True`, `exec_dynamic=False` |
| Use operator output-buffer evidence | Enable memory statistics and inspect `executor_statistics()` real/reserved and maximum sizes per output | Statistics are available only with `exec_dynamic=False`; this Python API is not a C++ executor audit |
| Set an allocation hint | Relate observed output sizes to `bytes_per_sample_hint`, keeping per-output and per-sample units distinct | A hint is not a hard RAM cap; queue depth, batch size and shape variation still matter |

Dynamic execution can be the default when async/pipelined execution uses no
separated queues. Do not read missing legacy statistics as zero use or switch
execution modes silently just to obtain them. Changing mode changes the
comparison. `run()` returning asynchronously is not output-ready timing;
`outputs()` is the documented synchronization boundary.

The inspected deserialization path uses different queue dictionary keys from
the constructor documentation. Keep constructor and deserialization entry
paths distinct; the exact configuration surface must be checked before use.
No NPU acceleration claim follows from this CUDA-oriented source.

## B2 — Mosaic bounded look-ahead and shard readiness

`predownload` is a **target count of samples per worker**, not a byte cap or
number of requests. At the pin its omitted value becomes `8 * batch_size`.
Sample look-ahead is also not a strict exact-count invariant: the loop tests
whether the target is less than the current distance before advancing.

The prepare thread initiates shard download/decompression; the ready thread
waits for contiguous usable samples; the yield loop waits behind readiness.
A shard can become remote again after eviction, causing a ready worker to
request it again. More look-ahead can therefore increase churn when the local
cache cannot retain the working set.

- `cache_limit` bounds shard-cache bytes, not total process RAM. Admission
  budgets compressed **and** raw forms during decompression.
- The inspected constructor rejects a limit no larger than index usage and a
  limit below four times the largest shard's maximum raw-plus-compressed size.
  This is a revision-specific implementation minimum, not a universal optimum
  or a guarantee against thrashing.
- Least-recently-used eviction happens under a shared cache lock; multiple
  workers may share download progress. Do not multiply per-worker sample
  targets into an exact network-byte prediction.
- A new epoch terminates the old iterator's prepare/ready loops. Preserve
  dataset partitioning, shuffle and resume semantics while tuning prefetch.

Candidate decision: increase look-ahead only when readiness starvation is
observed and cache headroom exists; otherwise consider shard/working-set
residency first. Proposed evidence is input-wait distribution, remote downloaded
bytes, repeated shard downloads, eviction/decompression activity and cache
occupancy. No measurements or cache changes were made here.

## B3 — FFCV cache owner and traversal order

| Workload condition | Candidate | Qualification |
|---|---|---|
| Dataset working set fits usable host cache, or local processes share it | `os_cache=True` selects `OSCacheManager` | Backed by read-only NumPy mmap; mapping a file does not prove its pages are resident |
| Working set exceeds usable RAM | Consider process-managed cache and `QUASI_RANDOM` access order | Source describes reduced disk reads, mostly useful with `os_cache=False`; no guarantee for arbitrary datasets |
| Uneven preparation causes batch wait | Review `batches_ahead` | Prepared batch buffers consume memory independently of dataset cache |
| Distributed training | Keep supported traversal semantics | `QUASI_RANDOM` is documented unavailable in distributed mode at this revision |

FFCV requires `.beton` conversion. The inspected OS cache retains its mmap
context between epochs instead of reopening it. `os_cache=False` selects the
process manager, but that manager's full eviction implementation was not mined.
The revision is historical; current Python/Numba/PyTorch/platform compatibility
is unverified. No drop-cache, mmap residency or decode correctness test ran.

## Proposed verification contract

For a separately authorized comparison, keep sample identities, output shapes,
labels, augmentation policy, rank partition and ordering requirements fixed.
Separate warm-cache throughput from cold retrieval and initialization. Report
training step time together with input wait, host/HBM peaks and actual I/O;
queue depth alone is not a performance result. Reject changes that violate
sample coverage or the stated reproducibility contract, even if batches arrive
faster. Hardware qualification, sample/augmentation parity and measured gains
remain unresolved.
