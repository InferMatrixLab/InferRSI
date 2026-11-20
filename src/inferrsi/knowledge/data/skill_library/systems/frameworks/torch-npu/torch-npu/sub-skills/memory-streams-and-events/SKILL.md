---
name: memory-streams-and-events
description: "Reason about TorchNPU device and pinned-host ownership, stream dependencies, events, asynchronous copies, allocator caches and graph interaction."
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "NOASSERTION",
      "disable-model-invocation": true,
      "metadata": {
        "disco-role": "operating"
      },
      "tags": [
        "torch-npu",
        "ascend",
        "pytorch",
        "memory-streams-and-events"
      ],
      "applicability": {
        "scope": "Source-grounded TorchNPU operation and diagnosis; qualify the selected installed stack independently.",
        "prerequisites": "Compatible Linux, PyTorch, TorchNPU, CANN, driver and authorized Ascend device access for device execution.",
        "input_contract": "Exact stack identities, bounded workload, tensor metadata and intended correctness/measurement boundary.",
        "produced_artifact": "A source-supported procedure or diagnostic trace with actual pass/fail/not-run observations.",
        "failure_modes": "Confusing registration with device readiness, CPU fallback with NPU execution, or source inspection with runtime proof.",
        "refusal_point": "Withhold backend correctness/performance conclusions when required device/runtime evidence is missing.",
        "hardware": "Ascend NPU required for device, stream, graph, precision, profiling and HCCL checks."
      },
      "limitations": [
        "Source-derived candidate; installed API and NPU/CANN execution were not validated.",
        "BLOCKED_REQUIRED_BACKEND: Linux Ascend NPU/CANN stack, multi-rank HCCL and optional compiler runtime checks remain unavailable.",
        "No model quality, benchmark gain, service/E2E claim or candidate promotion follows from static checks.",
        "Representative pinned op-plugin inspection does not cover every operator or external CANN kernel implementation."
      ],
      "consumption_mode": "packaged",
      "provenance_readsets": [
        "references/source-map.md"
      ]
    }
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
