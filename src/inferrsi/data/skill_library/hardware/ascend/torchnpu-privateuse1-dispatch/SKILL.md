---
name: torchnpu-privateuse1-dispatch
description: "Register TorchNPU as PyTorch PrivateUse1 under the name npu, including generated tensor methods, excluded quantized dtypes and the profiler activity alias. Use for backend identity, not for kernel coverage."
---

# TorchNPU PrivateUse1 registration

Status: candidate. Empirical validation: **not_run**. Pin: `54e365d3e3614299bccd17f06916544c3880c9fc`.

PyTorch's key list is [pytorch-dispatcher-and-custom-ops](../../../frameworks/pytorch/pytorch-dispatcher-and-custom-ops/SKILL.md) at v2.15.0. This skill is the TorchNPU caller of that extension point, at a different commit.

## Procedure

1. F: `register_privateuse1_backend` calls `torch.utils.rename_privateuse1_backend("npu")`, aliases the profiler activity, `_register_device_module("npu", torch_npu.npu)`, and `generate_methods_for_privateuse1_backend` for tensor, module and storage. P: after this runs, `torch.npu` is the registered module. The registry manager raises if `torch.npu` is missing. Registration is not runtime initialization.
2. F: the registry manager comment says this function must not initialize the NPU runtime; lazy init owns that. It then runs a CANN package check. P: importing the registration path is not proof the device is usable. The check body was not read.
3. F: unsupported dtypes passed into method generation are `quint8`, `quint4x2`, `quint2x4`, `qint32` and `qint8`. P: do not assume those quantized dtypes have tensor methods. Other dtypes are not certified by omission.
4. F: the profiler alias sets `ProfilerActivity.NPU` to `PrivateUse1` when the name is absent. If `torch.utils.backend_registration._rename_profiler_activity` exists it is preferred. The comment says torch 2.12 lacks that helper. P: `version.txt` does not list 2.12. The branch is compatibility code, not evidence this tag builds 2.12.
5. F: selected graph helper ops in `graphs.py` register `PrivateUse1` impls, and flex-attention patches register `AutocastPrivateUse1`. P: those impls are not a catalogue of ATen coverage. op_plugin kernels were not read.

## Limits

No operator count, fallback rate or numeric parity was measured.
