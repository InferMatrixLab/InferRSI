# Activated 8K search protocol

Governing acceptance: [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67#issuecomment-6359192342).
The owner approved 8K-only retrieval and formal performance, the statistical
rule, and the 44 GPU-hour phased ceiling. The root activation record was frozen
before submitting candidate job 2163. Campaign verdict remains **INCONCLUSIVE**.

The single new model change is merged FP8 projections in engine PR16. Baseline
and candidate sources are pinned in the Issue and activation record. Candidate
component, complete quality/scorer/executor binding, approved statistics,
raw-to-statistics adapter and independent review are content-locked. The copied
performance binding files are the exact reviewed private execution bytes.
Quality collection files here are exact source copies; host-specific wrappers,
full dataset/model/runtime identities and raw model outputs remain in controlled
storage. Their digests are retained in the root and component locks. Private
raw archives are not available from this public checkout.

Sixteen CPU controls exercise the actual performance-binding logic with a mocked
raw audit; they are not GPU or SSE validation. The separate actual baseline run
2140 was independently replayed through the unchanged SSE auditor. Initial
binding review findings (ambiguous terminal fields, missing actual HTTP Graph
and module-source checks, incomplete per-operator checks) were fixed before
freeze. Wrong metric prose was corrected to TTFT/TPOT. No gate was relaxed.

Quality qualification has a narrow executor scope. The original failed canonical
pilot, successful isolation/export/capacity observations and official assertion
classification remain retained. The production adapter reuses unchanged runtime
and supervision with independent source/consumer review; its first actual model
export still requires successful terminal and postflight sealing. No canonical
all-pass threshold was added, and this is not a model-quality PASS.

Candidate job 2163 has a 3600 GPU-second search ceiling. Baseline quality job
2157 has a separate 9000 GPU-second reservation. These are running allocations,
not completed outcomes. No retry or budget transfer is implied. Complete quality
and retrieval evidence is required alongside performance for final acceptance.

The production-binding observation and candidate-review records retain their
original pre-activation wording (including pending review or unexecuted status).
They are historical source-review snapshots. The later activation.json and its
prospective Issue comment define current execution authorization; snapshots are
not rewritten to imply they observed subsequent execution. The standalone binder
CPU tests require the original candidate component directory supplied through
PERFORMANCE_COMPONENT_DIR; that private component is not included here.

KnowledgeStore search-freeze record: store:case.qwen38-8k-search-freeze-cand,
revision sha256:82267a195a48c2dc0616b05eb512938830141c85edf9fadf81f39a6dea27ecaf,
with verified readback and retained preparation failures.
