# A decision round with local knowledge

Start with the [directory](index.md) and the primary task. Identify the decision that would change the next experiment. Record the original wording, target device and software, sourced observations, previous attempts, unanswered questions and a concrete next action.

Run the TTS pilot from the repository root:

```sh
inferrsi knowledge round docs/reviews/knowledge-retrieval/pilots/tts-regression.json
```

The [TTS request](../../../reviews/knowledge-retrieval/pilots/tts-regression.json) starts with the reported symptom and follows up with the terms for audio events and chunk gaps. Its [review](../../../reviews/knowledge-retrieval/pilots/tts-regression.md) covers two independent questions. The [migration request](../../../reviews/knowledge-retrieval/pilots/version-migration.json) and [review](../../../reviews/knowledge-retrieval/pilots/version-migration.md) distinguish the documented release scope from a local graph replay.

## Plan and select

Supply `task`, a positive `round`, `decision`, original `query`, nonempty `questions` and `next_action`. Add `environment`, `signals` (each has an observation and source), `tried` and `missing_measurements` when available. Each `queries[]` entry names a query. The first preserves the user's wording. Defaults are two distinct queries, five hits per query and 65,536 delivered UTF-8 bytes across all sources. External channels are closed.

To explore a new query, omit its selections and inspect `attempts[].listed`, including matched terms, applicability and limitations. Choose a returned `material_ref`, state which declared question it serves, give a reason and choose `method` or `conclusion`. Use an explicit revision for repeatable review. The default resource is the original body. For another resource use its canonical bundle path. A standalone replay can include the selections from an earlier inspection.

For an interactive caller, `inferrsi.apps.workflows.decision_round.decision_round(reader, request, select=choose, assess=review)` calls `choose(query, listed, answers)` after each Find. Return a list of selections or an empty list. The optional `review(selection, resource)` gets the delivered text and may return a quote, claim, applicability verdict and boolean adoption decision. A JSON request may supply the same assessment for fixed-input replay. Find ranking, reading and agent assessment are visible separately.

## Read and stop

The trace carries exact ref, revision, resource path, delivered text, byte count and SHA-256. Reads use the native reader and page within the shared byte limit. Repeated canonical resource keys reuse the first delivery. A citation must occur verbatim in that delivered text. The caller judges applicability as `match`, `analogue`, `unknown` or `conflict`; a matching substring establishes only that the quotation was delivered. Omitted or rejected citations leave the question unanswered.

Inspect `retrieval_stop`, `stop`, individual selection statuses and `unanswered`. A missing target observation yields `awaiting_measurement` with the stated measurement and next action. Reopen with a new round and the resulting trace, using the new stage, observed version or error to refine the search. A duplicate query is skipped. Unavailable pins are retained as failures for review.

## Campaign evidence

Pass `--session DIR` to use the campaign's native scoped Find and Read. For managed sessions the round must match the current round and the frozen plan must permit knowledge. The trace holds each search receipt and each delivered page receipt. The stored read capture contains the search path and decision round. Cite adopted read receipts when submitting the candidate with `--knowledge-ref`; the managed round observation records the associated contexts. Manual campaigns retain captures with the caller's round number. Register them in the manual iteration using the [campaign trace workflow](../knowledge-retrieval-trace.md#connect-a-new-round).

## Rebuild the directory

From an editable installation of the same checkout, run `python tools/build_knowledge_navigation.py`. Run it with `--check` to verify byte-for-byte reproducibility. Inspect the [inventory](../../../reviews/knowledge-retrieval/inventory.json) for CLI read arguments and the [gap report](../../../reviews/knowledge-retrieval/gaps.md) for missing or incomparable fields. The [Qwen Image benchmark](../../../reviews/knowledge-retrieval/qwen-image/README.md) traces a concrete selection through image generation and comparison.
