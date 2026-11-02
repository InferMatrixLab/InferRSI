---
name: pytorch-caching-allocator-and-streams
description: "Diagnose PyTorch v2.15 CUDA caching-allocator settings, private graph pools and stream-pool aliasing. Use for device allocator and stream lifetime, not the v2.8 host-copy procedure."
---

# CUDA caching allocator and streams

Status: candidate. Empirical validation: **not_run**. Pin: `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457`.

Host copy ordering and the caching host allocator remain [host-memory-management](../../../hardware/host/host-memory-management/SKILL.md) at v2.8.0. This skill does not re-read that path at v2.15.

## Allocator

1. F: `CUDAAllocatorConfig::instance` reads `PYTORCH_CUDA_ALLOC_CONF`, then on ROCm `PYTORCH_HIP_ALLOC_CONF` if that is unset, then `PYTORCH_ALLOC_CONF`. The static instance parses once. A later comment says reserve fields can be rewritten under a mutex by `setAllocatorSettings`. P: capture the process environment before import; do not assume a shell change after first use is visible. The reparse body was not read.
2. F: CUDA-specific keys include `backend`, `graph_capture_record_stream_reuse` (default false), `per_process_memory_fraction` (default 1.0), `throw_on_cudamalloc_oom`, pinned-register knobs and `expandable_segments_reserve` / `_by_class`. The default reserve spec is the fraction 1.125 and is consulted only when the config sets it.
3. F: `max_split_size`, garbage-collection threshold and power-of-two rounding are deprecated wrappers around `AcceleratorAllocatorConfig`. P: do not copy a numeric split threshold from an older comment. That shared config body was not read here.
4. F: `expandable_segments()` follows the shared flag and returns false, with a one-time warning, when this build lacks the driver API support checked in `CUDAAllocatorConfig.cpp`.
5. F: `beginAllocateToPool` / `endAllocateToPool` route allocations into a private pool and can run without `cudaStreamBeginCapture`. `markCaptureBegin` / `markCaptureEnd` are separate notifications that capture actually started. P: a private pool is not evidence that a graph is capturing. CUDA-graph output lifetime stays with the existing compiler card.

## Streams

F: each device lazily has a default-stream pool, a 32-stream low-priority pool used round-robin, and a high-priority pool. The 33rd low-priority request aliases the first stream, so those kernels cannot overlap. HIP builds do not distinguish the second and third pools. P: a new `torch.cuda.Stream()` is not a dedicated hardware stream once the pool wraps.

`recordStream` is a virtual allocator method. It records a stream on a data pointer. It does not insert a data dependency. The v2.8 host skill remains the owner for pinned-host reuse.

## Limits

`CUDACachingAllocator.cpp` was not read. No occupancy or fragmentation number was measured. NPU allocators stay with the TorchNPU skills at their own pin.
