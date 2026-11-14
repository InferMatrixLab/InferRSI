---
name: skill-evolution-playbook
description: 'Practical design choices for evolving agent skills from execution traces: when one trajectory should update a skill, how conflicting lessons are handled, how negative evidence is preserved, how large an edit should be, and when skills should split or merge. Drawn from Trace2Skill and SkillOpt. Use when designing or operating a skill evolution pipeline.

  '
---

# Skill Evolution Playbook

Status: candidate. Repository-derived notes record Trace2Skill @ 3d0b52a
and SkillOpt @ 343db229; the earlier Trace2Skill attribution to 7e5a1d77 belongs
to LearningToCommit and does not establish that implementation's behavior.
The [reviewed paper ledgers](../../workflows/npu-skill-factory/references/papers-20261015/references/readset.md)
keep Trace2Skill v5 and SkillOpt v2 separate from these repository pins. No
paper-to-code equivalence or local efficacy is established.

## When should one trajectory update a skill?

A single trajectory can motivate a scoped case or amendment proposal. Diagnose
its causal failure first and retain successful behavior the amendment must
preserve. Neither an anecdote nor agreement among analysts establishes efficacy.
No universal minimum trace count follows from these papers.

Trace2Skill's reviewed paper describes evidence-pool analysis and consolidation;
SkillOpt separates proposal generation from independently evaluated acceptance.
Consolidation produces a coherent candidate, not a replacement decision. Keep
final-test partitions outside edit selection, check combined effects and
unrelated-success regressions, and retain the incumbent for rollback. A tie or
uncertain result must not be reported as improvement.

See [Trace2Skill evidence](../../workflows/npu-skill-factory/references/papers-20261015/references/trace2skill.md),
[SkillOpt evidence](../../workflows/npu-skill-factory/references/papers-20261015/references/skillopt.md)
and [interaction counterexamples](../../workflows/npu-skill-factory/references/papers-20261015/cases/methodology-counterexamples.md).

## How are conflicting lessons handled?

Two trajectories can encode contradictory lessons: one shows approach A works,
another shows approach A fails.

**Trace2Skill's approach:** parallel multi-agent patch proposal followed by
hierarchical conflict-free consolidation. The `skill_evolver` agents each
propose section-level patches (`insert_after`, `replace_in_section`,
`add_section`, etc.); the consolidation step identifies conflicting edits to
the same section and resolves them through a separate consolidation model call.
Source: `skill_evolver/skill_evolving_agent.py`, `_SUPPORTED_PATCH_OPS` (historical code locator; pin attribution unresolved, not reverified).

**Practical resolution strategies:**
1. **Context-condition the lesson.** If A works in context X but fails in
   context Y, the skill should encode both as conditional: "When X, do A.
   When Y, avoid A." This is better than choosing one and losing the other.
2. **Separate sections.** Conflicting lessons often target different conditions.
   Add a "known failure modes" or "does not apply when" section rather than
   overwriting the "procedure" section.
3. **Escalate to human review.** When the conflict cannot be resolved by
   conditioning (the same context genuinely produces different outcomes across
   runs), record it as INCONCLUSIVE and flag for human review. Do not resolve
   by voting on whichever outcome appeared more often in the pool.

## How is negative evidence preserved?

**SkillOpt:** rejected candidate edits are stored in the staging area with
their evaluation result before being discarded. The staging state records
what was tried and why it was rejected.
Source: `skillopt_sleep/staging.py` @ 343db229.

**Trace2Skill:** error traces are analyzed separately from success traces, and
both pools contribute to the consolidated edit. Error-driven evolution produces
failure-mode additions to the skill; success-driven evolution adds positive
procedure refinements. Neither is discarded.
Source: Trace2Skill `run_parallel_skill_evolution.py` (error traces) vs
`run_parallel_combined_skill_evolution.py` (combined success+error traces) (historical code locator; pin attribution unresolved, not reverified).

**What to preserve in a rejection record:**
```yaml
rejected_edit:
  proposed_change: <what was changed and in which section>
  hypothesis: <why we thought this would help>
  held_out_result: <metric before → metric after>
  verdict: FAIL or INCONCLUSIVE
  evidence_level: <how many trajectories / what held-out set>
  context: <model, hardware, workload, task distribution>
  date: <ISO date>
```

A rejection record is editing context: keep incumbent/candidate identities,
target conditions, measured outcome, suspected cause and a retirement condition.
Store it with the corresponding evaluation evidence, outside the deployed task
procedure. Rejection constrains that comparison, not all future uses of an idea.
Protected guidance can be revised explicitly when its supporting evidence expires.

## How large should a skill edit be?

**SkillOpt's bounded edit:** modifications are restricted to specific sections
(`procedure`, `failure_modes`, `knowledge_sources`). The `clip.py` module
enforces a length budget: the candidate must not be substantially longer than
the current skill. The `revision.parent` field tracks the lineage so v0→v1→v2
is reconstructible.
Source: `skillopt/optimizer/clip.py`, `skillopt/optimizer/skill.py` @ 343db229.

**Trace2Skill's section-level patches:** edits target named sections with
specific operations. `replace_in_section` replaces content within a section,
`insert_after` adds content after a named anchor. Protected files (`LICENSE.txt`,
`recalc.py`) cannot be modified regardless of what the patch proposes.
Source: `skill_evolver/skill_evolving_agent.py` PROTECTED_FILES, PATCH_OPS (historical code locator; pin attribution unresolved, not reverified).

**Practical size rule:** bound the target passage and intended behavior before
editing, inspect the actual diff, and preserve rollback state. Paper-specific
section counts and length budgets are not universal defaults. Changing a skill's
scope requires explicit review of its identity and consumers; consolidation or
splitting is justified by distinct workflows and observed interactions, not an
arbitrary word count.

## When should skills split or merge?

**Split a skill when:**
- The `procedure` has grown to cover two distinct workflows that rarely co-occur.
  The signal: most trajectories use only the first half or only the second half,
  rarely both.
- Two distinct `applicability` conditions consistently produce conflicting lesson
  proposals. The conflict is structural, not resolvable by conditioning.
- Agents repeatedly need only a separable workflow with its own trigger and
  evidence contract; length alone is not a split criterion.

**Merge skills when:**
- Two skills consistently co-activate (every trajectory that uses skill A also
  uses skill B, with little overlap with other skills).
- One skill's `procedure` duplicates a large portion of another's.
- The two skills' `applicability` conditions are indistinguishable in practice.

**What to version when splitting:**
The original skill becomes deprecated (v_last) with a forward pointer to both
new skills. Both new skills start at v0 with `revision.parent = <original_skill_id>`.

## Skill deepening vs skill creation

Trace2Skill studies two modes:
- **Self-deepen:** start from an existing human-written skill; use traces to
  refine procedure, add failure modes, and extend coverage.
- **Self-create:** start from a minimal draft (e.g., name + description only);
  build up from error traces.

Neither mode is universally superior. A relevant incumbent offers useful
structure, but model/harness-specific regressions and task-conditioning matter.
Prefer an amendment when the existing skill owns the workflow; create a new
candidate for a genuinely distinct capability. See the reviewed Trace2Skill v5
ledger and its human-skill/small-model counterexample before claiming transfer.

## Task solver and improver are different claims

Use the [adaptation-interface records](../optimization-search-policy/references/papers-20261015/knowledge/adaptation-interfaces.md)
for Dream-RSI replay support, AIDE²'s separate inner/private/outer evaluation
boundaries and JitRL's candidate-scoring prerequisites. A stronger task-solving
agent is not automatically a stronger improver. The AIDE² improver comparison
remains inconclusive; later checkpoints can regress on individual held-out domains.
Replay rankings and private inner scores are not untouched outer generalization
evidence. These records enable no execution interface or persistent memory store.

## What should be versioned?

- The skill document itself (`SKILL.md`) at each accepted version.
- The trajectory pool or trace IDs that motivated each edit.
- The held-out evaluation result (metric before → after) for each accepted edit.
- Rejected candidates and their evaluation results.
- The `revision.parent` chain so the full lineage is reconstructible.

What does NOT need to be versioned separately:
- The raw agent trajectories (store a reference/ID, not a full copy).
- Intermediate patch proposals that were not accepted.
- The evaluation harness configuration (that is versioned separately in the
  benchmark/evidence tree).
