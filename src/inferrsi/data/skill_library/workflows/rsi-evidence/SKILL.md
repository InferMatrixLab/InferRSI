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

Freeze **repo × revision × backend × device × model × scenario** before comparing results. Reference `inferrsi.runspec.RunSpec` or your renamed package.

## Runtime and upstream review gates

- Keep framework dispatch and its tests model-neutral. Prefer existing explicit
  configuration over a second model/device/version-specific selection rule.
  Model policy belongs in model adapters; backend prerequisites and topology
  constraints belong in the owning backend. Remove obsolete knobs and tests
  when consolidating selection, while retaining default and explicit-opt-in checks.
- Before changing a shared component or script, enumerate direct and transitive
  consumers and map each changed contract to a regression test. Exercise the
  other consumers' fast and fallback paths, layouts, dtypes, hooks and gradients;
  include encoder/decoder integration where applicable. Record commands, source,
  environment, failures and skips. Missing consumer coverage is `INCONCLUSIVE`;
  one model's E2E success does not establish another model's quality or speed.
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

## Goal authority and accounting decisions

When a recommendation, stop/resume decision or repeated settlement depends on
source state, use the [LoopX Goal governance reference](references/loopx-goal-governance/README.md).
It separates canonical Todo authority from Markdown/index projections, Python
fact preparation from TypeScript decisions, and local accounting recovery from
external execution guarantees. Read its counterexamples before interpreting
`should_run`, missing state or a replay lookup. This source-derived candidate
adds no execution permission or empirical validation; the evidence, RunSpec and
verdict rules above still apply.
