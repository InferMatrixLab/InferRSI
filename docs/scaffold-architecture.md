# Architecture — portable repo scaffold

## System context

```
┌─────────────────────────────────────────────────────────┐
│  docs/repo-template.md (playbook — cited, not forked) │
└──────────────────────────┬──────────────────────────────┘
                           │
     ┌─────────────────────┼─────────────────────┐
     ▼                     ▼                     ▼
 recipes/            benchmarks/            evidence/
 (scenarios)         (harness stubs)        plan|results|patch|validator
     │                     │                     │
     └─────────────────────┼─────────────────────┘
                           ▼
              src/<package>/  (SIAS seams)
         harness/  model/  infra/
                           │
                     tests/ + skills/
                           │
              .github/workflows/ (4 lanes)
```

## SIAS seams (in `src/rsi_scaffold/`)

| Plane | Responsibility |
| --- | --- |
| `harness/` | Runners, scenarios, verdict helpers |
| `model/` | Model/revision placeholders, quality protocol hooks |
| `infra/` | Backend/device/executor placeholders, CI glue types |

Cross-plane dependencies must appear in RunSpec snapshots (see `runspec.py`).

## Claim contract module

`claim.py` defines `Verdict` (`PASS`, `FAIL`, `INCONCLUSIVE`) and documents rules in docstrings—no live campaign numbers.

## Evidence paths

`evidence_paths.py` resolves standard subpaths (`plan`, `results`, `patch`, `validator`) under a campaign root. Campaign IDs and SHAs are supplied at runtime or in issues, not in repo constants.

## CI architecture

| Lane | Trigger | Cost profile |
| --- | --- | --- |
| **draft** | `push` to non-`main` branches | `ruff` + `pytest` smoke |
| **ready** | `pull_request` to `main` | smoke + unit tests; path filters for heavier dirs |
| **merge** | `push` to `main` | manifest / policy job only |
| **nightly** | `schedule` + `workflow_dispatch` | full smoke + lint on `main` |

Acceptance runs with pinned SHAs are **issue-scoped** workflows or manual inputs—not merge lane defaults.
