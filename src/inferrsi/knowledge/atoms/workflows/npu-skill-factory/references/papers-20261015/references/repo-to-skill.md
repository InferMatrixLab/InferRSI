# Repo-To-Skill evidence ledger

F — [Repo-To-Skill: Distilling GitHub Repositories Into AI4AI Skills](https://arxiv.org/abs/2609.02749v1), Chen et al.; v1, 2026-09-02. Read [§§2–5](https://arxiv.org/html/2609.02749v1#S2), [Appendix A](https://arxiv.org/html/2609.02749v1#A1). Prior implementation pin `ac3fe1af` is carried context, not matched to this paper version.

## Mechanism contract

- **Objective:** reusable operational context with unchanged backbone/harness (§2, Eqs.1–4).
- **Assumptions:** inspectable evidence, scoped capabilities, relevant future tasks, trustworthy checks.
- **Variables/constraints:** source/task anchor; capabilities; evidence subset; graph/interfaces; verification record (Eqs.5–8). Skill construction and evaluation are separated.
- **Mechanism:** capability-specific evidence becomes procedures with references, optional wrappers, and explicit unresolved gaps (§3; A.1). Paper modules undergo isolated checks and bounded recovery without reopening the source implementation (A.2.2).
- **Resource trade-off:** construction is paid before reuse; downstream context is selective. Library construction allocation ≈$40/repository; MLE construction ≤24 GPU-hours/task is additional to ≤24 GPU-hours/task for running (Table 5).

## Author-reported evidence

| Setting; controlled comparator | Without → with skill | Locator |
|---|---|---|
| GPT-5.5/Codex, MLE 75 tasks; medal % | 31.11±2.22 → 72.89±1.18; three runs, SEM | Table 1 |
| PaperBench 20; replication % | 29.45 → 39.59 | Table 2 |
| FrontierCS 188; score / tokens per task | 70.63 / 2.46M → 77.14 / 4.47M | Table 3 |
| PassNet 200; AS / correctness / Fast_1 | 1.343 / 81.35% / 28.48% → 1.5313 / 90.76% / 26.72% | Table 4 |

F — PassNet metric denominators (§5.1): at tolerance t = −5, correctness is the fraction of subgraphs matching eager outputs; Fast_1 is the share of numerically correct subgraphs at least as fast as eager. AS aggregates rectified speedups across tolerance levels t ∈ [−10, 4] under the benchmark aggregation protocol; it is not a rate with the Fast_1 denominator.

## P — Interpretation and limits

The public repository count and the evaluated task/paper-specific collections must not be conflated. No result here establishes that every generated repository skill improves an agent. Same downstream budget does not mean equal total construction-plus-use cost. FrontierCS's larger token consumption makes an unconditional “skills save compute” rule indefensible. PassNet's aggregate and correctness gains coexist with a worse Fast_1 metric; select a metric contract before deciding which revision is preferable.

No component-isolating ablation establishes a universal benefit for scripts, graph depth, routing, or verification itself. PaperBench's two negative tasks and the PassNet overconservative-rule case deserve preserved counterexamples, not deletion from a positive summary. The proposed factory change is to preserve verification type, scope and cost, with source-local exceptions and a fallback when guidance is poorly matched. These are proposed safeguards, not local results.
