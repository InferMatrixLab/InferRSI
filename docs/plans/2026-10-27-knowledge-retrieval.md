# Knowledge retrieval implementation plan

**Goal:** Reduce repeated work in `Bundle.manifest()` while retaining the same
validated manifest, revision and retrieval results.

**Architecture:** Reuse resource digests and validated content paths within one
manifest call. `Bundle.metadata`, `Bundle.content` and `Bundle.dependencies`
remain mutable, so no digest or manifest survives that call. Keep the existing
package snapshot, checkout and store ownership boundaries.

**Scope:** `src/inferrsi/knowledge_operations.py`, focused regression tests in
`tests/test_bundle_manifest.py`, and the source-grounded audit in
`docs/knowledge-retrieval-audit.md`. Catalog/source bytes, scoring, query
semantics, ordering, budgets, omissions and dependency closure are unchanged.
Performance gates, revision pins and frozen measurement inputs belong to the
governing acceptance issue and its evidence packet, not reusable defaults.

## Plan -> code -> test -> review

1. Inspect the reader, selection helper, store and existing tests. Compare the
   alternatives: local digest reuse is bounded; persistent Bundle caching is
   unsafe with mutable inputs; changing selection is outside this slice.
2. Add a small synthetic Bundle fixture with file and directory dependencies.
   Verify the complete manifest and revision against the existing digest
   formula; count hashing calls and verify each resource is hashed once per
   call. Verify repeated calls detect changed bytes, removed resources, unsafe
   paths, changed metadata/requirements and changed dependency revisions.
3. In `Bundle.manifest()`, build one sorted resource digest map after content
   validation and required-resource checks. Reuse it for dependency validation
   and the returned resource inventory. Reuse validated required paths while
   preserving missing/unsafe-path validation and existing error categories.
4. Run `python -m pytest tests/test_bundle_manifest.py
   tests/test_knowledge_operations.py tests/test_collect_selection.py
   tests/test_knowledge_store.py` and `python -m ruff check
   src/inferrsi/knowledge_operations.py tests/test_bundle_manifest.py`.
   The accountable parent runs the full suite, installed-package checks and
   paired performance/quality protocol after its independent fixture freeze.
5. Review the diff for persistent caching, changed resource closure, digest
   order, invalid-input behavior, private data and unrelated changes. Record
   actual checks separately from pending measurements. Commit with the actual
   configured identity, DCO sign-off and material-agent attribution; hand the
   revision to the accountable parent for independent review and integration.

The audit distinguishes the delivered optional whole-resource context from
historical efficacy claims. It does not reinterpret the prior campaign or
claim that less hashing improves selection quality or agent outcomes.
