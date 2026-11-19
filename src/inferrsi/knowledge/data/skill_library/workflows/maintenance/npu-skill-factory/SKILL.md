---
name: npu-skill-factory
description: 'Design and operation of the InferRSI NPU skill factory: artifact lifecycle, skill evaluation contract, corpus selection, hide-and-re-distill procedure, and skill evolution cycle. Use when deciding where new skill artifacts belong, how to distill a candidate skill, or how to run the No-Skill vs Human-Skill vs Distilled-Skill comparison.

  '
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "status": "candidate",
      "sources": [
        {
          "url": "https://github.com/VectorSpaceLab/AREX-Skill",
          "commit": "ac3fe1af",
          "paths": [
            "docs/disco-meta-skills.md",
            "docs/disco-workflows.md",
            "src/disco/skills/create-paper-module-skill/SKILL.md",
            "src/disco/skills/create-paper-module-skill/scripts/create_skill_skeleton.py",
            "src/disco/skills/create-paper-module-skill/scripts/validate_skill_tree.py",
            "src/disco/modes/skill-policy.ts",
            "src/core/repo-skills-library-manager.ts"
          ],
          "type": "git",
          "revision_precision": "prefix"
        },
        {
          "url": "https://github.com/SkillOpt/SkillOpt",
          "commit": "343db229",
          "paths": [
            "skillopt/evaluation/gate.py",
            "skillopt/optimizer/skill.py",
            "skillopt/optimizer/clip.py",
            "skillopt_sleep/cycle.py",
            "skillopt_sleep/harvest_sources.py"
          ],
          "type": "git",
          "revision_precision": "prefix"
        },
        {
          "url": "https://github.com/WillowMindIE/MindIE-SD",
          "commit": "8481d39b",
          "paths": [
            ".agents/skills/profiling-analyze/SKILL.md",
            ".agents/skills/dit-perf-opt/SKILL.md",
            ".agents/skills/perf-gate/SKILL.md",
            ".agents/skills/dit-parallel-opt/SKILL.md"
          ],
          "type": "git",
          "revision_precision": "prefix"
        }
      ],
      "verification": {
        "locally_verified": false,
        "evidence_level": "source_grounded",
        "note": "Historical repository extraction and sibling schema at 82218b4, not a current local factory implementation. Reviewed paper additions and exact versions live in references/papers-20261015/references/readset.md and docs/reference-matrix.md; no efficacy or paper-to-code equivalence established."
      },
      "applicability": {
        "scope": "InferRSI skill lifecycle management",
        "prerequisites": "Current candidate inventory and source/evaluation evidence; historical sibling execution interfaces are not required for read-only artifact admission",
        "input_contract": "A candidate inventory plus the source and evaluation evidence for each candidate skill; read-only artifact admission needs no historical sibling execution interface",
        "produced_artifact": "An admitted or refused skill candidate with its source, evidence and limitation record, and its stable id and owning path",
        "failure_modes": [
          "A candidate admitted on an inventory line without source or evaluation evidence",
          "A stable id or path assigned twice across owners",
          "Indexing or admission reported as validation or promotion",
          "Paper-to-code equivalence asserted without a pinned readset"
        ],
        "refusal_point": "Refuses admission when a candidate has neither source evidence nor a declared evaluation state, and records the refusal instead of leaving the field blank"
      },
      "recommendations": [
        "Read the methodology counterexamples in references/papers-20261015/cases/ before admitting a candidate derived from a paper.",
        "Keep the source snapshot revision as research evidence; it is not a campaign default.",
        "Record an unvalidated candidate as candidate with not_run rather than omitting the state."
      ],
      "tags": [
        "skill-factory",
        "distillation",
        "evaluation",
        "npu",
        "ascend"
      ],
      "profile": "local-skill-v1",
      "kind": "skill",
      "origin": [
        "external"
      ],
      "empirical_validation": "not_run",
      "limitations": [
        "Source-derived candidate; no local efficacy validation."
      ],
      "provenance_readsets": [
        "references/papers-20261015/cases/methodology-counterexamples.md",
        "references/papers-20261015/COMPARISON.md",
        "references/papers-20261015/INTEGRATION_NOTES.md",
        "references/papers-20261015/knowledge/evidence-routing.md",
        "references/papers-20261015/QA.md",
        "references/papers-20261015/README.md",
        "references/papers-20261015/references/learning-to-commit.md",
        "references/papers-20261015/references/protocol-details.md",
        "references/papers-20261015/references/readset.md",
        "references/papers-20261015/references/repo-to-skill.md",
        "references/papers-20261015/references/skillopt.md",
        "references/papers-20261015/references/trace2skill.md",
        "references/papers-20261015/UNREAD_LEADS.md",
        "references/papers-20261015/updates/bounded-updates.md"
      ],
      "consumption_mode": "packaged",
      "searchspace_not_applicable": "SKILL.md §§ Choose the evidence product, Artifact lifecycle, and What this skill does not do define skill-distillation/evaluation methodology; NPU task tiers are evaluation prerequisites, not a hardware-resource mechanism."
    }
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

Current candidate bundles live under `src/inferrsi/knowledge/data/skill_library/<category>/<name>/`,
with linked references and cases under their owning skill. The library's
`skill-index.json` maps stable skill names to those category paths. Exactly two primary matrices record provenance
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
`skill_library/` tree includes explicitly labeled candidates. A candidate without an
authorized evaluation trail remains unvalidated regardless of packaging.

**Where each artifact belongs:**

| Artifact | Location | Format |
|----------|----------|--------|
| Knowledge records (experience) | `src/inferrsi/knowledge/data/skill_library/records/<stable-id>.json` | Validated JSON (catalog.py schema) |
| Bilingual skill library | `src/inferrsi/knowledge/data/skill_library/en/<repo>/` and `zh-CN/<repo>/` | SKILL.md + references/ + scripts/ |
| Skill bundle (distillation output) | `evidence/<campaign-id>/plan/agent-source-candidates/` | schema-validated JSON bundle |
| Human reference skill | `evidence/<campaign-id>/plan/human-<name>/SKILL.md` | SKILL.md + references/ |
| Candidate skill under evaluation | `evidence/<campaign-id>/plan/agent-source-candidates/<name>/` | SKILL.md + references/ |
| Promoted skill | `skills/<name>/SKILL.md` (including metadata) | InferRSI skill format |
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
preserved with their sources and the two sibling-prototype entrypoints annotated.

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
