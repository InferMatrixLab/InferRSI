> Supplier integration proposal, preserved as historical source context (2026-10-15). The local owner review and current two matrices govern acceptance; suggested follow-ups and permission statements below do not authorize work or describe the current inventory.

# Pack D incremental integration proposals

Status: candidate; empirical_validation: not_run. No matrix, InferRSI file, installed skill or PR was changed.

## Prior coverage and incremental value

The supplied Reference Matrix already credits `dense-performance-evidence`, `kernel-writing-guide`, `performance-ceiling-analysis`, Ascend operator profiling/tuning/tiling, and attribution-aware overlap. Their general measurement/roofline/evidence workflows are prerequisites, not new Pack D outputs. [Exact overlap limits](../sources.md#prior-coverage-inspected-before-extraction) record that the underlying roofline readset files/skill bodies were not supplied.

The separate `ascend-aclgraph-capture-replay` candidate addresses runtime graph eligibility and host dispatch/capture concerns. Pack D's increment is the within-attention progression from materialization to ownership, operation-class throughput, dependency-aware overlap and quantization/layout acceptance. It provides no new graph-runtime, allocator or Ascend implementation summary.

One [diagnose-attention-bottlenecks](../../SKILL.md) skill is proposed because the user-facing decision is unified. Its nine mechanism records support different branches, rather than becoming nine overlapping skills. Three cases retain distinct counter-signals. The [cost-model boundary note](knowledge/attention-cost-model-boundaries.md) is knowledge, not a third matrix or executable predictor.

## Proposal for docs/reference-matrix.md only

Add three version-scoped paper references, linked to the shared [readset](../sources.md):

- D1 / arXiv 2205.14135v2: dense exact-attention online statistics, tile-fit IO model, selective backward recomputation, scoped lower bound, and short-baseline/plateau counterexamples. Accelerator only.
- D2 / arXiv 2307.08691v1: non-matmul work reduction, query-row/column-gradient ownership, sequence work supply and intra-CTA reduction cost; combined rather than isolated attribution. Accelerator only.
- D3 / arXiv 2407.08608v2: Hopper async producer/consumer and inter-iteration scheduling, compiler/register counterexample, FP8 layouts and synthetic accuracy ablations. Accelerator only.

If the matrix uses `mined`, qualify it as extracted into a candidate, never local validation. Link the skill and appropriate cases. Do not assert current implementation support or rank cross-paper speedups.

## Proposal for docs/searchspace-matrix.md only

Propose links within existing **Accelerator** analysis/optimization/verification cells, matching the matrix's actual stage vocabulary when integrating:

- Diagnosis/cost analysis: [IO plateau case](cases/io-reduction-can-plateau.md), [partitioning case](cases/partitioning-after-fusion.md), and operation-specific ceilings in the knowledge note.
- Optimization proposals: online accumulation/recompute, independent output ownership, bounded async scheduling, layout-aware low precision, all gated by the operational skill.
- Verification: [overlap/FP8 counter-signals](cases/overlap-and-fp8-counter-signals.md), with correctness, instruction schedule, register/SMEM pressure, exact timing boundary and error baseline.

The latest SearchSpace Matrix body was not supplied, so these are cell-link proposals, not claims of current inventory or completed coverage. Device HBM/SRAM/SMEM/registers do not fill RAM/Host, SSD/Storage or Communication/Network cells. No new matrix is proposed.

## Acceptance boundary

Promote only after a separately authorized, workload-specific review/evaluation. Preserve paper version, readset and attribution. No hardware test, reproduction, environment change, framework run or tooling expansion is included. [Next-gate leads](NEXT_GATE_LEADS.md) remain unread and receive no evidence credit.
