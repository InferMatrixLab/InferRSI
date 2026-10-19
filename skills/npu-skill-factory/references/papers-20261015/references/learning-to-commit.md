# Learning to Commit evidence ledger

F — [Learning to Commit: Generating Organic Pull Requests via Online Repository Memory](https://arxiv.org/abs/2603.26664v1), Li et al.; v1, 2026-03-27, work-in-progress. [Methods](https://arxiv.org/html/2603.26664v1#S3), [experiments](https://arxiv.org/html/2603.26664v1#S4). Prior implementation pin `7e5a1d77` is not independently reconciled with the paper.

## Mechanism contract

- **Objective:** repository-aligned future patches.
- **Assumptions:** chronological expert-reviewed commits; parent snapshots; intent-only queries.
- **Variables/constraints:** cutoff, curriculum, memory CRUD; future diffs excluded from onboarding (§3.1–3.4).
- **Mechanism:** attempt historical task before revealing accepted diff; contrast localization/API/style discrepancies; revise or deprecate memory (Eq.1, Fig.1).
- **Resources:** onboarding attempts/reflection plus full memory at solve time; total tokens, time and memory growth unreported.

## Author-reported evidence

Claude Opus 4.6; one internal RL repository; 24 learning/7 test tasks (§4.1). Table 2 pairs skill/base:

| Condition | File IoU % | Tool calls | Line deviation |
|---|---:|---:|---:|
| seq-all | 80/61 | 56.8/71.9 | .69/1.59 |
| par-bycat | 80/68 | 62.7/62.7 | .62/.88 |
| par-all | 81/72 | 67.7/68.3 | .80/1.06 |
| seq-bycat | 71/71 | 75.0/76.4 | 1.22/1.13 |

Table 3 skill-win % (Claude/Gemini): seq-all 55/58; par-bycat 54/57; par-all 46/54; seq-bycat 26/46. Functional pass rates and explicit API-reuse-rate results are not supplied.

## P — Interpretation and limits

The measured outcomes support a limited repository-onboarding hypothesis, not broad reliability or real maintainer acceptance. Oracle similarity can penalize valid alternate solutions; a smaller patch is not automatically correct. Keep tests, localization, bloat, style, and acceptance as separate outcomes. Only two conditions exceed 50% under both judges in Table 3, so do not repeat the broader prose claim as if every dimension agreed.

Strict temporal separation blocks one known leakage route. Audit synthetic-query generation and benchmark access separately; the cutoff alone does not prove the model never encountered relevant material. Historical conventions also expire. Store when a rule was supported, conflicting later evidence, and a reason to retire it.

The paper moves from 2,738 raw commits to 386 suitable commits while reporting 77.2% suitability; that percentage is not 386/2,738, and the intermediate denominator is not clear in the inspected report. Do not reuse it as the raw-history yield. The four curricula are comparisons, but neither an oracle-free matched ablation nor a multi-repository generalization result is reported. For InferRSI, propose scoped memory updates rather than treating history mining as validated skill promotion.
