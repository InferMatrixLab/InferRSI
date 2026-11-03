# Registration and dispatch mechanisms

## Import-to-runtime trace

At this pin, `torch_npu.__init__` temporarily disables recursive device autoload,
imports torch, checks accelerator conflicts and executes ordered setup:
core-module loader -> component registry -> patches -> runtime-lifecycle barrier
-> optional features. The loader exposes required C-extension children before
Python consumers, including profiler, distributed c10d and NPURT. It also imports
op-plugin registrations, custom ops, optimizers and Meta registrations. Import
is therefore more than a Python namespace alias (F3).

Backend registration renames PrivateUse1 to `npu`, registers `torch.npu`, then
generates Tensor/Module/Storage NPU convenience methods with explicit quantized
dtype exclusions. The registry states that this phase must not initialize the
device; runtime initialization belongs to `npu._lazy_init()`. C++
`NPUHooksInterface` maps pointers to device location, calls lazy init, creates
NPU generators and returns the pinned allocator. It rejects host pointers as
device-owned and restricts storage resize to base formats (F4).

Use a fresh process for import-order checks. The source import contract tests
that `import torch_npu` alone leaves `torch._dynamo`, `torch._inductor` and
`torch_npu._inductor` unloaded. Do not import those modules as part of a
minimal device-only readiness probe and then attribute their load to basic
import. Compiler initialization is a separate [route](../../graph-and-compile/SKILL.md).

## Dispatch trace for a single operator

Record the full schema including overload, mutable aliases, out arguments,
input devices, dtype, shape/stride and autograd state. Look for a registered
PrivateUse1 kernel, a composite path, explicit host implementation or backend
fallback; a `.npu()` method alone does not prove operator support.

At the pin, the global PrivateUse1 boxed fallback checks
`CheckCpuFallbackAllowed`, warns once per operator and delegates to ATen CPU
fallback. `TORCH_NPU_FALLBACK_CPU_DISABLE=1` rejects both this dispatcher path
and explicit CPU kernels that call the shared guard. SparsePrivateUse1 has a
separate error fallback, not the same blanket CPU path. AutogradPrivateUse1 has
its own not-implemented fallback. Hence forward output, backward availability,
Meta shape propagation and compilation support need separate evidence (F5).

To detect an accidental host path, start a bounded fresh-process reproduction
with fallback disabled before import. Preserve the error naming the operator,
then reduce inputs without changing overload/dtype. A succeeding GPU/NPU
output-location check alone does not prove all intermediate operations stayed
on device; inspect trace events if the concern is hidden transfers.

## Output contract

Return `Python call -> schema -> dispatch key -> registration/generated wrapper
-> op-plugin/adapter -> ACLNN or ACL boundary`, plus independent autograd and
Meta edges. Mark the last inspected boundary; do not invent a CANN kernel body.
Provenance and inspected spans are in the [source map](../../../references/source-map.md).
