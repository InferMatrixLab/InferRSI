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
