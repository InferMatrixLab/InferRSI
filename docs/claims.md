# Claims (fill-in template)

## Verdict vocabulary

| Label | Meaning |
| --- | --- |
| `PASS` | Pinned baseline SHA + pinned candidate SHA; gates met; evidence tree complete |
| `FAIL` | Gates not met; evidence complete enough to defend the failure |
| `INCONCLUSIVE` | Missing validator freeze, partial runs, or environment blocks comparison |

## What belongs in an acceptance issue

- Campaign name: `{model-or-scenario} / {device}×{count}`  
- **Baseline SHA** and **candidate SHA** (filled per issue—not in shared CI defaults)  
- RunSpec dimensions: repo, revision, backend, device, model, scenario  
- Gate checklist (numeric bars, validators, e2e scenarios)  
- Evidence root: `evidence/<campaign-id>/` with `plan/`, `results/`, `patch/`, `validator/`  

## What downstream may say

- Link issue + SHAs; summarize numbers **only** if they match `results/` artifacts  
- Otherwise label **unverified**  

## Repo-local claims log

| Campaign id | Issue | Verdict | Notes |
| --- | --- | --- | --- |
| _example-campaign_ | _#_ | _INCONCLUSIVE_ | _scaffold placeholder_ |
