# Qwen S2-B1 search and decision record

In the [Qwen material-discovery exercise](https://github.com/InferMatrixLab/InferRSI/issues/380),
the agent considered combining RoPE, the VAE fastpath and fusion attention on
Ascend. It recommended checking initialization memory before attempting the
combination. The round produced a recommendation and had no candidate or new
device measurement.

Open the [generated round record](search/round-1.json) to trace that decision.

1. In `events`, `file-39` records the initial read of the Qwen case. The later
   search `file-73` records the query, scope and tool response. Under
   `delivery.passages` are three returned lines from the case. Line 18 describes
   the reported initialization OOM. Line 19 describes a resource reservation
   failure on a different host with a different combination.
2. In `materials`, find `qwen-ascend-rejected-directions.md`. Its `evidence`
   links line 18 to the assistant's actual recommendation. Line 16 also has a
   reviewed decision. Line 19 has no recorded adoption or rejection.
3. In `unresolved_details`, the broad search and the filename-filtering pipeline
   explain the partial coverage. `counts` is null. The individual verified
   passages and decisions remain available in the same file.

The [round outcome](results/summary.json) summarizes the decision and its limits.
The corpus was frozen at [InferMatrixLab/InferRSI revision f6d2007](https://github.com/InferMatrixLab/InferRSI/tree/f6d200775d554d08fb73673833611dd6ac02d14b/src/inferrsi/data/skill_library).
The reviewed passages come from three public sources.

- Cohort, fusion attention and initialization residency. [Qwen Ascend case, lines 6, 16 and 18](https://github.com/InferMatrixLab/InferRSI/blob/f6d200775d554d08fb73673833611dd6ac02d14b/src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen-ascend-rejected-directions.md#L6)
- Applicability conditions and evidence limits. [Typed case, lines 15 and 17](https://github.com/InferMatrixLab/InferRSI/blob/f6d200775d554d08fb73673833611dd6ac02d14b/src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen-ascend-rejected-directions.json#L15)
- Conditions for a retry and guidance on adapting a precedent. [Casebook procedure, lines 96 and 103](https://github.com/InferMatrixLab/InferRSI/blob/f6d200775d554d08fb73673833611dd6ac02d14b/src/inferrsi/data/skill_library/methods/inference-optimization-casebook/SKILL.md#L96)
