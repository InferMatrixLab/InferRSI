---
name: torchnpu-graph-capture
description: "Capture and replay a TorchNPU NPUGraph, including pool sharing, capture-error mode, the pre-capture sync and auto-dispatch update. Use for graph lifetime, not allocator tuning or a measured replay speedup."
---

# TorchNPU NPUGraph capture

Status: candidate. Empirical validation: **not_run**. Pin: `54e365d3e3614299bccd17f06916544c3880c9fc`.

Device allocator private-pool destruction rules stay with [torchnpu-device-memory-lifecycle](../torchnpu-device-memory-lifecycle/SKILL.md) at the older pin. vLLM-Ascend's wrapper and TorchAir are different repositories.

## Procedure

1. F: `torch.npu.graph` synchronizes the device, optionally runs `gc.collect()` when `force_npugraph_gc` is true, then calls `empty_cache` and `host_empty_cache` before `capture_begin`. P: capture entry is a global sync and cache flush. Do not place it on an overlap-critical path without a separate measurement.
2. F: `force_npugraph_gc` defaults to false and reads `TORCH_NPUGRAPH_GC`. Its docstring says true is the backward-compatible behavior. P: keep both sentences. This pin's default is false; the comment does not change that assignment.
3. F: default `capture_error_mode` is `global`. `thread_local` limits the malloc check to the current thread. `relaxed` does not error on those actions. The docstring says not to change it without knowing `aclmdlRICaptureMode`. P: `relaxed` is a weaker check, not a faster safe mode.
4. F: if a pool is omitted, capture uses a fresh pool token. The note says that sharing a pool with a previous capture that passed an explicit stream requires the same stream again. The class comment says only one capture should run in the process and that default-stream initialization is not thread safe. P: do not overlap two captures.
5. F: `NPUGraph.update` raises unless `auto_dispatch_capture` was true during capture. `replay` calls the C++ replay. `make_graphed_callables` defaults to three warmup iterations and its docstring still says the forward runs CUDA work as a CUDA graph. P: treat that CUDA wording as stale documentation inside the NPU file, not as a CUDA compatibility result. Warmup is a source default, not a tuned value.
6. F: `utils/_graph_tree.py` registers a Dynamo backend named `npugraphs` when missing, replaces `torch._inductor.compile_fx.cudagraphify` and `cudagraph_trees.get_manager`, and exposes `torch.compiler.npugraph_mark_step_begin`. P: patching Inductor's CUDA-graph entry does not prove CUDA-graph semantics on NPU. `npu/_graph_tree.py` was not mined.

## Limits

ACL runtime, CANN and the C++ graph object were not read. No replay latency was measured. External streams cannot capture; see the streams skill.
