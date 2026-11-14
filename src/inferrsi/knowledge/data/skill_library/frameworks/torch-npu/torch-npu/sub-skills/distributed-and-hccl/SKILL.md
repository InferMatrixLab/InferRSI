---
name: distributed-and-hccl
description: "Launch and diagnose TorchNPU HCCL communication, process groups, asynchronous work, stream ownership and higher-level distributed integration boundaries."
---

# Run and diagnose HCCL

Use for NPU distributed launch, collectives/P2P, hangs, work completion,
communication-stream memory or FSDP/DTensor integration. Read [the HCCL procedure](references/hccl.md)
and [failure recovery](references/troubleshooting.md).

Inputs: ranks/world/local ranks, one selected device per process, rendezvous,
stack/topology, collective order/tensor metadata and timeouts. Output: rank
mapping, ordered collective trace, correctness observations and exact blocked
runtime/dependency gates.

1. Qualify one-device execution, then establish rank/device mapping.
2. Initialize HCCL with a finite timeout and identical collective sequence.
3. Distinguish producer dependency, work handle, consumer-stream dependency and
   host completion.
4. Use [the bundled case](../../scripts/runtime_smoke.py) under `torchrun`
   with `--case hccl --run`; it never launches additional workers itself.
5. Escalate to the named higher-level integration only after collective
   correctness. Tie failures to the first differing rank/sequence.

Single-device checks, Gloo CPU collectives and source inspection cannot clear
HCCL `BLOCKED_REQUIRED_BACKEND`. Read [memory](../memory-streams-and-events/SKILL.md)
before changing communication-memory reuse policy.
