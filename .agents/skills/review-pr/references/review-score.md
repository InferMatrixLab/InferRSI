# Advisory PR Review Score

Use this score on request after assessing the reviewed revision. Base each
rating on the pinned diff and evidence. Apply the existing PR review verdict
and campaign verdict rules independently of the score.

| Dimension | Weight | What to assess |
| --- | ---: | --- |
| Scope and intent | 15 | Governing Issue, accepted scope, hypothesis or requested behavior, and the fit between the diff and the delivery slice. |
| Correctness and safety | 25 | Architecture ownership, public contracts, failure handling, cleanup, and the correctness of any changed evaluator or validator. |
| Validation | 20 | Focused tests, relevant CI, and replay or verification of the affected artifacts. |
| Claim evidence | 30 | Frozen gates, source and environment pins, trial index, measured outputs, and a verdict supported by the bundle. Use the [evidence rules](../../../../docs/contributing.md#evidence-and-claims). |
| Simplicity | 10 | Focused changes, reuse of the owning API and validator, and avoidable duplication, state or explanatory comments. |

Choose the highest rating supported by the evidence for each applicable dimension.

- **3** — the applicable checks are supported by matching evidence.
- **2** — the main checks are supported, with a bounded gap.
- **1** — some checks are supported, with a material gap or inconsistency.
- **0** — the dimension lacks usable evidence or a material contract violation
  is confirmed.

Use `N/A` when a dimension is outside the change's scope. For example, claim
evidence can be `N/A` for a scaffold-only change without a campaign claim.
Count each gap in its primary dimension. Identify the source of each rating,
including the difference between recorded experiment results and checks you ran.

The formula is `100 * sum(weight * rating) / (3 * sum(applicable weights))`.
Round to the nearest integer, with halves up. Withhold the total
if the snapshot is stale or a material portion of the diff could not be
reviewed. Report the base and head, total, dimension ratings with evidence,
and the highest-priority remaining action. Use the existing conversation and
formal review rules for delivery.
