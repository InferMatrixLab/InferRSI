> Historical supplier amendment proposal, 2026-10-15. This is editing context, not a deployed task procedure or an execution grant. The owning SKILL.md records the reconciled amendment.

# Candidate bounded update: optimization-search-policy

Status: candidate. empirical_validation: not_run. **All instructions in this file are P.** Target is an existing skill name recorded in the uploaded Reference Matrix; this is a proposed content delta, not an applied patch or assertion about its current text. Consult [source notes](../references/source-notes.md) for F evidence and exact limits.

## Trigger and required evidence

Use when optimization iterations repeatedly revisit failed hypotheses, accept noisy gains, accumulate costly mechanisms, or propose changing an agent/controller based only on its own search score. Obtain the objective, editable component, immutable interfaces/evaluator, candidate diff, task split, baseline window, score distribution, token/execution costs, history visibility and selection protocol. Mark missing evidence rather than inventing thresholds.

## Proposed decision additions

1. Name the adaptation unit: action choice, memory item, case, skill, search policy, harness, or improver. Explain why a smaller unit is insufficient. An experiment's failure alone does not justify rewriting the framework.
2. Record a testable hypothesis and its edits together. If multiple mechanisms change, retain candidate-level attribution; do not label all individual mechanisms proven or falsified. Distinguish execution failure, valid regression, noisy tie and a candidate that merely lost selection.
3. Separate proposal generation from acceptance. A benchmark-specific critic or code review can reject explicit leakage but cannot establish absence of subtle overfitting. Retain a baseline and untouched evaluation evidence where the proposed claim requires it.
4. For noisy scores, request a calibrated tolerance and an explicit cost allowance. Keep the best historical reference visible to prevent a chain of small tolerated regressions. Treat RRSI's numerical schedules and novelty bonus as paper choices, not defaults or permission to accept a weak candidate.
5. If history supports replay, declare the legal action interface, observed-prefix boundary and recorded continuation support. Label a result off-policy replay. A policy accessing future outcomes, changing the evaluator, or asking for unrecorded branches fails that replay claim.
6. For a harness improvement, compare the full cost appropriate to the objective. Character-count compression, policy tokens, discovery calls, GPU time and dollars are different measures. Preserve gains that were obtained at extra cost as trade-offs.
7. Before proposing a new improver, separate the task-level comparison from the improver-level experiment. An inconclusive improver comparison remains inconclusive; do not promote from a plot's apparently faster early rise.

## Benefit, costs and counter-signals

Intended benefit: fewer repeated low-information trials and clearer assignment of feedback to a bounded artifact. Cost: additional evidence bookkeeping and, if later authorized, repeated/held-out evaluation. Counter-signals include unstable evaluator definitions, unseen current skill text, unrepresentative replay support, conflicting checkpoint rankings, cheap-but-worse outcomes, and estimates whose overhead dominates the workload. Preserve a no-change decision when evidence cannot distinguish candidates.

## Verification idea and escalation

Propose only a future bounded comparison with fixed model/interfaces, explicit score/cost denominator, leakage controls, observation boundary and abort criteria. For replay, test unseen outcomes separately; for an improver, use repeated matched outer runs rather than executor benchmarks. No such run was performed here.

Escalate if the request needs live harness changes, evaluator repair, action/logit interception, new compute spending, or access to unavailable current artifacts. An evaluator bug can be a separate case; repairing it must not silently change the objective during a comparison. Do not add automatic framework machinery, global bans from contextual rejections, or a new primary matrix.
