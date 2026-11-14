# Weight, runtime and segment lifetime

Evidence class: CODE observations at
`b13a48219d5cdf408edcb93da6cd69b612ed03d3`, subject to the archive identity
boundary in [source notes](source-notes.md). Proposed downstream changes and
benefits are hypotheses until tested on the selected runtime/backend/model.

## Two capacity questions, several owners

[`DeviceMemoryRequest`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/device_residency_manager.h#L17-L46)
contains compute backend, runner owner, pending allocation, retained runtime and
optional backend limit. Its runtime peak covers runtime buffers, while the
manager accounts for weights separately.

[`GGMLRunner::memory_requests`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/ggml_runner.cpp#L722-L759)
subtracts reusable workspace from measured workspace growth, adds pending cache
outputs, and includes retained workspace/cache buffers. Residency updates use
the runner's identity and backend;
[`retained_runtime_buffer_bytes` / `sync_runtime_residency`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/ggml_runner.cpp#L239-L259)
include runtime workspace, runner cache and graph-cut cache. Different runner
objects on the same physical device can therefore consume the same capacity.

[`ModelManager::check_capacity`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L1759-L1841)
checks both:

- Device allocation headroom: pending allocation + missing weights + a pinned
  512 MiB implementation margin, against backend-reported free bytes bounded
  by tracked residency when total bytes are known.
- Explicit managed budget: retained current runtime + pending allocation +
  missing weights, against the cap minus already resident weights and other
  runner runtime buffers. A zero configured cap does not disable the separate
  device-headroom question.

The code handles unknown memory reports and a Vulkan-specific impossible free
report; these cases require actual backend observations. Split buffers expose
only total bytes, so the code conservatively charges that upper bound on each
participating device. This is not measured per-shard memory. The 512 MiB margin
is not a transferable recommendation or a guarantee for every driver allocation.

[`ensure_compute_backend_capacity`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L1855-L2019)
tries other owners' idle workspace reclaimers, protects pinned/explicitly
protected/prefetched tensors, then considers reloadable resident tensors in the
preferred order and global last-use order. Additional disk demotion has explicit
eligibility exclusions, including mapped, active, LoRA-applied and split states.
It can fail when safe reclamation is insufficient. CPU returns before this
accelerator reclamation path; CPU success cannot qualify it.

## Graph segmentation and protected use

[`execute_graph`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/ggml_runner.cpp#L829-L884)
uses segments only for non-CPU single-device execution with enabled management,
a valid multi-segment cut plan and a monolithic fit failure. Planning adds a
128 MiB headroom; execution keeps its normal limits. Multi-device scheduling and
CPU take other branches. Do not infer segmentation from configuration alone.

The
[`segment loop`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/ggml_runner.cpp#L894-L1015)
binds live graph-cut inputs, prepares measurement/workspace, prepares weights,
remeasures after possible LoRA work, checks capacity around allocation, stages
inputs, optionally prefetches, computes, captures outputs, reads final results,
and synchronizes before pruning consumed cuts. Cleanup restores bindings,
unpins parameters, frees segment context and updates runtime residency, including
failure returns. The underlying GGML/driver correctness is not established by
reading this caller.

[`prepare_params`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L1576-L1638)
loads/stages required states, increments pin counts and records the use epoch
before applying LoRAs. A failed LoRA application releases that usage and
invalidates the affected sources.
[`SegmentWeightPipeline::segment_start/end`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/segment_weight_pipeline.cpp#L83-L126)
holds the prepared parameter set through use. `release_compute_backend_params`
only decrements pins; it is not a promise of immediate physical deallocation.
Runtime ownership ends separately through
[`runner_end`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/ggml_runner.cpp#L460-L499).

[`ComputeWorkspace::segment_end/release`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/compute_workspace.cpp#L225-L269)
synchronizes an active workspace and rejects release while active. Its tracked
buffer bytes are neither total process memory nor every driver's scratch byte.

## Optional next-segment prefetch

[`enqueue_next`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/segment_weight_pipeline.cpp#L128-L204)
finds the next parameter-bearing segment, excludes parameters already used by
the current segment, checks missing residency and async support, protects both
current and proposed next weights, and admits capacity before scheduling. Only
`Scheduled` records a queued set. Unsupported/failed paths clear and disable
prefetch; an already-resident set needs no transfer.
[`activate`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/segment_weight_pipeline.cpp#L45-L81)
activates a matching queued segment before normal weight preparation.

The manager's
[`populate_prefetch_block` / `prefetch_params`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager_prefetch.cpp#L61-L261)
allocates separate staging tensors, enqueues host-set or backend-copy operations
on a transfer backend, and records an event when available. Split buffers, CPU,
missing async capability and incompatible parameter placement do not establish
this path. Parameters requiring initial storage loads can still incur synchronous
preparation before transfer scheduling. During
[`activation and clear`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager_prefetch.cpp#L264-L354),
the prefetch block is synchronized before prepared tensor buffers are installed
or discarded. The
[`synchronization helper`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager_prefetch.cpp#L31-L59)
waits on the event or transfer backend before freeing staging resources. This
caller-side ordering is observed; the unbundled GGML implementation and actual
driver completion remain unverified.

Performance hypothesis: when transfer can overlap useful work and extra queued
weights fit safely, prefetch may reduce exposed transfer time. It may instead
increase residency, evictions or host pressure; short segments, incompatible
placement or unsupported async paths may provide no benefit. A backend capability
flag and source scheduling are not evidence of real overlap or faster images.

Preserve these invariants when transferring the idea: active weights survive
their consumers; queued weights are not evicted before activation; output views
survive their final callbacks/readback; asynchronous work finishes before buffer
reuse; and accounting separates weights, current runtime, other runners and
pending allocations without counting a reusable buffer twice.
