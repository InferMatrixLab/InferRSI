# Qwen3.8 FP8 single-request campaign — diagnostic takeover

Governing acceptance: https://github.com/InferMatrixLab/InferRSI/issues/67
Status: **INCONCLUSIVE. No activated acceptance freeze or parity claim.**

This isolated checkout retains the 2026-10-22/23 Codex takeover diagnostics and
prospective plan. Earlier readiness drafts and DSH evidence remain in their
original stores; this directory does not replace or retrospectively freeze them.

- `plan/diagnostics/fp8-graph-takeover.md`: bounded diagnosis and repair contrast.
- `plan/freeze-proposal.md`: owner-review statistical/retrieval/budget proposal.
- `results/diagnostics/`: original and repaired numerical traces, summaries and
  source digests. Trace data contains no service timing claims.
- `patch/diagnostics/`: separate configured-backend and model-prefill repairs.
- `validator/diagnostics/`: diagnostic observer; not the final acceptance validator.

Publication follow-up: `results/diagnostics/http-impact.md` binds the clean
main-based engine commits to actual HTTP timing and token evidence. The repaired
Graph matches eager for all six short requests; original main differs on two.
The exact publication-head CPU suite has one inherited failure, reproduced on
unmodified main; see the report rather than transferring earlier green totals.
The subsequent accounting adapter and failed long-output boundary check are
recorded in `results/diagnostics/benchmark-http-impact.md`; full model readiness
remains outstanding.

The HTTP follow-up consumed 0.04 GPU-hours of the owner-approved 44 GPU-hour
phased ceiling. It does not activate the statistical/retrieval freeze proposal.
KnowledgeStore record `store:case.qwen38-publication-http-prefill-cand`, revision
`sha256:83c7df1d6debb6e2797a96fd30d6a8270d842d6cf97428610821b3d78a964c32`,
retains positive, negative and inconclusive observations with verified readback.

Current local engine implementation has two independently bounded commits: the
configured FP8 backend is validated/reported, and initial prefill preserves its
original K/V operands with reserved Graph storage. GPU repair evidence applies
to the model-only diff. CPU regressions also cover the combined source.

The prefill discrepancy is repaired for all three diagnostic cases. Replay
matches fixed-capacity eager at all 48 steps, but compact/buffered decode logits
still differ in 13/48 steps despite identical greedy choices. Full service,
long-context, quality and performance qualification remain outstanding.

Knowledge candidates were recorded using InferRSI KnowledgeStore, with retained
revisions and verified readback. They are not promoted library coverage. Raw
operational logs and private device identities remain in controlled task storage.

Further bounded diagnostics retain the official-client accounting adapter,
failed long-output request, readiness-file preflight race and separate Graph
demotion fix. See `plan/diagnostics/benchmark-http.md` and
`plan/diagnostics/graph-demotion.md`. Original observers/results are preserved;
versioned successors do not retroactively change their verdicts.

The completed10-request boundary repair and its remaining numerical differences
are recorded in `results/diagnostics/graph-demotion-impact.md`. Engine PR9 is
merged; full Graph/eager sequences agree on3/5 pairs and campaign acceptance
remains INCONCLUSIVE. Readiness allocation use is839 GPU-seconds.
