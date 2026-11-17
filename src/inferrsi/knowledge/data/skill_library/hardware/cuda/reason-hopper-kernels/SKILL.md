---
name: reason-hopper-kernels
description: Reason about Hopper SM90 CUDA GEMM kernels using TMA and mbarrier lifetimes, WGMMA warpgroup participation, register and pipeline budgets, layouts, software scheduling and FP8 scaling. Use for an H100/H200-family kernel diagnosis or a Blackwell-to-Hopper applicability check; source-derived candidate guidance with no local GPU validation.
---

# Reason about Hopper kernels

Use this procedure to turn an observed Hopper kernel bottleneck into one bounded
change and a correctness-first verification proposal. It does not implement a
kernel or establish installed library support. All operational steps are
**proposed**; the references distinguish inspected source facts, upstream reports
and unresolved claims. Empirical validation is **not_run**.

Read [source qualification and coverage](references/sources.md) first when using
KernelWiki material: its SM90 tags do not establish Hopper compatibility. The
[inventory](references/source-inventory.json) accounts for every synthesis page
and every source-page header advertising SM90 at the pinned snapshot. Read the
[retained notices](references/notices.md) before reusing source material.

## Establish the actual contract

Record device and compute capability, compiler/toolkit and target flags, kernel
and library revisions, selected implementation, shape/strides/alignment, operand,
scale, accumulation and output types, grouping/masking, epilogue and correctness
criterion. Distinguish kernel steady state from quantization, layout conversion,
JIT/descriptor setup, launch overhead and whole-request time.

Confirm the actual instruction path. Hopper WGMMA needs an architecture-specific
SM90a compilation path; a device-family label, a package import or a generic
SM90 dispatch guard does not prove that path was built or selected. Do not map
Blackwell tcgen05, TMEM, hardware block-scaled MMA, CLC or two-SM MMA recipes to
Hopper. Hopper thread-block clusters and TMA multicast are separate capabilities.

## Choose the next discriminating check

| Signal | Inspect and reason about | Small candidate and counter-signal |
| --- | --- | --- |
| TMA/barrier stalls, stale data, hang or size-sensitive failure | [Synchronization](references/synchronization.md): full/empty stages, transaction bytes, phase on reuse, WGMMA completion and epilogue-store lifetime | Repair the ownership protocol before tuning depth. A wait can be a correct dependency, not evidence of insufficient stages. |
| High registers, spills or low resident work | [Resource/layout/scheduling tradeoffs](references/resources-and-scheduling.md): all live accumulators, role budgets, padded SMEM and scale/epilogue storage | Reduce a live range, tile or unroll factor; compare against extra IO or lost instruction parallelism. A register cap can add spills. |
| Load/compute gaps with a long independent K-loop | Same reference: producer/consumer specialization and stage cost | Consider one extra input stage or a role change only after proving independence. Short K or lower residency can make it slower. |
| Low device utilization, thin/grouped GEMM or a long last wave | Same reference: useful tile count, actual residency, software schedule, locality and reduction cost | Compare tile/raster/grouping choices. Persistence cannot create missing work; split-K adds reduction and numerical obligations. |
| FP8 error or scaling/preprocessing cost | [FP8](references/fp8.md): scale meaning/layout, reduction-chunk boundary, partial-sum lifetime and output contract | Change one scale/layout/promotion choice; recheck error and the full conversion-plus-GEMM boundary. A software E8M0 representation is not native block-scaled WGMMA. |

For attention, start with
[diagnose-attention-bottlenecks](../diagnose-attention-bottlenecks/SKILL.md) for
online-softmax, mask, forward/backward and quality obligations; use this owner's
references only for the selected Hopper mechanism. General kernel lifecycle and
measurement remain with
[kernel-writing-guide](../../../methods/kernel-writing-guide/SKILL.md).

## Return a reviewable hypothesis

State the source path/revision and evidence class; observed signal and missing
observations; semantic and architecture prerequisites; one proposed change; the
resource or accuracy exchange; a counter-signal and stop condition; and the next
check. Retain a rejected direction with its changed-condition requirement.

For later authorized validation, first check tails, zero/short K, repeated stage
wraparound, multiple work tiles, grouped offsets and output/scale layout against
the frozen reference. Inspect generated PTX/SASS and compiler resources on the
actual stack. Then compare the same workload and boundary, accounting for setup,
conversion, reduction, synchronization and epilogue costs. A source report or CPU
packaging check establishes no GPU correctness, performance or service gain.
