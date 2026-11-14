---
name: draft-acceptance-issue
description: Draft a campaign acceptance issue with checklist, RunSpec, evidence paths, and placeholders for baseline/candidate SHAs.
---

# Draft acceptance issue

Use when starting a new campaign in a ThinkFlowLab RSI-style repo.

## Steps

1. Pick `campaign_id` (naming: `{model-or-scenario} / {device}×{count}`).  
2. Copy `evidence/_template/` → `evidence/<campaign_id>/` (empty tree with README stubs).  
3. Open issue using `.github/ISSUE_TEMPLATE/campaign-acceptance.yml` or [docs/contributing.md#acceptance-checklist](https://github.com/InferMatrixLab/InferRSI/blob/b2f60f913a949f9073686a23476f752e11d709a4/docs/contributing.md#acceptance-checklist).
4. Fill **pinned baseline SHA** and **pinned candidate SHA** in the issue—use placeholders `<baseline-sha>` / `<candidate-sha>` until known.  
5. Resolve criteria using the [acceptance-criteria procedure](../../methods/performance-ceiling-analysis/references/acceptance-criteria.md):
   use user-supplied criteria; otherwise use `performance-ceiling-analysis` to
   formulate targets. Preserve partial requirements, label derived fields and
   retain unresolved evidence gaps. List supported gates and their provenance in
   `plan/` before candidate search.
6. Set initial verdict `INCONCLUSIVE`.  

## Do not

- Commit campaign SHAs into `recipes/`, `benchmarks/`, skills, or workflow defaults.  
- Claim `PASS` without `validator/` freeze and `results/` rationale.  

## Output

Issue body sections: campaign id, SHAs, RunSpec, criteria source and derivation (including evidence gaps and freeze authority), gates, evidence paths, verdict, downstream citation blurb.
