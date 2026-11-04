# Affine RMSNorm on Ascend NPU

Implement `compute(x, weight, *, eps) -> y` for contiguous float32 NPU tensors
`x[rows, features]` and `weight[features]`:
`y = x / sqrt(mean(x*x, axis=-1, keepdims=True) + eps) * weight`.
Preserve input and weight bytes, shape, dtype and device. The public, seeded
suite includes nonuniform signed weights, ordinary, zero, large and tiny inputs.
Only the decode/prefill shapes are timed. The independent CPU oracle uses scalar
double arithmetic and `math.fsum`; CPU reference computation is never a timed
candidate or a device fallback.

The baseline composes eager PyTorch NPU operations. The example candidate uses
the existing fused `torch_npu.npu_rms_norm` implementation; it is a reference
control, not a newly written kernel or evidence of Agent efficacy.

## Execution boundary

Run reviewed source only, inside a caller-owned single-device allocation. The
worker requires exactly one `ASCEND_RT_VISIBLE_DEVICES` entry and uses logical
device 0 without changing the scheduler's mapping. Discovery needs no PyTorch
import; execution requires an installed compatible torch/torch_npu/CANN runtime.
The existing formal SkillEval CPU sandbox explicitly rejects this adapter.

Input/weight generation, transfer, oracle preparation and output validation are
outside timing. Each timed call has distinct retained input objects and bytes.
The clock surrounds the eager call and its completion synchronization, following
an untimed pre-synchronization. It includes Python dispatch and synchronization
cost, so **synchronized eager-call latency is not pure device kernel time**.
Output copies and checks happen after the clock stops. Every measured output is
checked; incorrect output has no usable performance metric.

`profile` uses the Ascend PyTorch CPU/NPU profiler after warmup, separately from
measurement. Its raw local trace includes verification copies and must be
reviewed before publication; it is diagnostic, not a speed score. An empty
device-kernel trace is an error rather than successful profiling.

## Sources and limits

API/shape semantics follow the [official op-plugin API](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/docs/en/custom_APIs/torch_npu/%28beta%29torch_npu-npu_rms_norm.md),
[implementation](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/op_plugin/ops/opapi/RmsNormKernelOpApi.cpp)
and [tests](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/test/test_custom_ops/test_npu_rms_norm.py).
The source BSD-3-Clause license is retained in `LICENSE`. Workloads, scalar
oracle and adapters here are independently authored; upstream performance
numbers are not imported.

First qualification is limited to the recorded device and installed runtime,
float32, contiguous 2D forward execution and this public suite. It establishes
neither BF16/FP16, gradients, graph replay, hostile-producer isolation, arbitrary
NPU qualification nor service/skill/search benefit. A/A and reference controls
and issue-scoped predeclared gates are needed before choosing by speed.
