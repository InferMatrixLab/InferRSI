# Trace2Skill evidence ledger

F — [Trace2Skill: Distill Trajectory-Local Lessons into Transferable Agent Skills](https://arxiv.org/abs/2603.25158v5), Ni et al.; v5, 2026-06-04 (v1 2026-03-26). [§2](https://arxiv.org/html/2603.25158v5#S2), [§§3–4](https://arxiv.org/html/2603.25158v5#S3), Appendices A–I. Prior `3d0b52a` is not a verified paper-version match.

## Mechanism contract

- **Objective:** frozen-agent test improvement from disjoint evolution evidence (Eq.1).
- **Assumptions:** labeled traces, inspectable artifacts, reusable target procedure.
- **Variables/constraints:** seed skill, error/success pools, merge breadth, edit applicability. Unexplained failures are excluded (§2.3).
- **Mechanism:** independent diagnoses become hierarchical consolidated edits; reject missing-file and conflicting-range edits (§2.4, Eq.2).
- **Resources:** 128 analysts, merge batch 32; same eight-A100 node; full study ≈20,000 GPU-hours (A; B.1), not per-skill cost.

## Author-reported evidence

| Controlled comparison | Result | Locator |
|---|---|---|
| Spreadsheet parallel / seq-1 / seq-4 | 122B Vrf 65.83/61.83/59.00; ≈3/60/15 min | Table 4 |
| Consolidated / ReasoningBank top-1 | 122B Vrf 69.83/56.00 | Table 5 |
| All-error / BO-selected | Vrf 65.83/69.83; HiTab 43.45/43.38 | Table 6 |
| Human skill / none, 35B | Vrf 9.67/19.00 | Table 1 |

Main spreadsheets: 200 evolution/200 verified test; three seeds. +57.65 WikiTQ points is a specific 35B-author→122B-user creation/error result, not an average.

## P — Interpretation and limits

This is evidence for candidate consolidation, not an unconditional publish-all rule. The default aggregation avoids repeated subset evaluation, but the paper itself shows gains from selection and an unfavorable counter-metric. Independent diagnosis can still share correlated model errors; support counts should trace back to distinct tasks and sources, not merely the number of generated patches.

The latency result is wall time with large concurrency, not token-normalized or dollar-normalized efficiency. Seq-1 remains higher on 35B Soft/Hard in Table 4. Top-1 retrieval is one particular retrieval comparator, and OOD retrieval results were excluded; do not conclude that consolidated skills dominate every retrieval strategy.

The study preloads the known target SKILL.md (I.1). It therefore does not validate catalog discovery, routing, or autonomous skill selection. Treat the human skill's small-model regression as evidence for model/harness-specific suitability checks. The agentic analyst's benefit is also not universal: 122B creation's Avg is 26.02 versus 26.60 for log-only analysis (Table 12), despite better in-distribution scores.

BO uses only 32 validation tasks and at most 15 high-coverage patches (Appendix E). Its search must remain separated from final test claims. No local trajectory was generated or diagnosed in this pack.
