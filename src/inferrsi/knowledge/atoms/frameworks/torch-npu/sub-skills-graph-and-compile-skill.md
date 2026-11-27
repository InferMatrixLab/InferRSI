---
name: graph-and-compile
description: "Choose and debug TorchNPU manual NPUGraph, npugraphs, npugraph_ex, TorchAir, Inductor and FXRT compilation routes with explicit storage and backend gates."
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
        "graph-and-compile"
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

# Choose capture and compilation paths

Use for graph replay, `torch.compile`, graph breaks, stale results, compiler
dependency failures or unexpected eager fallback. Read [the graph procedure](references/graphs.md)
and [failure recovery](references/troubleshooting.md).

Inputs: exact stack/revisions, backend name, eager function, input shapes/dtypes/
strides, mutation and aliasing, state/RNG, capture stream and output lifetime.
Output: selected backend contract, eager-versus-compiled/replayed comparison,
capture assumptions and unresolved compiler/device checks.

1. Establish a correct eager NPU result before capture.
2. Select manual NPUGraph, built-in graph backend, TorchAir, Inductor or FXRT
   explicitly; record optional compiler availability.
3. Preserve stable storage and legal stream/capture operations.
4. Compare updated-input replays, then benchmark after warmup and synchronization.
5. Use [the bundled graph case](../../scripts/runtime_smoke.py) with
   `--case graph --run` for a tiny manual replay check, not compiler conformance.

Use [memory](../memory-streams-and-events/SKILL.md) for pool/lifetime questions
and [operator development](../operator-development/SKILL.md) for missing Meta
or custom-op registrations. TorchAir and CANN internals remain external evidence
boundaries; no backend speedup is established by this source study.
