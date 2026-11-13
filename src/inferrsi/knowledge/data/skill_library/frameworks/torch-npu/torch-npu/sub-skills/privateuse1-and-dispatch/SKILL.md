---
name: privateuse1-and-dispatch
description: "Trace TorchNPU initialization, PrivateUse1 registration, lazy device setup, operator dispatch and explicit CPU fallback boundaries."
---

# Trace registration and dispatch

Use when `torch.npu` is missing, a tensor unexpectedly executes on CPU,
PrivateUse1 registration conflicts, an autograd path fails, or import loads
unexpected compiler state. Read [registration and dispatch](references/dispatch.md)
and [failure recovery](references/troubleshooting.md).

Inputs: plugin/torch revision, fresh-process import order, autoload settings,
operator schema/overload, tensor devices/dtypes and gradient context. Output:
an initialization or dispatch trace with the selected kernel/fallback and the
first failing boundary.

1. Locate failure in core extension, backend registration, patches, lifecycle
   barrier or optional feature setup.
2. Separate renamed PrivateUse1/device methods from actual runtime initialization.
3. For one operator, identify schema, dispatch key, implementation and fallback.
4. Check forward, autograd and Meta paths independently; route missing kernels
   to [operator development](../operator-development/SKILL.md).
5. Validate with a fresh interpreter and the actual NPU stack. Record CPU fallback
   rather than describing a CPU result as NPU coverage.

For broad CUDA-to-NPU migration, [the support reference](../../references/support-workflows.md)
describes the opt-in transfer shim and its process-wide effects. Importing this
skill never enables that shim.
