# Evidence tree

First-class paths for every campaign (see [contribution guide](../docs/contributing.md#evidence-and-claims)).

| Segment | Purpose |
| --- | --- |
| `plan/` | Hypothesis, RunSpec snapshot, gate checklist |
| `results/` | Metrics, logs, verdict rationale |
| `patch/` | Candidate diff or revision pointer |
| `validator/` | Frozen validator definition + inputs |

## Convention

```
evidence/
  <campaign-id>/
    plan/
    results/
    patch/
    validator/
```

Populate per acceptance issue. This scaffold keeps only `.gitkeep` placeholders—no campaign artifacts or pinned SHAs in the template.

When archiving a round that studied knowledge retrieval or adoption, copy
`search/archive/round-<n>.json` from the local campaign directory to
`evidence/<campaign-id>/search/round-<n>.json` in the repository. This is
the portable v2 record produced by `campaign import-search --archive-review`.
The campaign's `search/round-<n>.json` is the local v1 window record.
Preserve the campaign-relative paths of any artifacts needed to audit the
round. See the [round import guide](../docs/dashboard.md#archive-evidence-for-readers-outside-the-session).
