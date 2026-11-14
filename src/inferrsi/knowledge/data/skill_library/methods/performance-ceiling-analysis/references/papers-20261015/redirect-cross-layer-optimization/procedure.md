# Redirect cross-layer optimization

Use when a local kernel improvement does not improve serving, or a previous improvement changes the dominant cost. This is a proposed extension to `performance-ceiling-analysis`, `host-overhead-profiling`, `host-overhead-optimization` and `inference-optimization-casebook`. It adds no profiler installation, framework or automated production loop.

Sources: [FlashVector](references/source-notes.md), [Agentic Kernel Optimization](references/source-notes.md), [bounds and predictions](references/source-notes.md).

## Procedure (P)

1. Fix the service objective, request semantics, absolute SLO, resource budget and correctness type. Snapshot representative baseline inputs/outputs and configuration identity. Keep request-level and candidate-row batch counts distinct.
2. Attribute exposed time to actual owners: kernel, graph/dispatch, server serialization, feature materialization/assembly, queue/batch scheduling. Do not add overlapping time shares or infer an owner merely from a tool's stack label.
3. Estimate conditional whole-system headroom, then rank hypotheses by plausible service impact, uncertainty and experiment cost. FlashVector's time-share×expected-gain score is a heuristic. Random layer sampling is its reported design, not a requirement or proven optimum.
4. If the potential removable share cannot beat locally measured uncertainty, redirect or explicitly justify more samples. Repeated measurements must test drift/correlation; never copy the paper's±6% or1/sqrt(k) behavior as a universal noise law.
5. Choose semantic transformations from evidence: expose fusion-hidden operations; reuse invariant work; eliminate needless host materialization; preallocate assembly; or choose a regime-specific kernel family. For views/shared memory, require lifetime/immutability/fallback evidence. For fusion, record register/shared-memory/occupancy trade-offs.
6. Validate the exact rewrite contract locally. Require full-stack replay under identical resources and workload before service-level acceptance. The proposed default acceptance is correctness plus a reproducible E2E improvement without any SLO regression; weaker non-regression-only acceptance must be separately justified by the user's goal.
7. Re-profile accepted changes and reopen configuration tuning. Vary instance count and batching under the same resource and SLO contract; more concurrency is not inherently better. Verify each selected row's measured inequalities.
8. Store model/workload/hardware-scoped accepted and rejected hypotheses. Refresh only when the approved task warrants it; paper descriptions of always-on behavior do not authorize a recurring task.

## Output and stop

Deliver before/after bottleneck ownership, candidate mechanism and trade-offs, correctness contract, component versus full-stack measurements, noise assumptions, SLO arithmetic, resource denominator and next redirected hypothesis. Stop on unresolved ownership, missing semantic/lifetime guarantees, sub-noise gain, unmeasured integration effects or unauthorized deployment.

Do not convert FlashVector's30× serialization-step result into a30× service claim. Table4 ModelB has p99 above its stated SLO; it is a counterexample to accepting a caption without arithmetic.

## Resource contract

This procedure and its local `references/source-notes.md` are sufficient for selective consumption. The rest of Pack A supplies optional comparisons and integration notes; no parent-folder file is required to interpret the procedure or its source limits. Existing InferRSI skill names above are reconciliation targets, not runtime dependencies.
