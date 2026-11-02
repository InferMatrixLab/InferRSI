---
name: pytorch-inference-profiler
description: "Schedule a PyTorch profiler window and separate CPU, CUDA and PrivateUse1 activities from shape-tracing copies. Use for what the trace can show, not for a measured speedup."
---

# PyTorch inference profiler

Status: candidate. Empirical validation: **not_run**. Pin: `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457`.

## Procedure

1. F: `schedule(wait, warmup, active, repeat=0, skip_first=0, skip_first_wait=0)` emits `NONE` during skip and wait, `WARMUP`, then `RECORD`, and `RECORD_AND_SAVE` on the last active step of the cycle. `repeat=0` continues until profiling stops. `active` must be positive. `warmup=0` warns that results can skew. P: keep at least one warmup step before reading a steady decode trace. The warning is not a measured bias.
2. F: user schedules must not return `DEVICE_STOPPED`. That value is internal.
3. F: the `profile` docstring lists CPU, CUDA and XPU activities. `_KinetoProfile` also branches on `PrivateUse1`. P: an NPU activity name is TorchNPU's alias of `PrivateUse1`, not a symbol defined by this file.
4. F: `record_shapes=True` holds tensor references and can block reference-count optimizations and add copies. `with_stack` records file and line. P: turn them on to attribute an op, then off for a timing run. A profiled step is not the unprofiled latency.
5. F: chrome export defaults the worker name to hostname plus pid and uses a nanosecond timestamp. P: redact host names and source paths before sharing a trace. This repository's privacy rules apply to captured artifacts.

## Later check

Record wait, warmup and active step counts, activity set, whether shapes and stacks were enabled, and the profiler version. Compare one unprofiled step only under a separate authorized run. No trace was collected here.

## Limits

Kineto and CUPTI were not read. Host-overhead ratios from other skills are not this profiler's output. NPU levels are [torchnpu-profiler-and-compile](../../../hardware/ascend/torchnpu-profiler-and-compile/SKILL.md).
