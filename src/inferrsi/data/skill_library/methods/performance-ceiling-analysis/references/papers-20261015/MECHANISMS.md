# Pack A: model, shortlist, measure, redirect

Status: **candidate / not_run**. Four original papers; author-reported evidence, not local measurements. Every operational rule below is **P**; **F** records the paper's actual methods/evidence in the linked source audits.

## Main answer

Model enough to reject impossible choices and cheaply compare plausible ones; use empirical predictions to shortlist, matched measurements to select, and artifact/correctness evidence to accept. When residuals, bottleneck ownership or workload regimes change, redirect the experiments instead of repeating the same recipe.

- **Vidur → calibrated shortlist.** Separate token, sequence and communication dependencies; model stateful queueing rather than only adding kernel means. Retain joint SLO and total cost constraints. Predicted ranks require matching calibration and become unreliable near an unvalidated capacity boundary. [V1–V3](references/vidur.md)
- **InferenceBench → controlled search and final-state reliability.** Count actual distinct trials, preserve an incumbent, keep quick probes separate from held-out full evaluation, and audit the timing path independently of quality. Fixed-budget engine comparisons, best-seen/final discrepancies and structured/warm-start ablations diagnose different failures. [I1–I3](references/inferencebench.md)
- **FlashVector → layer-aware redirection.** A kernel improvement can expose host preparation or configuration bottlenecks. Rank impact against measured uncertainty, preserve semantic/lifetime conditions, verify globally, and retune after code changes. Local and full-stack denominators remain separate. [F1–F4](references/flashvector.md)
- **Agentic Kernel Optimization → regime dispatch and search correction.** Profiler/history-driven candidates, exactness gates and semantic shortcuts can matter more than endless local parameter changes. Cumulative trajectories are not controlled ablations; structural future directions stay unmeasured. [M1–M8](references/agentic-kernel.md)

## What this adds to existing InferRSI intelligence

The existing analytical/empirical/Amdahl ceiling hierarchy remains intact. This pack adds a **prediction calibration boundary**, **final-artifact preservation evidence**, **measurement-integrity failure cases**, and **cross-layer/regime redirection rules**. It does not fill missing hardware measurement cells. [Prior overlap and merge targets](references/prior-coverage.md)

## Proposed candidate procedure

1. Freeze objective, absolute constraints, semantics, resource/cost denominator, workload and current-stack identity.
2. Record conditional physical bounds and observed attainable envelopes separately from a simulator prediction or heuristic rank.
3. Shortlist distinct feasible mechanism families with predicted direction, uncertainty, discriminating metric and bounded trial cost.
4. Measure matched trials, independently gate quality/integrity, and retain invalid/inconclusive outcomes rather than hiding them.
5. Redirect when measured evidence falsifies the model or exposes a different owner/regime. A failed implementation does not automatically falsify an optimization idea.
6. Restore and verify the best valid final artifact under the full target workload. Only then promote an empirical claim, and only within its measured scope.

[Evidence supplement](knowledge/bounds-predictions-and-decisions.md) · [Six candidate cases](cases/decision-cases.md) · [Exact readset](READSET.md)

## Non-comparable quantities

Do not order these papers by headline multipliers: Vidur reports simulator latency error and historical search cost projections; InferenceBench reports failure-aware speedup against naïve PyTorch under finite agent budgets; FlashVector reports component and production-pod effects; kernel campaigns report PyTorch-relative kernel aggregates and a separate contest FlashInfer-relative score. Hardware, workload, quality contract, budget, baseline and denominator all differ.
