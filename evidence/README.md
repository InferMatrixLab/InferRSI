# Evidence tree

[Optimization run submissions](records/README.md) document individual
user-selected runs under `records/`. Campaign acceptance evidence uses the
structure below.

First-class paths for every campaign (see [contribution guide](../docs/contributing.md#evidence-and-claims)).

| Segment | Purpose |
| --- | --- |
| `plan/` | Hypothesis, RunSpec snapshot, gate checklist |
| `results/` | Key metrics, complete trial index, archive references, verdict rationale |
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

Populate per acceptance issue using [the bundle template](_template/README.md)
and [archiving contract](../docs/guides/evidence-archiving.md). Large raw records, logs,
profiler output and generated inventories belong in external versioned archives.
The template has placeholders only, with no actual campaign pins or results.
`results/artifacts.json` is the archive authority; the repository inventory
references it. Validate metadata offline with `tools/validate_evidence.py` and
explicitly verify archive content with `tools/verify_evidence_archive.py`.

When archiving a round that studied knowledge retrieval or adoption, copy
`search/archive/round-<n>.json` from the local campaign directory to
`evidence/<campaign-id>/search/round-<n>.json` in the repository. This is
the portable v2 record produced by `inferrsi evidence import-search --archive-review`.
The campaign's `search/round-<n>.json` is the local v1 window record.
Preserve the campaign-relative paths of any artifacts needed to audit the
round. See the [round import guide](../docs/dashboard.md#archive-evidence-for-readers-outside-the-session).
