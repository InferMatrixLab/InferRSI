# Offline skill PR summary example

Fixed-output pipeline control, not a model measurement or a skill-efficacy claim.
Revision/hash values below are placeholders for the temporary Git fixture.

PR plan: `<canonical-pr-plan-sha256>`

Base: `<fixture-base-sha>` · Head: `<fixture-head-sha>`

Comparison: **old/new** (`addition` uses **absent/new**)

Client: **FixedOutputClient**, model label `offline-fixture`, effort `test`

| Pair outcome | Count |
| --- | ---: |
| fix | 1 |
| regression | 1 |
| unchanged_correct | 1 |
| unchanged_incorrect | 1 |
| inconclusive | 1 |
| missing_pair | 1 |

One unrelated source change remains **uncovered** and never counts as a pass.
The deliberately incorrect candidate is graded as a regression; malformed JSON
is inconclusive. The final pair is missing after the observed-token stop.

Budget: 12 scheduled calls, one repeat, 60 seconds/trial, 900 seconds/comparison,
observed-token stop threshold 200. The fixed client records **10 calls**; no real
model calls occur. Monetary cost is unknown. Publication retry updates the same
single simulated comment with **zero additional evaluation calls**.

The [offline integration control](../../../tests/test_skill_eval_pr.py) verifies
these outcomes, including addition/update, lost publication response, stale
heads and retained evidence validation. The
[demo command](../../../tests/fixtures/skill_eval_pr_demo.py) saves the complete
plan, results, regenerated reports and simulated summary for local inspection.
Simulated GitHub links are not live evidence. Real Actions evidence is requested
for 30 days; after expiry the comment alone cannot substantiate its outcomes.
