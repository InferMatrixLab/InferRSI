# Negative Diagnostic Knowledge Implementation Plan

**Goal:** Preserve previously rejected directions as scoped diagnostic options.

**Architecture:** Reuse owner-local Case records and the existing explicit
KnowledgeReader/Collect interface. Separate source observations from suggested
revisit checks. No new registry, automatic routing or candidate promotion.

**Tech Stack:** Existing JSON/Markdown case bundles, Python readers and pytest.

## Scope and assumptions

The user's "viewpoint" is interpreted as the preceding request to retain failed
directions for diagnosis. This change covers only directions already recorded
in the latest repository: Qwen B300, Qwen Ascend and Drama3 B300. It does not
implement the separate daily L2C learning proposal.

## Steps and verification

1. Add three case bundles under `skills/inference-optimization-casebook/cases/`.
   Pin source summaries to their exact repository revision; retain original
   campaign verdicts and the distinction between reported and reproduced work.
   Verify every observation against its source and read every bundle through
   KnowledgeReader. Commit the records separately with DCO.
2. Connect these cases to the existing casebook/search procedure and both
   matrices. Document conditional reuse and counter-signals. Verify Collect,
   shared-resource revisions and local links through the existing CPU tests.
   Commit the integration separately with DCO.
3. Independently review both slices, including source applicability and the
   absence of modified frozen evidence. Push to main under the user's direct
   integration authorization, refreshing checks if main changes.

## Decision and limits

Use a conditional prior over experiments: a failed quality gate, missing gain,
resource failure, confounded run and analytical rejection answer different
questions. Prefer the cheapest discriminating check before an expensive retry.
Neither an unchanged symptom nor a reader test establishes the root cause,
universal inapplicability or a new performance result. Missing raw evidence stays
explicit; a case is not an executable policy or a hard blacklist.
