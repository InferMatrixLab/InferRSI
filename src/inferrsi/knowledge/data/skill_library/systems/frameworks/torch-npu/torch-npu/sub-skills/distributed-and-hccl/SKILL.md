---
name: distributed-and-hccl
description: "Launch and diagnose TorchNPU HCCL communication, process groups, asynchronous work, stream ownership and higher-level distributed integration boundaries."
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
        "distributed-and-hccl"
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
