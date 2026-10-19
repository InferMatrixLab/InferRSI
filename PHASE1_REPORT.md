# InferRSI Phase 1 Report — Meta-Skill Bootstrap

> Historical snapshot from 2026-10-14. Its inventory, proposed next steps and
> sibling-workstream reports are not current implementation or validation status.
> Use the [three-objective overview](README.md#three-objectives-of-the-current-wip),
> [Reference Matrix](docs/reference-matrix.md) and
> [SearchSpace Matrix](docs/searchspace-matrix.md) for current framing and evidence.
> The original report below is preserved; new Magpie coordination evidence remains
> pending Dot delivery and owner review.

**Branch:** `opus/meta-skill-bootstrap`
**Date:** 2026-10-14
**Base:** `4c8e1285` (InferMatrixLab/InferRSI main)

---

## Executive summary

This branch adds three candidate meta-skills to InferRSI and a design document
for the NPU skill factory, without duplicating the existing runner, evidence,
or verdict infrastructure. The sibling workstream (`Dong1017/InferRSI @
codex/skill-eval-bootstrap`) has already implemented the distillation and
evaluation runner; this branch's role is to provide the skill content and
the design contract that runner operates against.

**Artifacts added:**

| Path | Status | Notes |
|------|--------|-------|
| `skills/performance-ceiling-analysis/SKILL.md` | candidate | Three-level model, measurement plan, INSUFFICIENT_EVIDENCE for B300 |
| `skills/performance-ceiling-analysis/metadata.json` | candidate | Source provenance, verification state |
| `skills/repository-evolution-analysis/SKILL.md` | candidate | Magpie-grounded, LTC temporal-split method |
| `skills/repository-evolution-analysis/metadata.json` | candidate | |
| `skills/npu-skill-factory/SKILL.md` | candidate | Lifecycle contract, evaluation design, evolution cycle |
| `skills/npu-skill-factory/metadata.json` | candidate | |

---

## Workstream 1 — Performance Ceiling Analysis

### Question
Can an agent estimate optimization headroom well enough to decide whether a
target such as 2× is worth pursuing?

### Source evidence

| Source | Repo | Commit | What was extracted |
|--------|------|--------|-------------------|
| perf-analysis/SKILL.md | NVIDIA/TensorRT-LLM | f33e0e5f | Bottleneck classification table, delegation model, escalation trigger |
| roofline-analysis.md | NVIDIA/TensorRT-LLM | f33e0e5f | SOL% interpretation, hierarchical roofline, ridge-point concept |
| roofline_model.py, model_analyzer.py | hahnyuan/LLM-Viewer | 1893e4b5 | Per-layer FLOPs formula, arithmetic intensity, hardware table schema |
| hardware_params.py | hahnyuan/LLM-Viewer | 1893e4b5 | NPU entry required fields: name, peak_flops, memory_bandwidth, memory_capacity |
| configs/DiT.py | hahnyuan/LLM-Viewer | 1893e4b5 | DiT vs LLM difference: fixed-frame sequence length, no KV growth |
| driver1.c, roofline.py | ebugger/ERT | 0771fa96 | Empirical sweep procedure, anti-optimization trick (alpha *= 1-1e-8) |

### Method extracted

Three-level model:
- **L1 analytical**: FLOPs formula per layer type, arithmetic intensity, roofline bound with hardware table entry. Works without hardware access.
- **L2 empirical component**: SOL%, occupancy, kernel bottleneck classification via profiler counters. Requires remote accelerator.
- **L3 end-to-end**: Per-stage Amdahl formula, covering scheduler + denoising steps + VAE + audio codec + communication + idle gaps.

Escalation rule: go L1 → L2 when AI is near the ridge point or when kernel attribution matters. Go L2 → L3 when individual kernels are near their ceiling but E2E is still below expected.

**Amdahl formula:**
```
S_total = 1 / Σ_i (f_i / s_i)
```
where f_i = stage fraction of total time, s_i = achievable speedup on stage i.

### Implementation

`skills/performance-ceiling-analysis/SKILL.md` — answers all seven required
questions: WHEN to use, WHAT evidence first, HOW to escalate, HOW to estimate
all three ceilings, HOW to express uncertainty, HOW to decide feasibility,
WHAT experiment to run next.

For the fishaudio/drama-3 / B300 target case, every empirical field is labelled
`INSUFFICIENT_EVIDENCE` and listed as a named REMOTE measurement to be taken.
No accelerator numbers are fabricated.

### Validation

Source-grounded only. Cannot be empirically validated on this machine.
Verdict: **INCONCLUSIVE** (hardware unavailable; structural correctness reviewed).

### Limitations

- B300 hardware constants (peak FP16 FLOP/s, memory bandwidth) are missing from
  all source files — they must come from the NVIDIA datasheet or an ERT run.
- ERT's `driver1.c` is C/CUDA; an NPU port requires a vendor-specific compute
  API and is an open design question.
- L3 stage fractions for drama-3 under vLLM-Omni and SGLang-Omni are unknown;
  the Amdahl formula cannot produce a meaningful answer without them.

### Next experiment

REMOTE: (1) Add B300 hardware entry to LLM-Viewer table from NVIDIA datasheet.
(2) Run nsys on drama-3 serving at concurrency 1 and 8 to extract stage fractions.
(3) Run ncu on the dominant denoising kernel to determine SOL% and AI vs ridge point.
(4) Fill the measurement plan schema in `SKILL.md` with real numbers and produce
the first ceiling analysis report.

---

## Workstream 2 — Repository Evolution and Fast Iteration

### Question
Does repository history provide actionable knowledge that a current source
snapshot does not?

### Source evidence

| Source | Commit | What was extracted |
|--------|--------|-------------------|
| magpie-commits.jsonl | 77800032 | 3428 commits, numstat, top-3 paths; diff-size percentiles computed |
| magpie-clusters.json | — | 14 provisional clusters (8 confirmed: provider onboarding, subscription/auth, routing, GUI settings, library/MCP, session search, usage/metering, i18n) |
| magpie-important-commits.md | — | 45-commit shortlist; 8 SHAs verified via git show --stat |
| LearningToCommit pipeline | 7e5a1d77 | s1–s5 pipeline, temporal split, skill conditioning, evaluation contracts |

### Method extracted

**Why Magpie iterates quickly** (evidence-grounded):
- 71% of commits are under 1000 lines; p50 = 151 lines, p75 = 342. Diffs are small, which means faster review and more isolated risk. *Source: computed from JSONL.*
- Median feature-to-repair latency: 1.54 hours (454 commit pairs). 42% of repairs land within 1 hour. *Source: computed.*
- 91.3% of focused commits touch only one top-level directory; provider, gateway, and GUI changes arrive separately. *Source: computed.*
- ~40 PRs/day merge cadence. *Source: computed from PR number patterns in subjects.*
- Abstraction layers appear *after* 2–5 concrete implementations exist, not speculatively. *Source: observed from commit date ordering; causation not established.*

**Temporal-split mechanism** (from LearningToCommit):
The agent receives a source archive built from `base_commit` (parent of the
sampled commit) with the target change excluded. The temporal cutoff is enforced
by the archive, not a log filter. This is reusable for non-LLM repos with the
following adaptations: problem synthesis from commit message + diff (not issue
trackers), validation via compiler + test pass + performance regression gate,
and an agent toolset that includes a compiler and profiler.

**45-commit shortlist validity:** 8 of 45 SHAs verified by diff sampling;
all confirmed as high-information commits. The heuristic (large diff + new capability
label) is adequate for further use; expand beyond it only for capability evolution
sequence reconstruction.

### Implementation

`skills/repository-evolution-analysis/SKILL.md` — covers state model, capability
model, transition model construction procedure, the Magpie fast-iteration findings,
and the full temporal-split benchmark construction procedure from LearningToCommit.

The capability evolution graph JSON, `w2-capability-evolution-graph.json`, is a
local research artifact excluded from this PR
(generated by the W2 research agent, 2026-10-14). It covers three families
(provider onboarding, library/MCP centralization, usage metering) with real SHAs
and before/after states. The skill document describes how to build such a graph
for a new repository.

### Validation

Source-grounded. The 8 diff samples match their description.
Verdict: **INCONCLUSIVE** (no agent benchmark run with vs. without the skill).

### Limitations

- This skill's history is Magpie-specific. A new repository needs its own evolution
  analysis before this skill is useful as a conditioning document for that repo.
- The LearningToCommit temporal-split evaluation is expensive (requires running
  an agent on multiple historical tasks). No benchmark has been run on InferRSI
  yet with and without the skill.
- Repair-latency and merge-cadence results are correlation, not causation.

### Next experiment

Construct 3–5 historical tasks from a target repository using the LearningToCommit
pipeline map. Run the three-variant experiment (no_skill, human, distilled) on
those tasks using the existing skill_eval harness. Compare file localization and
patch minimality as primary metrics.

---

## Workstream 3 — NPU Skill Factory

### PR #9 reconciliation

PR #9 (`4ad551a9`, david6666666) adds `src/inferrsi/data/skill_library/` with 42
bilingual skill documents (21 per language) for 5 inference engines, a
`source-manifest.json`, and knowledge JSON records in 4 new `repo_packs/` entries.
It extends `catalog.py` to add `strata, sglang, sglang_omni` to `REPO_TYPES`.
It does **not** add generation, evaluation, or evolution machinery.

The sibling workstream (`Dong1017/InferRSI @ codex/skill-eval-bootstrap`) adds
`skill_distill.py`, `skill_eval.py`, `schemas/skill-bundle.json`, and a completed
pilot in `evidence/skill-bootstrap-20261014/`. It is based on the upstream
pre-PR#9 tree (commits 1eae6e7 and older are shared; 4c8e128 is not).

**Decision:** the lifecycle design in this branch (`skills/npu-skill-factory/SKILL.md`)
is compatible with both. Knowledge records land in `repo_packs/` per PR #9
conventions. Candidate skills live in `evidence/<campaign-id>/plan/` per the
sibling workstream's pilot. Promoted skills land in `skills/` here. The two
branches are complementary, not competing.

### Artifact lifecycle

Six stages documented in `skills/npu-skill-factory/SKILL.md`:
```
Raw/preflight → Imported knowledge → Candidate bundle → Evaluation →
Promoted skill → Evolution
```

Each stage has a specific storage location, format, and promotion criterion.
The critical rule: do not bulk-copy imported skills into `skills/`.

### Human-skill corpus

Four skills selected from MindIE-SD @ 8481d39b and awesome-ascend-skills @ 75ec89ce.
Best Stage 3.4 candidate: `profiling-analyze` (MindIE-SD).

Reasons: (1) encodes CANN field aliasing proof and silent-failure patterns that
are not in public documentation; (2) executable helpers (analyze_trace.py,
compare_traces.py) run CPU-only; (3) distilled version can be compared at the same
length budget; (4) source material predates the skill by 6–12 months.

License note: MindIE-SD is Apache-2.0. `awesome-ascend-skills` has UNKNOWN
license (synced from GitCode) — must be resolved before external publication.

### Skill evaluation contract

Implemented in sibling workstream. Contract defined in `skills/npu-skill-factory/SKILL.md`:
- Three variants: no_skill, human, distilled.
- Accept criterion: `task_success(distilled) > task_success(no_skill)` with no
  regression on correctness, over ≥3 tasks × ≥2 repetitions, excluding inconclusive.
- Skill Build Cost recorded separately from per-task runtime cost.

First pilot result (sibling workstream, 2026-10-14):
- 1 Tier A task (`retire-mlapo-env`), 1 repetition per variant.
- All three variants: success, validator passes.
- Wall time: no_skill 381s, human 504s, distilled 371s.
- Input tokens: no_skill 402K, human 682K, distilled 265K.
- **Interpretation: INCONCLUSIVE for promotion.** One easy task, one trial. Token
  reduction is encouraging but not sufficient evidence. See `evidence/skill-bootstrap-20261014/results/pilot-01-summary.json`.

### Evolution cycle

Minimum viable cycle documented in `skills/npu-skill-factory/SKILL.md`:
Skill_v0 → failing task trigger → bounded edit (procedure/failure_modes sections
only, ±20% length) → held-out evaluation → `PASS`/`FAIL`/`INCONCLUSIVE` →
accept/reject with lineage preserved in `skills/<name>/history/`.

Accept criterion (adapted from SkillOpt `gate.py`):
`candidate_hard_accuracy > current_skill_hard_accuracy` on the held-out set.

### Next experiment: Stage 3.4 (hide and re-distill)

1. Verify `profiling-analyze` temporal cutoff via `git log` on the MindIE-SD clone.
2. Archive MindIE-SD source at `cutoff_commit` excluding the skill file.
3. Run `python -m inferrsi.harness.skill_distill` (sibling workstream) targeting
   `profiling-analyze` capability.
4. Run the three-variant experiment on ≥3 Tier A CANN profiling tasks.

---

## Q&A

**Q1. Can an agent estimate optimization headroom well enough to decide whether 2× is worth pursuing?**

Yes, at L1 (analytical), with caveats. Given model config and a hardware spec
entry, the agent can compute the roofline bound, classify memory-bound vs
compute-bound, and apply Amdahl's formula to stage fractions. The bottleneck
classification is reliable; the Amdahl speedup estimate requires real stage
fractions. Without empirical stage fractions (B300 measurement), the answer for
drama-3 is INSUFFICIENT_EVIDENCE, not a fabricated range. The skill encodes how
to go from that state to a defensible range once REMOTE measurements are taken.

**Q2. Does repository history provide actionable knowledge that a current source snapshot does not?**

Yes. The Magpie analysis shows that the registration pattern for a new provider
(which files to touch, what abstraction to reuse, that abstraction is introduced
post-feature not pre-feature) is not derivable from the current source alone —
it requires seeing the commit sequence. Repair latency data (median 1.54h) and
coupling patterns are also history-only. Whether this translates into measurable
task-success improvement requires the temporal-split benchmark, which is the
next experiment.

**Q3. Can we re-distill useful skills from repositories that already contain human-authored skills?**

The infrastructure to answer this exists (sibling workstream skill_distill.py).
The first pilot showed the distilled skill (`source-only sub-agent candidate`)
achieved the same task outcome as human and no-skill in one trial. This is
encouraging but INCONCLUSIVE. The `profiling-analyze` hide-and-re-distill
experiment is the correct test because the human skill encodes unrecoverable NPU
knowledge — if the distilled version covers the CANN field-aliasing rules and
silent-failure patterns, that is evidence of genuine value recovery.

**Q4. How should InferRSI distinguish imported knowledge, candidate skills, and promoted executable skills?**

Three distinct artifact kinds with separate locations and promotion criteria:
- **Imported knowledge** (`repo_packs/`, `skill_library/`): status = `imported`,
  `locally_verified = false`. Source-grounded reference material. Not executable
  instructions.
- **Candidate skill** (`evidence/<campaign-id>/plan/`): schema-validated bundle,
  3-5 alternatives, no evaluation verdict. Not in `skills/`.
- **Promoted skill** (`skills/`): passed the evaluation criterion on ≥3 tasks
  ≥2 repetitions with a PASS evidence tree. May be evolved but not downgraded
  silently.

**Q5. What evaluation evidence is required before promoting a distilled skill?**

At minimum: ≥3 Tier A tasks × ≥2 repetitions per variant (no_skill / human /
distilled), with `task_success(distilled) > task_success(no_skill)` and no
regression on correctness, zero inconclusive trials (or inconclusive trials
excluded from the success rate with explicit disclosure), and a complete evidence
tree under `evidence/<campaign-id>/`.

**Q6. What should be the next raw NPU repository to mine, and why?**

`Ascend/pytorch` first. It is the foundational kernel layer for Ascend NPU
development, predates all the MindIE-SD skills, and any skill distilled from it
would apply across models rather than being diffusion-specific. `op-plugin` is
second if the question is operator performance. `triton-ascend` is third for
Triton-native kernel writing. Clone sparse (only `.agents/` and relevant source
paths) and state the specific capability question before cloning.

**Q7. Which part of the current InferRSI substrate is the largest blocker to true skill/harness RSI?**

The skill evaluation pipeline requires a live agent (Codex or equivalent) that
can write to a workspace, which is environment-gated (the sibling workstream's
pilot recorded explicit rejected-distillation attempts due to sandbox write
restrictions before `danger-full-access` was configured). This is not a code
problem — the runner is implemented. It is an execution environment problem:
Tier B tasks require a real NPU, and the distillation loop requires a permissioned
sandbox. Until those environments are reliably available, all results will be
either Tier A only or INCONCLUSIVE due to environment, not algorithm.

---

## Status of each stage

| Stage | Status | Evidence |
|-------|--------|---------|
| 0. Audit InferRSI + PR #9 | Complete | This report |
| 1. Performance ceiling skill | Candidate | `skills/performance-ceiling-analysis/SKILL.md` |
| 2. Magpie evolution skill | Candidate | `skills/repository-evolution-analysis/SKILL.md` |
| 3. Skill factory design + lifecycle | Candidate | `skills/npu-skill-factory/SKILL.md` |
| 3.3 Human-skill corpus | Complete | 4 skills selected, `profiling-analyze` as Stage 3.4 candidate |
| 3.4 Hide-and-re-distill | Not started | REMOTE + sibling workstream runner required |
| 3.5 Skill evaluation contract | Defined | Inherited from sibling workstream |
| A/B/C pilot | 1 trial INCONCLUSIVE | `evidence/skill-bootstrap-20261014/` (sibling) |
| 4–8 SkillOpt cycle, raw NPU mining | Deferred | Blocked on evaluation baseline first |

---

## Remaining work (this branch)

1. Knowledge JSON records for `performance-ceiling-analysis` and
   `repository-evolution-analysis` should be added to `repo_packs/` once the
   skills pass evaluation — do not add them while status is `candidate`.
2. A knowledge record for the selected NPU corpus (CANN profiling methodology)
   should be drafted in `repo_packs/vllm_omni/knowledge/ascend/diffusion/`
   or a new component, following the PR #9 record format.
3. The Stage 3.4 distillation and evaluation run requires the sibling workstream's
   runner plus an NPU-accessible environment or a CPU-only Tier A Ascend task.
