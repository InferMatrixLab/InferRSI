# Candidate

Runtime candidate: commit `6da28494` on baseline `ab03f3ffb8f2e5bc02c304828c5c41890eef673e`.

`Bundle._manifest` / `_view` may reuse validated resource path/content hashes only within one Collect invocation. Keys contain the exact path and immutable bytes; metadata, required resources and dependency revisions are still validated for each bundle. Public manifest/view calls remain uncached. Default selection, ranking, limits, explicit identities and context resources are unchanged.

The same packaged library bytes were repeatedly validated and hashed for each generated skill owner. This removes repeated resource work, not corpus contents or provenance checks. No cross-request state is introduced. Tests exercise changed bytes at the same path, multiple owners, mutable metadata/dependencies, unsafe paths and request lifetime.

Tradeoff: the request-local memo retains distinct resource bytes/keys until that Collect call completes. It is not a cross-request cache, but memory overhead is nonzero. Peak memory is not measured in this campaign and no memory-improvement claim is made.

## Withheld from production

The final feature branch reverts the runtime change in `23e769ac`; production runtime matches the baseline. The candidate-specific regression tests are retained with the candidate, not active against baseline private APIs. This is evidence-only delivery, not promotion of an unaccepted optimization.

`candidate.patch` preserves the source/test delta. The 2.2KB `candidate.bundle` additionally preserves the **exact** original candidate commit so replication does not depend on a temporary branch surviving a squash merge. It requires the baseline commit already in this repository:

```sh
git bundle verify evidence/indexer-255-20261029/patch/candidate.bundle
git fetch evidence/indexer-255-20261029/patch/candidate.bundle \
  refs/heads/issue255-indexer-evidence:refs/heads/reproduce-indexer-255-candidate
git worktree add /tmp/indexer-255-candidate 6da28494891b21cdc89f632d84d763bc997b7d15
```

Do not use the final evidence-only branch as the optimized arm. No more performance studies were run after the single prospective confirmation.
