# Submission notes: `ascend-video-diffusion-optimization`

InferRSI submission record for the packaged Ascend skill.

## Packaged location

```text
src/inferrsi/data/skill_library/hardware/ascend/ascend-video-diffusion-optimization/
├── SKILL.md
├── metadata.json
├── assets/campaign.template.json
├── references/field-notes-video-diffusion.md
└── scripts/evaluate_target.py
```

## Commit and PR

```bash
git checkout -b skill/ascend-video-diffusion-optimization
git add src/inferrsi/data/skill_library/hardware/ascend/ascend-video-diffusion-optimization
git add src/inferrsi/data/skill_library/skill-index.json
git add tests/test_ascend_video_diffusion_skill.py
git commit -s -m "skills: add goal-driven Ascend video diffusion optimization workflow"
```

- DCO sign-off is required (`git commit -s`); do not invent a signing identity.
- Expected CI lane: draft (lint and CPU smoke). No model downloads, GPU jobs, or
  campaign thresholds were added.
- Suggested PR title: `skills: add goal-driven Ascend video diffusion optimization workflow`

Suggested PR body:

> Adds a portable workflow skill for latency / RTF / throughput / peak-HBM work on
> Ascend video diffusion pipelines (condition encoders, DiT, MoE, attention, VAE).
> The skill drives a measure-change-verify loop and ends in a verdict that follows
> the repository claim contract.
>
> - `SKILL.md`: goal contract, stage baseline, optimization loop, candidate
>   selection, correctness protection, final acceptance.
> - `references/field-notes-video-diffusion.md`: first-hand field notes
>   and rejected experiments. Marked unverified and non-reproducible.
> - `scripts/evaluate_target.py`: optional local pre-check for target, improvement,
>   variance, quality and resource gates. Stdlib only, no accelerator dependency.
>   It is explicitly not the source of a public verdict.
> - `assets/campaign.template.json`: schema template with synthetic values; real
>   gates come from the acceptance issue.
>
> No campaign revisions or numeric gates are included. No public performance claim is made.

## Contract alignment

| Rule | How this package complies |
| --- | --- |
| No pins or thresholds in skills | No revisions, SHAs, campaign IDs, or gate values are committed; the template holds synthetic values only and points at the acceptance issue. |
| Verdicts are `PASS` / `FAIL` / `INCONCLUSIVE` | The evaluator emits only those three, plus `INVALID` for unreadable input, which is documented as a tool error rather than a verdict. |
| Microbench ≠ service gain | Section 6 requires the full workload, cold and warm measurement, and issue-scoped evidence. The evaluator's output carries a scope note that a public `PASS` also needs pinned revisions, frozen validators and a complete evidence tree. |
| Validation levels L0–L4 | Section 1 links the repository's level definitions and evidence layout. |
| One plane per step | Section 3 requires one declared change per iteration. |
## Open questions for the maintainer

1. `metadata.json` → `origin`. Every shipped example uses `"external"` for imported
   material. This skill is first-party, so `["first-party"]` was used; confirm the
   allowed values and whether the key should be omitted instead.
2. Optional bilingual edition. The package is English-only, matching the existing
   `skills/` candidates. Say whether a `zh-CN` mirror under the engine skill library
   is also expected.

## Local validation performed

Run:

```bash
pytest -q tests/test_ascend_video_diffusion_skill.py
```

The CPU-only tests verify catalog discovery, trigger metadata, packaged
resources, relative links, and evaluator behavior for `PASS`, `FAIL`,
`INCONCLUSIVE`, and malformed-input `INVALID` results. They do not establish
model-level quality or end-to-end performance; those remain campaign evidence.
