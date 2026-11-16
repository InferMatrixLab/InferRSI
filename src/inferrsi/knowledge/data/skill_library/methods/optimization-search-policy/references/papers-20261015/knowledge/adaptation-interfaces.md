# Candidate knowledge records: adaptation interfaces

All records are candidate and empirically unvalidated. F facts are supported in [source notes](../references/source-notes.md); P entries are proposed integration constraints. These records explain when a method can be considered; they do not implement it.

## K1 — replay controller eligibility

- **F source:** Dream-RSI v2 §3/Eq.1 and Appendix D.2/Listing2.
- **F required interface:** root/frontier actions; revealed observations; fixed evaluator; replayable parent–child outcomes; bounded workers; prefix-safe history; explicit grid plan within hard caps. The paper's solve/plan_grid signatures belong to its own implementation contract.
- **F benefit/cost:** many supported policy comparisons can reuse recorded outcomes; policy-development cost and unseen online outcomes remain outside a cheap-replay claim.
- **P applicability:** retain as a knowledge record until an actual supplied system exposes equivalent semantics. A plain transcript with no replayable state or action frontier is insufficient.
- **P counter-signal/failure:** reordered observations leak future information; an evaluator changed across histories; unsupported branches receive fabricated rewards; replay score replaces fresh evidence. Escalate any of these before recommending controller adaptation.
- **P verification idea:** audit support/visibility and later compare a candidate on fresh authorized trajectories. Never infer such a comparison was performed by this pack.

## K2 — executor versus improver evidence

- **F source:** AIDE² v1 §§2.1,3.3,3.6; Appendix A Tables1–2.
- **F required interface:** fixed-budget inner tasks return solutions; private grading produces aggregate feedback; outer candidate selection is specified separately. Public/private separation is not the same as an outer-held-out benchmark.
- **F counter-evidence:** stronger task checkpoints are not uniformly stronger across domains; the 3-seed/arm ignition experiment is inconclusive about improver superiority.
- **P operational rule:** store executor and improver claims as separate entries within the existing evidence record. Keep score definitions and budget types attached. Do not replace an improver because its offspring is a better executor.
- **P verification idea:** a future improver comparison needs matched initial incumbents, outer budgets, seeds and independent endpoint evaluation. More expensive nesting must be explicitly approved.

## K3 — advantage-based action adaptation eligibility

- **F source:** JitRL v4 §§4–5, Appendix C/F/J.
- **F required interface:** normalized state/action identities; action candidates including eligible retrieved actions; measurable or approximated prior action scores; return-bearing memory; valid-action checks; reward evaluator. Frozen weights are compatible with adaptation, but raw logits access is not universally available.
- **F benefit/cost:** no gradient update; additional retrieval, scoring and evaluator work. Consistency depends on coverage, action frequency, regularity and slow drift; it is not guaranteed by merely retaining trajectories.
- **P operational rule:** record which interface is actually available. Verbalized confidence is not a raw-logit guarantee. If only textual skill loading exists, preserve this as knowledge rather than advertise executable JitRL capability.
- **P counter-signal/failure:** state aliasing, stale rewards, incompatible actions, empty-neighborhood behavior not specified by a current implementation, or approximated priors with unknown calibration. Require a defined fallback rather than transcribing the paper's empty-memory pseudocode divisions.
- **P verification idea:** later isolate retrieval from reranking under identical action support and feedback; measure quality plus complete overhead. Current InferRSI support and efficacy remain unknown.
