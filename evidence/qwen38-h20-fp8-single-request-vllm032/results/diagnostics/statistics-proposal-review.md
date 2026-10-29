# Proposed statistics: implementation and independent review

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE / NOT ACTIVATED.** No engine patch, GPU run or measured speedup.

The issue-scoped reducer implements the proposed paired-ratio median and
input-cluster bootstrap. Twenty-four synthetic checks pass, including complete
identity ratios, slower-than-margin rejection, uncertainty-only inconclusiveness,
missing/duplicate/wrong records, row-order invariance, token accounting, timeout,
NaN/huge integer/overflow handling and duplicate JSON-key rejection. The exact
reducer identity and sample-index digest are retained in the companion JSON.
These are correctness checks of a proposal, not campaign performance evidence.

Independent review identified finite-value median overflow, huge-integer and
JSON-duplicate hazards in the initial draft; corrected before submission or
any model-performance data. The reviewer reran the twenty-four checks and
additionally checked TPOT/ratio underflow and the inclusive 1800-second boundary.
The final review found no blocking implementation issue. The explicit limitation
is that input-cluster resampling conditions on the same three service repetitions;
it does not estimate restart-level shared variation. The execution plan now
records that limitation and 405504 total generated tokens including warmup.

A local lint invocation first reported one import-order issue in the synthetic
checker; fixed and lint passed. A scaffold-test invocation named a nonexistent
path and collected no tests; the corrected inventory/evidence-path selection
then passed 19 tests. No existing shared validation bar was changed.

Owner statistical/retrieval confirmation, quality sandbox qualification,
source/runtime/command binding, complete freeze and independent acceptance
validation still precede performance search. This reducer cannot activate a
campaign and always emits campaign INCONCLUSIVE.

KnowledgeStore candidate `case.qwen38-statistics-proposal-cand` revision
`sha256:2cc26379c8031c28be93cab1fd305243cc25332a34c4ca6b2ad9f281d6a55124` was written and read back exactly; no library promotion.
