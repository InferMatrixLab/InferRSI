# Small frozen retrieval assessment

- `development.json`: 8 source-reviewed partial-positive queries, visible before the candidate.
- `heldout.json`: 4 independently source-reviewed unseen queries/labels, released only after runtime candidate freeze.
- Reproduce with `tools/evaluate_indexer.py`; issue-scoped gates, exact revisions, raw data and the efficiency/accuracy table live under `evidence/indexer-255-20261029/`.

These are not an exhaustive question bank or complete relevance ground truth. Partial-label Hit@5/MRR@5 measure whether a known positive appears, not full Recall/Precision or an agent's task success. Explicit-ID/resource-budget/no-match/stale-projection contracts are checked separately.

Known label qualifications are retained rather than silently repaired after seeing results: dev02 mixes KV-transfer intent with an AFD hidden-state skill; heldout02 shares a target skill family with dev08. The latter tests unseen natural wording, not family-disjoint generalization. See the evidence's independent label review and per-case table.
