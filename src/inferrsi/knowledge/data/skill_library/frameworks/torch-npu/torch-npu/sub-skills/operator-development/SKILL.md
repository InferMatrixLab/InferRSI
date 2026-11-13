---
name: operator-development
description: "Develop or diagnose TorchNPU operators across schema/code generation, PrivateUse1, autograd, Meta, ACLNN and legacy ACL adapter paths."
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
