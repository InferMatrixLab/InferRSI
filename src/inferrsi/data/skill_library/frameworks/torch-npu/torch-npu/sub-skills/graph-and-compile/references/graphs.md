# Capture, compilation and replay

## Route selection

| Route | Selection | Distinct contract |
|---|---|---|
| Eager | Ordinary NPU calls | Correctness reference; no compilation claim. |
| Manual NPUGraph | `torch.npu.NPUGraph()` and `torch.npu.graph(g)` | Capture/replay fixed work with explicit storage/stream/RNG constraints. |
| Built-in graph tree | `torch.compile(fn, backend="npugraphs")` | Lazy NPU Dynamo/Inductor setup then `NpugraphsBackend`; output/lifetime and graph-tree cache semantics matter. |
| NPUGraph-EX | `torch.compile(fn, backend="npugraph_ex")` | Lazy optional package path with its own compiler config; not an alias for every graph route. |
| TorchAir | `torch.compile(fn, backend="npu")` | Uses TorchAir when packaged; if absent the inspected loader can return eager graph execution with a warning. Completion alone does not prove graph compilation. |
| Inductor | `torch.compile(fn, backend="inductor")` | NPU lowering/codegen selected by build/runtime config; `TORCHINDUCTOR_NPU_BACKEND` routes include default/Triton, AscendC, DVM and deprecated MLIR. Dependencies differ. |
| FXRT | `from torch_npu.fxrt import backend; torch.compile(fn, backend=backend)` | Optional in-wheel inference runtime with its own IR, view and memory behavior. |

These are source entry contracts (F11-F14), not an installed support matrix.
The `npu` eager fallback is particularly important: preserve the warning and
verify selected compiler activity before reporting successful compilation.
TorchAir's gitlink is retained but its source was not inspected in this run.
DVM/MLIR/Triton backend internals beyond inspected loader boundaries are also
unverified; changing a selector does not install their toolchain.

## Minimal manual workflow

Allocate static input before capture. Warm up the same operations on a side
stream and join it. Capture on a non-default managed stream, keep inputs and
outputs alive, update input values in place, replay and check the synchronized
host result. Use `python <SKILL_ROOT>/scripts/runtime_smoke.py --case graph --run`.
Never replace the static input's storage and assume the captured graph follows
the new Python variable. Validate shapes, strides, addresses and aliases again
when changing workloads. Returned captured output storage may be reused by a
later replay; clone or copy results before another replay when they must persist.

The Python graph context picks a side stream if none is supplied and performs
synchronization/cache cleanup before entering capture. C++ `capture_begin`
rejects default streams, unsupported external streams, `TASK_QUEUE_ENABLE=2`,
an instance already holding a captured graph and expandable pinned-host
allocation mode. The latter mode lacks capture private-pool integration and
could recycle pinned blocks incorrectly; do not suppress the guard (F11).

Capture allocates from a graph-private device/host pool and tracks generators
for replay numerics. Sharing a pool is a lifetime/execution-order decision,
not permission for arbitrary concurrent reuse. Keep pool-sharing order and
stream compatible with the captured storage. CPU tensor-value-dependent control
flow, host reads and dynamic shape changes require separate handling rather
than silently capturing the first branch.

## Compile and export support

For one selected compiler, compare eager and compiled results for the promised
dtype/shape range, multiple new values, input mutation and output retention.
Record graph breaks and recompilations, plus warmup/cache state. AOT/LibTorch
deployment also needs a matching generated artifact, ABI, runtime dependencies
and launcher; a Python compile success is not C++ deployment validation.

FXRT is built into the TorchNPU wheel unless disabled, and loads lazily through
`torch_npu.fxrt`. Its documented view path is zero-copy for supported view ops;
that does not imply all operations/copies are free. `FXRT_DISABLE_VIEW_OPS`
selects a bounded debugging comparison (`all` or named view families), and
`FXRT_DEV_DUMP_IR=1` requests an IR dump. Preserve generated input/output/alias
contracts. This graph inventories FXRT but does not claim comprehensive IR-pass
or executor inspection.

Measure completed execution after warmup, separately from compilation/capture
time. A graph microbenchmark cannot establish model-quality or service gains.
