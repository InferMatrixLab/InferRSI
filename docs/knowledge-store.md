# Authorized local Create / Update

This K2 write slice builds on the [normalized read contract](knowledge-operations.md).
It adds one backend: SQLite in an **existing, explicitly authorized local directory**.
Create and Update operate only on **store-owned candidate bundles**. Package and
checkout content stay read-only; they are never written, and their IDs cannot be
reused in the store. Amending repository-owned content follows the normal scoped
PR path.

```python
from pathlib import Path
from inferrsi.knowledge_operations import Bundle, KnowledgeReader
from inferrsi.knowledge_store import KnowledgeStore

skills = Path("skills")
store = KnowledgeStore(Path("/authorized/local/knowledge-workspace"), skill_root=skills)
source = KnowledgeReader(skill_root=skills).read("calibrate-serving-simulation")
draft = Bundle(
    {**source.metadata, "id": "calibrate-serving-simulation-local", "state": "candidate",
     "derived_from": [{"ref": "checkout:calibrate-serving-simulation",
                       "revision": source.revision}]},
    dict(source.content), dict(source.dependencies),
)
revision = store.create(draft)
# Supply a complete amended Bundle, preserving source attribution and resources:
# next_revision = store.update(amended, expected=revision,
#                              reason="Clarify applicability", evidence=[source_pointer])
old = store.read("calibrate-serving-simulation-local", revision=revision)
collected = store.collect(ids=["store:calibrate-serving-simulation-local"],
                          revisions={"store:calibrate-serving-simulation-local": revision},
                          material=True)
```

`skill_root` is required: pass the checkout skills root whose IDs must be reserved,
or `None` to declare package-only use. `store.reader()` / `store.collect` combine
package, checkout and store items with qualified `store:<id>` refs. An ID owned by
the store and a read-only adapter is reported as ambiguous, never shadowed.

## Create and Update

- Create registers a supplied **candidate** and rejects duplicate identity. It
  rejects an ID owned by package or checkout content. An adaptation of existing
  content uses a distinct ID and records `derived_from` entries with a qualified
  `ref` and the source content revision (or `null` if unknown).
- Create does not relabel imported content or generate guidance. Update requires
  the expected current revision, a reason and an explicit evidence list (empty
  means none supplied). It publishes a successor without changing the content's
  state; promotion is not implemented.
- An Update whose bundle reproduces a retained revision is an explicit conflict.
  Existing history preserves old metadata, provenance, resources, parent revision,
  reason and evidence even if a later interpretation changes.
- If a read-only adapter later gains a store item's ID, reads report ambiguity and
  further Updates fail with a collision until the owners resolve it.

## Writer and publication guarantees

- Scope: cooperating processes/threads using this API on one local SQLite file;
  no network-filesystem, distributed-store or hostile filesystem-owner guarantee.
- The workspace must already exist and lie outside the installed `inferrsi`
  package, the checkout containing `skill_root` and, for a source or editable
  install, the checkout containing the package (these hold evidence and both
  matrices). That package checkout is the nearest ancestor holding both
  `pyproject.toml` and `.git`; with `skill_root=None` it is the only checkout
  guarded, so a checkout lacking either marker is not protected. The entrypoint of a stored bundle must be UTF-8 text. Workspace and database symlinks are rejected. No destination
  directory is guessed or automatically created; the caller controls permissions.
- SQLite `BEGIN IMMEDIATE` serializes writers before duplicate/stale checks.
  Resources, revision metadata and the current pointer commit in one transaction.
  A database error rolls the whole transaction back; partial usable bundles are
  never published. A five-second lock timeout raises an explicit SQLite error.
- Content/resource/dependency validation runs before writing. Dependencies are
  included as bytes and checked against declared digests. Old reads load retained
  bytes and verify their complete bundle identity; they never fall through to a
  current checkout. No external mutable dependency lookup occurs during reads.
- Resource keys cannot be absolute paths or traversal paths; they are database
  keys, never filesystem write destinations.
- Runtime operations write only the store database. They do not edit adapter
  sources, raw evidence or either matrix, and a store candidate is not repository
  coverage until exported through a reviewed repository change.
- Normal SQLite local-filesystem transaction guarantees apply. This implementation
  does not claim tested power-loss durability, malicious tamper resistance or an
  automatic recovery campaign. Integrity mismatches fail visibly.

Tests use real bundles, SQLite transactions, competing writer connections and a
real rejecting database trigger to prove rollback after an insert starts. They do
not use hardware, synthetic performance claims or a fake storage implementation.
