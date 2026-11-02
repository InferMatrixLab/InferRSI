---
name: pytorch-dispatcher-and-custom-ops
description: "Separate PyTorch dispatcher registration from a custom-op schema before adding a backend kernel or an export boundary. Use for DispatchKey, PrivateUse1 and mutates_args, not for kernel performance."
---

# PyTorch dispatcher and custom ops

Status: candidate. Empirical validation: **not_run**. Pin: `pytorch/pytorch` `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` (`v2.15.0`). Read [source notes](references/source-notes.md) before using a symbol.

## Decision order

1. F: `Dispatcher` is the dynamic dispatch interface. A registration listener runs on operator `def`, not on `impl` or `fallback` (`Dispatcher.h` comments above `OpRegistrationListener`). P: do not treat a backend kernel registration as a new schema.
2. F: `DispatchKey.h` includes `PrivateUse1`, `AutocastPrivateUse1`, `BackendSelect` and `PythonDispatcher`. The header comment says `PythonDispatcher` is how Python intercepts a key. P: a PrivateUse1 impl does not by itself rename the backend or generate `tensor.npu` methods. That alias is TorchNPU's owner.
3. F: `torch.library.custom_op` requires a `namespace::name` identifier, accurate `mutates_args` (or the string `unknown`, which assumes every input is mutated), and optional `device_types`. `None` means a default impl for all device types. An op with no tensor arguments needs a `device` argument before a device-specific impl. `torch.Tag.out` custom ops do not support autograd. P: wrong `mutates_args` is undefined behavior in the docstring; do not guess it from a kernel name.
4. P: for export or `torch.compile`, keep the custom op as the graph boundary the decorator documents. Preventing tracing from entering the function is a contract, not a speedup.

## Evidence to request later

The operator name, schema, `mutates_args`, registered device types and whether autograd is required. A later run would compare eager and exported calls on those aliases. This extraction did not run that check.

## Limits

C++ `TORCH_LIBRARY` bodies, codegen and kernel performance are unread. NPU registration is [torchnpu-privateuse1-dispatch](../../../hardware/ascend/torchnpu-privateuse1-dispatch/SKILL.md) at a different pin.
