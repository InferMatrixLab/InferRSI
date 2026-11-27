# Knowledge

Knowledge maintains the packaged skill library and provides retrieval of
skills, cases, and records. Apps supplies the reader to callers and workflows.
Benchmark owns assessment of the results those workflows produce.

## Entry points

- [`knowledge_find.py`](knowledge_find.py) exposes `find` for ranked discovery.
- [`knowledge_operations.py`](knowledge_operations.py) exposes
  `KnowledgeReader.collect` for context, `read` for bundles, and `resource` for
  files at a pinned revision.
- [`RankingPolicy`](ranking_policy.py) supplies field weights to Find and
  Collect. For example, pass `ranking_policy=RankingPolicy("trial", {"applicability": 3})`
  to compare results against the default on the same library. Collect records
  its version and effective weights in `retrieval.selection.ranking_policy` when
  it ranks matches or selects skill sections by relevance. Explicit item IDs
  keep caller order even when section selection uses these weights.
  Inspect `contexts` and `context_omissions` to see which material fit the budget.
- [`ranking_replay.py`](ranking_replay.py) binds a Find and delivery with
  `replay_binding` (query, limit, filters, byte budget, frozen rule, scoring version and
  corpus digest) and checks it with `verify_replay`. Only an identical corpus and scoring
  version can report `reproduced`; archival capture verification is a separate check.
- [`knowledge_store.py`](knowledge_store.py) exposes `KnowledgeStore.create` and
  `update` for an authorized writable store. The packaged library is authored
  in the repository.

## Author and use knowledge

Follow the [skill library guide](data/skill_library/README.md) and
[record guide](data/skill_library/records/README.md) for repository contributions.
Resolve ambiguous names with source-qualified references and pin the revision
when reading a resource. Use a record's applicability and evidence when
deciding whether to reuse it.

See [library organization](../../../docs/knowledge-base.md),
[read operations](../../../docs/knowledge-operations.md), and the
[writable store contract](../../../docs/knowledge-store.md). The
[discovery](../../../tests/knowledge/test_knowledge_find.py),
[reader](../../../tests/knowledge/test_knowledge_operations.py), and
[store](../../../tests/knowledge/test_knowledge_store.py) tests cover these interfaces.
