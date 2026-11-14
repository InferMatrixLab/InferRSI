# AKG Affine tail guards

Status: source-derived candidate. This reference answers: **when a static CUDA
Affine loop extent is not divisible by its tile size, why can AKG emit full-size
point loops, and what must protect the tail accesses?** The worked contract is a
single band of zero-based, unit-step, perfectly nested elementwise loops. It is
not a contract for reductions, arbitrary affine maps, multilevel tiling or every
AKG backend.

Source: [mindspore-ai/akg](https://github.com/mindspore-ai/akg) at
`5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff`, Apache-2.0. The
[source ledger](#source-ledger) pins the implementation and fixture. A
`FileCheck` fixture describes expected intermediate representation (IR); it is
not an executed kernel result.

## Follow the selected branch

1. **Resolve the target before interpreting the option.** The standalone
   `akg-opt` driver registers AKG Affine passes. The
   `akg-affine-loop-tile` declaration defaults `inequality-convert-to-if` to
   false. The implementation initially defaults to CPU, while a function's
   `process` attribute overrides the target. The fixture has
   `process = "cuda"`. In the GPU optimization pipeline, the `gpuFast` block
   constructs `createAKGLoopTilingPass(kTargetCuda, true)`; the second argument
   enables automatic tile-size selection. That call is a pipeline insertion
   point, not evidence that a user's compilation selected it. [A, B, D, E]
2. **Check the actual loop and option gates.** The pass obtains tileable bands.
   Its static-path checks reject multiple GPU bands and nonconstant loop
   bounds. In `runCudaOperation`, a non-dynamic function or a reduction
   operator sets `inequalityConvertToIf = true`, regardless of its false
   declaration default. Here "dynamic" is the compiler's
   `ShapeAlignTool.getFuncArgSizes() > 0` state; do not substitute a guessed
   meaning based only on a tensor type. The reduction alternative exists but
   is outside this elementwise readset's qualification. [A]
3. **Establish tile-size ownership and branch priority.** With automatic tiling,
   the solver supplies sizes. Otherwise `tile-sizes` is used when nonempty and
   `tile-size` remains 1; a different `tile-size` supplies the common size
   instead. For one level, the size count equals the band size. After tiling,
   `separate` takes priority, then `separate-no-if`, then
   `inequality-convert-to-if`. A true guard option alone does not select the
   guard rewrite. CPU and NPU paths force `separateNoIf = true`; their tail
   strategy must not be inferred from this CUDA example. [A, B]
4. **Trace expansion and protection together.**
   `perfectlyNestedWithIf` selects point loops whose upper-bound maps have
   multiple results, the representation of competing tile/original bounds in
   this fixture. If there are none, it returns without adding a condition.
   `createFullBlock` finds constant-distance lower/upper bound pairs,
   constructs full-size loops, clones their body and replaces the old inner
   nest. The condition builder derives an inequality from the related outer
   loop's exclusive upper bound: `upper_bound - 1 - point_index >= 0`.
   The rewrite moves every non-yield operation from the new innermost body
   into the condition's then-region. Full-size loop bounds and protected body
   placement are one contract. [A]
5. **Preserve the boundary through the pipeline.** The inspected GPU pipeline
   subsequently invokes boundary-if extraction, memory promotion, mapping,
   kernel outlining and boundary-if restoration. Their implementations are
   outside this readset. Inspect the resulting accesses and synchronization
   at the boundary being claimed; the mere presence of `affine.if` at this
   pass does not prove later thread mapping, barrier legality, reduction
   semantics, numeric equivalence or a performance benefit. [D]

## Worked tail and counter-signals

The pinned fixture requests tile sizes `32,30,30` for FP32 elementwise
multiplication on shape `[32,1280,768]`. Its expected IR has full point-loop
spans of `32,30,30`, with **both loads, the multiply and the store** inside
one `affine.if` requiring the second index to be at most 1279 and the third
at most 767. The exactly divisible first dimension needs no additional
predicate in that expectation. [C]

Arithmetic consequence of that fixture: the last starts on the second and
third dimensions are 1260 and 750. Their nominal 30-element spans extend to
1289 and 779; only 20 and 18 elements respectively are valid. The condition
must exclude those excess indices before any input read as well as the output
write. Guarding only the store would still leave invalid input accesses.
This is a source-based deduction, not a reproduced execution.

Use these counter-signals to stop an unsupported conclusion:

| Observation | Interpretation / next check |
|---|---|
| Point loops extend beyond the original extent, with all relevant accesses under the expected condition | Consistent with this IR strategy; do not remove the guard to make the loops look simpler |
| A guard exists but an input load was hoisted outside it | Recheck access safety in that actual IR; predicate existence alone is insufficient |
| A divisible extent produces no new guard | Can match the early return when no point bound has competing results; verify the actual bounds and dispatch |
| The CPU/Ascend target or a separation option is selected | Follow that selected strategy; this CUDA guard contract does not qualify it |
| Multiple bands, dynamic bounds, reductions or multiple tiling levels are involved | Re-establish their supported loop/shape conditions; the worked fixture is insufficient |
| Transformation diagnostics appear despite a produced output file | Capture diagnostics and inspect IR; output existence alone does not certify the rewrite |

The helper can fail on an unexpected tiled-loop count, inability to construct a
constant-distance full block, or inability to construct the condition.
`tileEachBand` is void and prints an inequality-conversion diagnostic when the
helper returns failure; the shown branch does not explicitly call
`signalPassFailure`. This is a bounded source observation. A proposed
negative compiler test must check both diagnostics and emitted IR, rather than
assuming a process exit code certifies guard construction. No upstream defect
or recovery behavior is established by this reading. [A]

## Bounded verification procedure

1. Record the exact AKG revision/build, selected pipeline and options, function
   `process`, compiler dynamic-shape state, operator kind, band count,
   original bounds/steps and effective tile sizes. Keep a pre-tiling IR snapshot.
   If these do not match the worked contract, narrow the claim or obtain the
   relevant implementation evidence first.
2. With an already qualified AKG toolchain, run the pinned fixture's
   `akg-opt` / `FileCheck` command from its first line. Retain stdout, stderr,
   exit status and output IR. This step checks the stated IR expectation only.
   No AKG build or fixture execution was performed for this distillation.
3. Inspect the immediate output: outer tile steps, nominal point-loop bounds,
   every tail condition and both input/output access placement. Compare a
   divisible control and a non-divisible tail while keeping the operator,
   dtype and pipeline fixed. Check invalid indices on each remainder axis,
   including the corner where both indices exceed valid bounds.
4. For a claim about compiled execution, inspect the relevant later IR/code
   and then run the real selected backend against an independent reference.
   Freeze supported shapes/layout/dtype and tolerances; include divisible,
   remainder and smaller-than-tile cases where supported. Check access safety
   and synchronization on that actual path. IR pattern matching does not
   substitute for this step.
5. Only after correctness, measure with the same workload, device, compilation
   and warmup/cache policy. Record compile time separately from steady-state
   execution. Attribute any change to the executing code; no gain is predicted
   merely from replacing a min-bound loop with a conditional body.

The existing kernel-writing guide's tail-mask and verify-before-benchmark rules
remain applicable. Compiler-generated guards are one implementation of a
bounded access contract, not permission to omit masks in a handwritten kernel.

## Source ledger

All links below resolve within the same full revision
`5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff`. Line ranges are source
observations; proposed checks above were not executed.

| Key | Pinned path / lines | Read purpose |
|---|---|---|
| A | [LoopTiling.cpp](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L70-L112), [195–244](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L195-L244), [495–601](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L495-L601), [809–1081](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L809-L1081), [1084–1086](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L1084-L1086), [1123](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L1123), [1543–1581](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L1543-L1581), [1609–1698](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Dialect/Affine/Transforms/LoopTiling.cpp#L1609-L1698) | Target/defaults, size ownership, full-block and condition construction, branch priority, static checks and dispatch |
| B | [Affine/Passes.td, 72–95](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/include/akg/Dialect/Affine/Passes.td#L72-L95) | Pass name and option defaults |
| C | [inequality-conversion fixture, 1–47](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/tests/ut/Dialect/Affine/akg_loop_tiling_inequality_convert_to_if.mlir#L1-L47) | Exact command, input and FileCheck expectations; inspected, not run |
| D | [GPUOpt.cpp, 82–131](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/lib/Pipelines/GPUPipelines/GPUOpt.cpp#L82-L131) | Conditional pipeline insertion and downstream pass names only |
| E | [akg-opt.cpp, 67–101](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/akg-mlir/tools/akg-opt/akg-opt.cpp#L67-L101) | Standalone pass/driver registration |
| Context | [README_en.md, 1–30](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/README_en.md#L1-L30) | AKG-MLIR identity, distinct from AKG-AGENT |
| License | [LICENSE, 1–201](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/LICENSE#L1-L201), [NOTICE, 1–2](https://github.com/mindspore-ai/akg/blob/5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff/NOTICE#L1-L2); C++ files retain Apache-2.0 headers at 1–15 | Apache-2.0; MindSpore AKG, Copyright 2019–2025 Huawei Technologies Co., Ltd. This addition paraphrases the mechanism and retains attribution; no upstream implementation is vendored |

Uncovered: executed compiler/FileCheck behavior, downstream lowering correctness,
CUDA runtime/access/synchronization/numerics, performance, CPU/NPU strategies,
dynamic/reduction/multilevel paths and agent efficacy. This reference does not
promote the owner's candidate state.
