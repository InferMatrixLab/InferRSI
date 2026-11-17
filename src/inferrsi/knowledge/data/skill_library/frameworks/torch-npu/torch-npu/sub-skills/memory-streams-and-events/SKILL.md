---
name: memory-streams-and-events
description: "Reason about TorchNPU device and pinned-host ownership, stream dependencies, events, asynchronous copies, allocator caches and graph interaction."
---

# Trace memory and stream lifetimes

Use for asynchronous corruption, unexpected memory retention, stream races,
pinned copy lifetime or misleading timings. Read [the ownership procedure](references/lifetimes.md)
and [failure recovery](references/troubleshooting.md).

Inputs: allocation owner, tensor/storage aliases, allocating/using streams,
event edges, host-copy boundaries, allocator configuration and exact build.
Output: ordering diagram, ownership table, synchronized measurements and one
bounded discriminating check.

1. Identify producer, consumer and completion boundaries.
2. Establish stream ordering and allocation lifetime separately.
3. Classify live, active, reserved and host-pinned memory independently.
4. Run [the bundled stream case](../../scripts/runtime_smoke.py) with
   `--case streams --run` on the qualified NPU host.
5. Route capture to [graphs](../graph-and-compile/SKILL.md) and communication
   ownership to [HCCL](../distributed-and-hccl/SKILL.md).

The existing library owners `torchnpu-device-memory-lifecycle` and
`torchnpu-pinned-host-memory-lifecycle` retain their earlier immutable source
pins. Load them by declared metadata reference for allocator-tuning depth; do
not treat this newer operating graph as an update to their evidence.
