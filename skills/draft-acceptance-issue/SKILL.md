---
name: draft-acceptance-issue
description: Draft a campaign acceptance issue with checklist, RunSpec, evidence paths, and placeholders for baseline/candidate SHAs.
---

# Draft acceptance issue

Use when starting a new campaign in a ThinkFlowLab RSI-style repo.

## Steps

1. Pick `campaign_id` (naming: `{model-or-scenario} / {device}×{count}`).  
2. Copy `evidence/_template/` → `evidence/<campaign_id>/` (empty tree with README stubs).  
3. Open issue using `.github/ISSUE_TEMPLATE/campaign-acceptance.yml` or [docs/issues-acceptance-checklist.md](../../docs/issues-acceptance-checklist.md).  
4. Fill **pinned baseline SHA** and **pinned candidate SHA** in the issue—use placeholders `<baseline-sha>` / `<candidate-sha>` until known.  
5. List gates in `plan/` before any RSI or search loop.  
6. Set initial verdict `INCONCLUSIVE`.  

## Do not

- Commit campaign SHAs into `recipes/`, `benchmarks/`, skills, or workflow defaults.  
- Claim `PASS` without `validator/` freeze and `results/` rationale.  

## Output

Issue body sections: campaign id, SHAs, RunSpec, gates, evidence paths, verdict, downstream citation blurb.
