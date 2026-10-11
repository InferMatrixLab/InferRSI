---
name: rsi-evidence
description: Guide agents to publish and cite RSI evidence using plan/results/patch/validator paths and PASS/FAIL/INCONCLUSIVE verdicts.
---

# RSI evidence discipline

Use when documenting or reviewing optimization campaigns in ThinkFlowLab-style repos.

## Evidence paths

For campaign id `{campaign_id}`, artifacts live under:

- `evidence/{campaign_id}/plan/`
- `evidence/{campaign_id}/results/`
- `evidence/{campaign_id}/patch/`
- `evidence/{campaign_id}/validator/`

Do not paste metrics only in issue comments—link paths.

## Verdicts

Only **`PASS`**, **`FAIL`**, or **`INCONCLUSIVE`**.

- **PASS**: pinned baseline SHA + pinned candidate SHA, frozen validators, gates met on recorded RunSpec.
- **FAIL**: gates not met with complete evidence.
- **INCONCLUSIVE**: missing freeze, partial runs, or environment blocks comparison.

## SHAs

Baseline and candidate revisions are **owned by the acceptance issue** for that campaign. Replace placeholders like `<baseline-sha>` and `<candidate-sha>` from the issue—never assume org-wide default pins in skills or CI.

## RunSpec

Freeze **repo × revision × backend × device × model × scenario** before comparing results. Reference `rsi_scaffold.runspec.RunSpec` or your renamed package.

## Downstream citation

External PRs link the acceptance issue and SHAs; they do not redefine thresholds. Mark summaries **unverified** if artifacts are missing.
