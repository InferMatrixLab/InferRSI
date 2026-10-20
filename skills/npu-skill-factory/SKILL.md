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

## Design detail (historical, not implemented here)

The full historical design records — the sibling bundle schema
(`schemas/skill-bundle.json`, not present in this repository), the selected
NPU corpus with license status, the Stage 3.4 hide-and-re-distill procedure
(its `omnirsi.harness.skill_distill` entrypoint is a sibling-workstream
prototype, also not in this repository), the Stage 3.5 three-variant evaluation
contract with its SkillOpt-derived accept criterion, the revision-lineage
layout and the Phase 1 evolution cycle — live in
[skill-factory-design-20261014.md](references/skill-factory-design-20261014.md),
preserved verbatim with their sources.

Boundaries that still hold from that design:

- The sibling pilot (one Tier A task, all three variants passing) established no
  statistical difference; promotion remains INCONCLUSIVE.
- Tier A tasks are CPU/static only; Tier B tasks require an NPU device.
- Do not promote based on token cost alone; record skill build cost separately
  from per-task runtime benefit.

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
