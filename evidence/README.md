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
