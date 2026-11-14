---
name: diagnose-attention-bottlenecks
description: Diagnose the next attention-kernel bottleneck after IO reduction using evidence about HBM traffic, work ownership, parallelism, scalar work, asynchronous scheduling and precision. Produce a bounded optimization hypothesis and correctness-first verification plan; do not infer current library support or NPU portability from GPU papers.
---

# Diagnose attention bottlenecks

All steps below are **P: proposed operational rules**. This skill produces a diagnosis and future test proposal, not executable kernel code or a validated tuning recommendation. Read [sources](references/sources.md) before making a numerical claim; [mechanisms](references/mechanisms.md) records the supporting `F` facts and counter-evidence.

## Trigger and evidence gate

Use when attention remains slow despite fusion/tiling, a larger tile or deeper pipeline regresses, low-precision throughput disappoints, or a proposed hardware port assumes that the paper's instructions transfer directly.

Obtain the actual kernel/library revision and device; forward/backward or inference phase; batch, query/KV lengths, head count and head dimension; causal/padding masks, dropout and MQA/GQA; input, accumulator and intermediate dtypes; output/gradient tolerance and task-quality requirements. Distinguish an attention kernel from a whole training step or serving request.

Request existing evidence for HBM bytes and allocation, shared-memory/register use and spills, independent CTA/work-tile counts, synchronization/atomic waits, Tensor Core/GEMM activity, scalar/special-function work, and exposed load/compute stalls. A low percentage of peak FLOP/s does not identify which is limiting. If these observations are unavailable, return conditional hypotheses and the missing evidence; do not initiate profiling or runs without authorization in the current task.

## Decision procedure

1. **Check semantics before costs.** Preserve stable online-softmax normalization, masks and dropout replay; require correct output and gradients at the approved tolerance. Dense exact attention, block-sparse attention and quantized attention have different contracts. Exact algebra does not imply bitwise-identical floating-point results. Do not turn the historical papers' pseudocode directly into an implementation without resolving their notation/boundary issues. [F1–F3; sources, interpretation cautions]
2. **Find the HBM materialization.** If an N-by-N score/probability or gradient intermediate crosses device HBM, consider tiled online accumulation and selective recomputation. Budget the Q/K/V/output tiles, statistics and score tile together in fast memory. Count transferred elements separately from peak allocated bytes. Extra recomputation FLOPs can be worthwhile only if the avoided transfers were sufficiently expensive. [F1–F2]
3. **Reclassify after fusion.** When HBM traffic falls but latency stops improving, inspect scalar normalization and special functions separately from matmul. Consider holding an unnormalized running output until final normalization and storing row logsumexp for backward. Do not use a single scalar FLOP ceiling for mixed matmul and softmax work. [F3; F6]
4. **Inspect independent work and ownership.** If batch times heads supplies too little work for the device, consider independent query-row tiles in forward. Prefer owners that can finish their own output without an inter-warp reduction. Backward is different: column-tile parallelism shares dQ and may require atomics or another explicit reduction strategy. Require a synchronization and gradient-correctness contract; do not remove communication merely because forward avoids it. [F4–F5]
5. **Tune tile size against resource ceilings.** Larger tiles can reduce IO yet raise register/shared-memory demand, reduce schedulable work or spill. Record the active constraint and head dimension; do not copy the paper's tile sizes, 80-block heuristic, or block-size-256 plateau into a universal threshold. [F2; F5]
6. **Gate overlap on real independence.** With supported asynchronous copy and matmul, draw producer/consumer and inter-iteration dependencies. Bound circular buffers; release a stage only after its consumers finish. Compare inter-warpgroup scheduling with intra-warpgroup pipelining as distinct mechanisms. Budget the extra score/probability buffers, and verify the generated instruction schedule rather than assuming source-code order survives compilation. Deeper pipelines must earn their register/occupancy cost. [F6–F7]
7. **Treat FP8 as a layout-plus-accuracy decision.** Establish supported operand/accumulator layouts, transpose and permutation costs, scaling granularity and outlier behavior. Measure preprocessing and conversion within the relevant end-to-end boundary. Block scaling and an orthogonal Q/K transform are candidate accuracy techniques, not evidence that a model's training or serving quality is preserved. Keep the numerical and performance tests separate. [F8–F9]
8. **Reclassify once more.** After any successful intervention, ask which resource now limits the same workload. Do not apply the entire sequence unconditionally or assume a later generation dominates every shape/baseline.

## Portability gate

The transferable ideas are IO-aware tiling, sufficient statistics, recomputation, independent output ownership, explicit dependency/lifetime management, and precision-aware accounting. Hopper TMA, WGMMA, setmaxnreg, bar.sync, LDSM/STSM and register permutations are concrete NVIDIA mechanisms. Another accelerator requires a separately approved capability mapping and validation; this corpus proves no Ascend/NPU implementation, support matrix or gain. Local device-memory movement is not host RAM, storage or network coverage.

If the evidence instead shows host dispatch/capture overhead, route to the separate graph/capture diagnostic. FlashAttention's device-kernel findings do not justify changing graph mode or capture sizes.

## Required output and proposed verification

Return: observed bottleneck and confidence; workload/semantic contract; one smallest candidate change; expected resource exchange; counter-signal; missing evidence; source ID; and the next authorization gate.

For a later authorized comparison, keep hardware/clock, stack, workload, dtype, mask/dropout and measurement boundary fixed. Report forward, backward and combined time separately; HBM bytes and allocation separately; fast-memory use/spills, active work and waits; preprocessing cost for precision changes; output/gradient error and any required task-quality result. State whether throughput counts useful matmuls, recomputation, causal masking and batch. Only claim application benefit after measuring that application boundary.

Reject or defer a proposal on wrong outputs/gradients, violated buffer lifetime, unverified compiler ordering, spills or memory overrun, unsupported primitives, unacceptable accuracy, or a gain that vanishes after including the omitted work. Empirical validation remains not_run; source-paper results do not establish local compatibility or efficacy.
