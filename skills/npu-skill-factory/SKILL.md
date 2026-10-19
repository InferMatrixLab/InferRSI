---
name: npu-skill-factory
description: 'Design and operation of the InferRSI NPU skill factory: artifact lifecycle, skill evaluation contract, corpus selection, hide-and-re-distill procedure, and skill evolution cycle. Use when deciding where new skill artifacts belong, how to distill a candidate skill, or how to run the No-Skill vs Human-Skill vs Distilled-Skill comparison.

  '
---

# NPU Skill Factory Design

Status: candidate. A Tier A pilot was reported by the sibling workstream on
2026-10-14; it was not integrated or rerun here. This skill supplies methodology,
not an implemented factory or automatic promotion pipeline.

## Choose the evidence product

Choose a case, reusable knowledge, bounded amendment or new skill according to
scope and workflow ownership. A new source need not create a new skill; a distinct
trigger, procedure and output can justify one. The
[evidence-routing note](references/papers-20261015/knowledge/evidence-routing.md),
[comparison](references/papers-20261015/COMPARISON.md),
[counterexamples](references/papers-20261015/cases/methodology-counterexamples.md)
and [exact paper readset](references/papers-20261015/references/readset.md)
retain the approved paper-level reasoning alongside the older repository pins.

Keep source fidelity, static usability, execution correctness, behavioral efficacy
and transfer evidence separate. Construction, selection, deployment-context and
downstream costs need distinct denominators; a library entry or upstream score
is not local promotion. Source limitations and unrun checks remain explicit.

Current candidate bundles live under `skills/<name>/`, with linked references and
cases under their owning skill. Exactly two primary matrices record provenance
and coverage. Do not invent a paper Git SHA or force these notes into a repository
knowledge-record schema that requires implementation fields they cannot supply.
The CLI explicitly reads metadata, instructions and resources; it implements no
factory, automatic routing or updater. Manual integration is not an AREX/DisCo run.

## Artifact lifecycle

The following lifecycle and schema are historical design references from the
sibling workstream and PR #9, not current implemented repository contracts.
Use the current candidate layout above for integration; historical evaluation
examples neither launch work nor set universal promotion thresholds.

```
1. Raw/preflight evidence
      ↓  (exploration, repo cloning, index extraction — read-only)
2. Imported / distilled source material
      ↓  (knowledge JSON records in repo_packs/, skill_library/ entries)
3. Candidate skill (SKILL.md + schema-validated bundle)
      ↓  (3-5 candidates from a distillation run; status: candidate)
4. Skill evaluation
      ↓  (No-Skill vs Human vs Distilled comparison on held-out tasks)
5. Promoted executable skill (in skills/)
      ↓  (only after a passing evaluation campaign with PASS evidence)
6. Evolution (bounded edit → re-evaluation → accept/reject)
```

**Promotion rule:** directory placement does not establish promotion. The current
`skills/` tree includes explicitly labeled candidates. A candidate without an
authorized evaluation trail remains unvalidated regardless of packaging.

**Where each artifact belongs:**

| Artifact | Location | Format |
|----------|----------|--------|
| Knowledge records (experience) | `src/inferrsi/data/repo_packs/<repo>/knowledge/<backend>/<component>/<name>.json` | Validated JSON (catalog.py schema) |
| Bilingual skill library | `src/inferrsi/data/skill_library/en/<repo>/` and `zh-CN/<repo>/` | SKILL.md + references/ + scripts/ |
| Skill bundle (distillation output) | `evidence/<campaign-id>/plan/agent-source-candidates/` | schema-validated JSON bundle |
| Human reference skill | `evidence/<campaign-id>/plan/human-<name>/SKILL.md` | SKILL.md + references/ |
| Candidate skill under evaluation | `evidence/<campaign-id>/plan/agent-source-candidates/<name>/` | SKILL.md + references/ |
| Promoted skill | `skills/<name>/SKILL.md` + `metadata.json` | InferRSI skill format |
| Skill evaluation evidence | `evidence/<campaign-id>/results/` | per InferRSI evidence tree |

Source: PR #9 `skill_library/` layout (source-grounded, pr/9 @ 4ad551a9);
sibling workstream `evidence/skill-bootstrap-20261014/` (observed @ 82218b4).

## Skill bundle schema

Each distillation produces a bundle validated against `schemas/skill-bundle.json`.
A bundle must have:

- `status`: `"candidates_generated"` or `"blocked"` (not a placeholder).
- `capability_graph.nodes`: each node has `id`, `label`, and `source_paths`
  pointing to files actually present in the source snapshot.
- `skills`: 3-5 candidates, each with:
  - `name`: lowercase, no spaces, ≤63 chars.
  - `capability`, `applicability`, `preconditions`, `inputs`, `outputs`,
    `procedure`, `knowledge_sources`, `code_evidence`, `docs_evidence`,
    `tools`, `scripts`, `validation` (≥1 item), `failure_modes`.
  - `provenance.source_repo`, `provenance.source_revision`,
    `provenance.source_paths` (all paths must be in the snapshot).
  - `revision.version` and `revision.parent`.

Source: `schemas/skill-bundle.json` (observed @ 82218b4).

## Existing corpus: selected NPU performance skills

These four skills are the starting corpus for hide-and-re-distill and the
A/B/C comparison:

| Skill | Repo | Path | Purpose | Perf-relevant |
|-------|------|------|---------|---------------|
| profiling-analyze | MindIE-SD @ 8481d39b | `.agents/skills/profiling-analyze/` | 5-layer CANN profiling analysis from CSV/JSON | Yes |
| dit-perf-opt | MindIE-SD | `.agents/skills/dit-perf-opt/` | DiT bottleneck → feature selection → A/B | Yes |
| perf-gate | MindIE-SD | `.agents/skills/perf-gate/` | Same-window A/B protocol & noise floor | Yes |
| ops-profiling | awesome-ascend-skills @ 75ec89ce | `external/cannbot/ops/ops-profiling/` | Operator profiling → roofline | Yes |

The two `vllm-ascend` skills in the sparse clone are framework-integration and
CI/CD skills, not performance skills. They are not used in this corpus.
Source: `w3b-ascend-corpus-evidence.md` (2026-10-14).

**License status:** MindIE-SD is Apache-2.0. `awesome-ascend-skills` synced from
GitCode; license is UNKNOWN — flag this before any external publication.

## Stage 3.4 — Hide-and-re-distill procedure

Best candidate: `profiling-analyze` from MindIE-SD.

**Why this candidate:**
- The skill encodes NPU-specific knowledge that is only partially recoverable from
  public documentation: CANN CSV field aliasing proof (value-set matching, not
  header name matching), silent failure patterns ("export succeeded" ≠ file
  exists), and empirical utilization rules (call counts stable across devices,
  single-kernel ms varies ±10%, single collective latency varies ~2×).
- Source material available before the skill's cutoff: CANN 24.7+ public CSV
  spec, `torch_npu.profiler` API, reference materials in `.agents/skills/profiling-analyze/references/`.
- The distilled version can be compared at the same length budget (~295 lines,
  ~1287 words).

**Temporal cutoff (REMOTE verification required):**
Run `git -C <repo> log --follow -- .agents/skills/profiling-analyze/SKILL.md`
on the MindIE-SD clone at revision 8481d39b to find creation and last
substantive change dates. Reported by corpus agent as 6-12 months pre-cutoff,
but the exact dates are INSUFFICIENT_EVIDENCE locally.

**Procedure:**
1. Archive source snapshot at `cutoff_commit` (the commit just before the skill
   was last substantially changed). Remove `.agents/skills/profiling-analyze/`
   from the archive (this is the "hidden" material).
2. Keep: CANN public docs, `torch_npu.profiler` API, any referenced source files
   that predate the cutoff, the `analyze_trace.py` and `compare_traces.py`
   scripts that ship with the skill.
3. Run `python -m omnirsi.harness.skill_distill` with the distillation config
   pointing to the archived snapshot, producing 3-5 candidates.
4. Validate the bundle against `schemas/skill-bundle.json`.
5. Render candidate SKILL.md files from the bundle.
6. Proceed to Stage 3.5 evaluation.

Source: sibling workstream `skill_distill.py` (observed @ 82218b4), which
implements this exact procedure for the `retire-mlapo-env` task.

## Stage 3.5 — Skill evaluation contract

**Three variants:**

| Variant | What the agent receives |
|---------|------------------------|
| no_skill | Task only; no skill document |
| human | Task + frozen human SKILL.md from `plan/human-<name>/` |
| distilled | Task + rendered candidate SKILL.md from bundle |

Fix across all variants: same model, same harness, same tools, same task,
same base commit, same budgets.

**Evaluation measures:**

| Measure | Type | Notes |
|---------|------|-------|
| Task success | Primary | Frozen validator exit code: 0 = success, 1 = fail, other = inconclusive |
| Correctness | Primary | Does the patch actually pass the verification contract? |
| Regression | Primary | Does the validator's regression check pass? |
| Files inspected | Secondary | From agent trace `tool_calls` count |
| Tool calls | Secondary | From agent trace |
| Failed attempts | Secondary | `failed_commands` from trace |
| Input tokens | Cost | From `turn.completed` events |
| Wall time | Cost | Elapsed seconds per variant |
| Patch minimality | Quality | Lines added/removed relative to oracle diff |
| Repo convention adherence | Quality | Requires human review |

Tier A tasks: CPU/static correctness only. Tier B tasks: require NPU device.

**Accept criterion (SkillOpt-derived, adapted for InferRSI):**
The distilled skill is accepted for promotion when, on a held-out task set:
```
task_success(distilled) > task_success(no_skill)
```
with no regression relative to `human` on correctness or Tier A validation.
A single pilot result (1 task × 1 repetition each) is not sufficient for
promotion. The accept criterion requires: ≥3 tasks, ≥2 repetitions per variant,
`inconclusive` trials excluded from the success-rate estimate, and a campaign
evidence tree under `evidence/<campaign-id>/`.

Do not promote based on token cost alone. Lower input tokens does not imply
better task success.

Source: sibling workstream pilot result (one Tier A task, all three variants
pass, no statistical difference established — consistent with the criterion
above: INCONCLUSIVE for promotion).
`evidence/skill-bootstrap-20261014/results/pilot-01-summary.json` (observed @ 82218b4).

**Skill build cost vs per-task runtime benefit:**
Record `build-cost.json` separately from task execution costs. The distillation
run's usage (model calls, elapsed time) is a one-time cost amortized over all
tasks the skill is used for. Do not include distillation cost in per-task ROI.

## Skill revision lineage

When an accepted skill is subsequently evolved, preserve the revision chain:

```
skills/<name>/
  SKILL.md           (current promoted version)
  metadata.json      (includes revision.version and revision.parent)
  history/
    v0/SKILL.md      (initial promoted version)
    v1/SKILL.md      (first accepted evolution)
    ...
```

`revision.parent` points to the previous version's SHA or version string.
Rejected candidates are stored in the evidence tree of the evolution campaign
under `evidence/<evolution-campaign-id>/plan/rejected-candidates/`.
Source: skill bundle schema `revision` field (observed @ 82218b4); skill history
layout is a design decision — no prior implementation exists in this branch.

## Skill evolution cycle (minimum viable, Phase 1)

One evolution cycle:

1. **Select trigger:** a task where the current skill (v0) produced FAIL or
   INCONCLUSIVE, or where the human skill outperformed the distilled one by a
   measurable margin (not within noise).
2. **Bounded edit:** propose a revision that changes only the `procedure`,
   `failure_modes`, or `knowledge_sources` sections, not the `capability` or
   `applicability` contract. Length budget: ±20% of current skill length.
   Do not replace the entire skill.
3. **Independent evaluation:** use development/selection evidence to choose the
   candidate; keep final-test tasks outside adaptive edit selection. Check combined
   behavior and unrelated successes, not only the triggering failure.
4. **Accept/reject gate:** apply the frozen task-specific contract. A tie or noisy
   result is not an improvement. Preserve the incumbent and report regressions or
   inconclusive outcomes without excluding them silently from success estimates.
5. **Revision lineage:** on accept, copy the current `SKILL.md` to `history/v0/`
   and write the accepted edit as the new `SKILL.md`. Update `metadata.json`
   with the new `revision.version`.

This cycle does not require automatic trace harvesting in Phase 1. The trigger
comes from observed evaluation failures. Harvest-from-real-traces (SkillOpt
Sleep cycle) is deferred to Phase 2.

## Where to go next after Phase 1

Once the evaluation contract is validated on ≥1 Tier A task with ≥3 tasks and
≥2 repetitions:

1. Add Tier B tasks (require a real NPU environment — REMOTE).
2. Expand corpus from `raw_npu_repos_metadata_only` in `preflight.json`:
   priority order is Ascend/pytorch, then op-plugin, then triton-ascend, then msit.
   Do not clone all four at once; state the capability/question first.
3. Implement harvest-from-real-agent-traces (SkillOpt Sleep cycle pattern).
4. Wire the skill router to select skill by detected repository type and task tier.

## What this skill does not do

- It does not claim that any distilled skill works on a real NPU — all current
  evaluation is Tier A (CPU/static).
- It does not establish statistical significance from the current pilot.
- It does not manage the catalog or automatically route agents to skills.
- It does not provide the skill library management framework — that is PR #9.
