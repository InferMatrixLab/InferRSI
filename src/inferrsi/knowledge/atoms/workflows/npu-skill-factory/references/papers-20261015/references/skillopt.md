# SkillOpt evidence ledger

F — [SkillOpt: Executive Strategy for Self-Evolving Agent Skills](https://arxiv.org/abs/2605.23904v2), Yang et al.; v2, 2026-05-25 (v1 2026-05-22). [§3](https://arxiv.org/html/2605.23904v2#S3), [§4](https://arxiv.org/html/2605.23904v2#S4), Appendices A–C, Algorithm 1. Prior `343db229` is not independently reconciled.

## Mechanism contract

- **Objective:** select a compact skill on selection data; report untouched-test performance (Eqs.1–3).
- **Assumptions:** reliable scalar feedback; frozen target/harness; independent splits.
- **Variables/constraints:** edit budget/schedule, rollout/reflection batches, current/best skill, rejected buffer, protected slow region, optimizer-only memory.
- **Mechanism:** ranked localized edits; strict selection improvement, ties rejected; epoch-level comparisons separately gated (§3.2–3.6).

## Author-reported evidence

| Measurement | Values | Locator |
|---|---|---|
| GPT-5.5 Spreadsheet, no-skill / strongest baseline / SkillOpt | 41.8 / 73.6 GEPA / 80.7 | Table 1 |
| Default / no edit budget; SearchQA, Spreadsheet, LiveMath | 87.1,77.5,61.3 / 84.6,75.7,57.3 | Table 3 |
| No rejected buffer | 85.5,72.9,58.9 | Table 3 |
| No meta or slow update | 86.3,55.0,59.7 | Table 3 |

Table 6: 379–1,995 final tokens; 1–4 accepted updates. Training tokens: SearchQA 213.8M; Spreadsheet 21.4M; OfficeQA 20.8M; DocVQA 188.2M; LiveMath 23.2M; ALFWorld 59.3M. No optimizer calls at deployment.

## P — Interpretation and limits

A strict scalar gate controls acceptance; it does not prove that every important behavior is preserved. Add an explicit regression set and task contract before translating that gate into an operational policy. A single append operation can add a large instruction block, so counting edits is not a semantic or token-distance bound. Keep proposal size and changed behavior inspectable too. The optimizer's private learning history should not automatically become instructions for the deployed agent.

Preserve these reporting uncertainties:
- Table 2(a) states a 4:1:5 train/selection/test split; Appendix C's ablation paragraph states 2:1:7. Do not silently select one.
- Table 6 cost/point values (37.9M, .6M, 1.1M, 46.4M, 3.6M, 15.9M) do not directly reproduce Table 1 no-skill gains from their total tokens. Treat the gain denominator/run identity as unresolved.
- Table 2's learning-rate sweep and Table 3's default row differ. The headline results are not all a single default-config run.
- No matched numerical gate-off row or repeated-seed uncertainty is supplied in the inspected result tables. A strong narrative claim about gating is not that missing ablation.

The native verifiers and scorer-specific adaptations are useful only within their task contract. For example, a benchmark favoring static spreadsheet values does not authorize replacing formulas when a real user requires them. Training cost may be unattractive for one-off work. These are limits on transfer, not evidence that the method fails generally.
