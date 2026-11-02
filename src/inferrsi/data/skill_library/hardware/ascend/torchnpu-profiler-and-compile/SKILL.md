---
name: torchnpu-profiler-and-compile
description: "Configure TorchNPU profiler levels and Dynamo in-graph NPU APIs, and keep npugraphs registration separate from a measured compile speedup. Use for trace prerequisites and trace rules."
---

# TorchNPU profiler and compile hooks

Status: candidate. Empirical validation: **not_run**. Pin: `54e365d3e3614299bccd17f06916544c3880c9fc`.

PyTorch's generic schedule and shape-tracing cost stay with [pytorch-inference-profiler](../../../frameworks/pytorch/pytorch-inference-profiler/SKILL.md). This skill adds the NPU wrapper and Dynamo hooks at the TorchNPU pin.

## Profiler

1. F: `torch_npu.profiler.profile` uses the supplied schedule when it is callable. Otherwise it warns and installs `_default_schedule_fn`. P: a non-callable schedule is not the caller's object; check the warning.
2. F: `export_stacks` warns and returns unless `with_stack` is set. Another export path requires `record_shapes` and either `with_stack` or `with_modules`. P: a trace without those flags cannot answer a stack or shape question. Enabling them has the PyTorch retention cost documented on the PyTorch skill; this file does not remeasure it.
3. F: `experimental_config.py` names profiler levels `Level0`, `Level1`, `Level2` and `Level_none`, export types `Db` and `Text`, and AI Core metrics including pipe utilization, arithmetic utilization, memory, L0, UB, L2 cache and resource-conflict ratio. P: names are an allow-list in this file, not a definition of the counter and not a collected profile. `HostSystem` also names CPU and memory. That is a host-side profiler option, not a host-allocator change.

## Compile hooks

1. F: `trace_rule.py` marks many `torch.npu` stream, memory, allocator and RNG calls as in-graph functions, and marks `torch.npu.set_device` as a skip. `current_device` is constant-folded and also listed as needing guards. P: constant-folding a device query can bake the traced device into a graph. Do not assume a later `set_device` is visible inside a compiled region; it is skipped, not folded.
2. F: the compiler config module in this pin exposes `force_npugraph_gc` and nothing else that was read. Graph capture behavior is the graph skill.
3. P: `npugraphs` registration is a backend name plus Inductor monkeypatches. It is not a measured compile or replay improvement. AOTInductor CUDA/CPU packaging is a PyTorch document and does not establish an NPU package.

## Limits

No profiler run, Dynamo trace or compiled graph was produced. CANN parser output was not read.
