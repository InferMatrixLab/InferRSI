---
name: profiling-and-debugging
description: "Capture bounded TorchNPU CPU/NPU traces, memory timelines and synchronization-aware diagnostics; distinguish collection, parsing, completion and performance claims."
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
        "profiling-and-debugging"
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

# Profile and debug TorchNPU

Use for kernel/communication/host gaps, memory traces, async exceptions or stream
sanitizer diagnosis. Read [the profiling procedure](references/profiling.md)
and [failure recovery](references/troubleshooting.md).

Inputs: tiny correct reproduction, stack/backend, selected activities, bounded
schedule, trace output location and question to discriminate. Output: trace
collection/analysis status, relevant events/counters, completion boundary and
one source-grounded hypothesis.

1. Reproduce correctness without profiling.
2. Select CPU/NPU activities and minimal trace options.
3. Advance the schedule with `prof.step()` and verify actual artifacts.
4. For memory timelines include the required shape/memory/stack-or-module options.
5. Use [the bundled profile case](../../scripts/runtime_smoke.py) with
   `--case profile --run --output <NEW_TRACE_DIRECTORY>` on a qualified host.

For async error location use a fresh bounded run with the documented launch
blocking setting, then restore the normal timing mode. Profiling overhead and
microbenchmarks do not establish L4 service performance. Device trace collection
remains `BLOCKED_REQUIRED_BACKEND` without NPU/CANN profiling support.
