---
name: rsi-evidence
description: Guide agents to establish acceptance criteria, freeze and cite RSI evidence using plan/results/patch/validator paths and PASS/FAIL/INCONCLUSIVE verdicts.
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "profile": "local-skill-v1",
      "kind": "skill",
      "status": "candidate",
      "origin": [
        "first-party"
      ],
      "consumption_mode": "packaged",
      "tags": [
        "evidence",
        "verdict",
        "runspec",
        "provenance",
        "review"
      ],
      "empirical_validation": "not_run",
      "provenance_readsets": [
        "references/loopx-goal-governance/README.md"
      ],
      "applicability": {
        "scope": "Preparing acceptance criteria, documenting or reviewing an optimization campaign whose verdict will be cited downstream",
        "prerequisites": "For preparation, the user requirements and available model/hardware/workload evidence; for verdicts, pinned baseline and candidate SHAs and an evidence tree under evidence/<campaign-id>/; conclusions about LoopX goal authority additionally need its governance reference",
        "input_contract": "Campaign artifacts in plan/, results/, patch/ and validator/, plus the RunSpec that fixes repo x revision x backend x device x model x scenario",
        "produced_artifact": "An evidence record that links paths instead of pasting metrics, and states exactly one of PASS, FAIL or INCONCLUSIVE with its rationale",
        "failure_modes": [
          "Metrics pasted into an issue comment with no link to an evidence path",
          "A verdict vocabulary outside PASS/FAIL/INCONCLUSIVE",
          "PASS recorded on a cleanup or integrity-probe failure",
          "Output reused across trials, aliased into a reference, or written outside its own trial directory",
          "Source fingerprint taken over a directory overlap that excludes changed tracked files",
          "Org-wide default SHAs assumed in a skill or CI instead of read from the acceptance issue"
        ],
        "refusal_point": "Refuses PASS when the validator freeze, the results rationale or the pinned SHAs are missing, and reports INCONCLUSIVE for that campaign instead"
      },
      "recommendations": [
        "Use user-supplied acceptance criteria; otherwise follow performance-ceiling-analysis to formulate targets. Preserve partial requirements and record each derived field's evidence before freezing gates.",
        "Link evidence paths in the report; a metric quoted only in a comment cannot be re-checked later.",
        "Fingerprint tracked source even when the output directory overlaps it, and exclude only the current run's generated files.",
        "Treat a missing upstream-cache release proof as INCONCLUSIVE rather than a PASS with a caveat.",
        "Read baseline and candidate SHAs from the acceptance issue for that campaign, never from a skill default.",
        "Freeze optional required_trial_checks for complete requests, effective graph controls and clean worker exits; require literal true per trial and retain supporting receipts."
      ],
      "limitations": [
        "Documents evidence discipline; it performs no measurement and certifies no campaign.",
        "The LoopX goal-governance reference is a source-derived candidate and adds no execution permission or empirical validation."
      ]
    }
---

# RSI evidence discipline

Use when documenting or reviewing optimization campaigns in ThinkFlowLab-style repos.

## Establish acceptance criteria

Use the user's supplied criteria, including a referenced accepted plan. If none
were supplied, use `performance-ceiling-analysis` to formulate evidence-backed
targets under its [acceptance-criteria procedure](../../../playbooks/measurement/performance-ceiling-analysis/references/acceptance-criteria.md).
Preserve partial requirements and derive only missing fields. Record the source
of each criterion, derivation evidence and freeze authority before search.
Unknown inputs remain explicit; estimates cannot relax supplied or frozen gates.

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

## Omni and streaming experiments

Use the [Omni experiment contract](references/omni-experiments.md)
for reference/RNG parity, feedback-aware stage boundaries,
matching streaming decode schedules, internal graph controls and protocol preflight.
Freeze selected `--require-trial-check` dotted boolean fields
in RunSpec and require literal true evidence from every baseline/candidate trial.
Missing, malformed or false fields make qualification INCONCLUSIVE; a successful
process and metric alone do not prove complete requests or normal worker exits.
Retain underlying receipts and all failed attempts. After repairing the harness,
rerun the complete comparison rather than combining arms from different attempts.
These checks do not replace the accuracy dataset or mixed-request concurrency.
