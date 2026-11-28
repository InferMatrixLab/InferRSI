---
name: operator-development
description: "Develop or diagnose TorchNPU operators across schema/code generation, PrivateUse1, autograd, Meta, ACLNN and legacy ACL adapter paths."
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
        "operator-development"
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

# Develop and validate an NPU operator

Use for a missing overload, custom operator, wrong dtype/shape/aliasing behavior,
or compile/backward support gap. Read [the implementation procedure](references/development.md)
and [failure recovery](references/troubleshooting.md).

Inputs: exact schema, intended dtype/layout/device/shape range, mutability,
gradient requirements, PyTorch/TorchNPU/op-plugin/CANN revisions, target hardware
and reference outputs. Output: a schema/registration/kernel-boundary plan,
implementation checklist and correctness matrix with unverified entries.

1. Validate the contract with [the bundled checker](../../scripts/operator_contract.py).
2. Choose built-in operator adaptation versus a namespaced extension.
3. Implement device, autograd and Meta behavior as separate responsibilities.
4. Exercise scalar, broadcast, out/in-place, dtype and layout boundaries before
   compilation or graph capture.
5. Report L0 results from the actual accelerator and retain external-kernel
   boundaries. Source inspection does not establish custom kernel correctness.

Use [dispatch](../privateuse1-and-dispatch/SKILL.md) to identify the actual
entry path and [graphs](../graph-and-compile/SKILL.md) for capture constraints.
