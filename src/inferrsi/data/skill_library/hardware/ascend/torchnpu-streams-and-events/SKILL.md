---
name: torchnpu-streams-and-events
description: "Order TorchNPU work with managed streams and events, and avoid external-stream APIs the wrapper rejects. Use for stream capability limits, not for allocator reuse or a measured overlap gain."
---

# TorchNPU streams and events

Status: candidate. Empirical validation: **not_run**. Pin: `54e365d3e3614299bccd17f06916544c3880c9fc`.

`record_stream` lifetime inside the caching allocator remains the older device-memory skill. This file documents the Python stream wrapper at the newer tag, including APIs that external streams reject.

## Procedure

1. F: `Stream.wait_stream` records an event on the other stream and waits on it. `Event` says the underlying event is created lazily on first record or export, only same-device streams may record it, and any device may wait. P: a wait is an ordering edge. It is not a host-side duration measurement.
2. F: `ExternalStream` does not own the `aclrtStream` lifetime. Non-default `priority` or `is_sync_launch` raises. The documented unsupported list includes `synchronize`, `query`, `record_event`, `wait_event`, `wait_stream`, `Tensor.record_stream`, graph capture, graph task groups, super-kernel scope, host callbacks and task-queue event ops. The note says those paths go through an internal `AsyncTaskQueue` that only tracks streams TorchNPU created. P: an externally created stream is not a drop-in `torch.npu.Stream`. Do not use it for capture or allocator stream tracking.
3. F: graph capture refuses external streams in that table. P: capture uses a managed stream; see [torchnpu-graph-capture](../torchnpu-graph-capture/SKILL.md).
4. P: side-stream overlap still needs a measured gap between independent work. This wrapper does not provide that measurement. CUDA's 32-wide pool aliasing is a PyTorch CUDA fact, not an NPU pool size; the NPU pool implementation was not read.

## Limits

C++ stream and task-queue sources were not read. No multi-stream timeline was collected.
