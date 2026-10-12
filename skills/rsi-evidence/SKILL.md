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

Freeze **repo × revision × backend × device × model × scenario** before comparing results. Reference `omnirsi.runspec.RunSpec` or your renamed package.

## Runtime and upstream review gates

- Hardware/dtype matches do not prove build dependencies or collective availability.
  Keep optional acceleration opt-in until initialization establishes prerequisites;
  do not fall back on only one rank after starting a collective.
- Prove that request caches release after success, failure, interruption and
  dropped step-mode requests. Avoid strong references from singleton models to
  request prefix KV. Preserve reusable graph buffers separately.
- Search the target repository for shared primitives before adding kernels.
  Place reusable math in its common operator layer, keep model-specific policy
  in the adapter, and qualify reduction order, casts, hooks and dtype fallbacks.
- Fingerprint tracked source even when output directories overlap source.
  Exclude only the current run's generated untracked artifacts.
- Require outputs to resolve inside their own trial directory. Reject aliases to
  references, repeated paths within a trial, and reused outputs across trials.
- Cleanup and integrity probe failures must still produce a failed manifest;
  missing evidence or changed source must never become `PASS`.
- Publish portable reproduction commands and path-normalized evidence with
  checksums. Keep the archived raw records immutable and distinguish historical
  frozen claims from fresh comparisons on rebased code.

## Downstream citation

External PRs link the acceptance issue and SHAs; they do not redefine thresholds. Mark summaries **unverified** if artifacts are missing.
