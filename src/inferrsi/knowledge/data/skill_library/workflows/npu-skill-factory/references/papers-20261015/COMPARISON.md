# Comparison: choose the artifact before choosing the learning method

All destinations below are P, candidate/not_run. The underlying F records and exact paper locators are in the linked ledgers.

| Source | Distinct evidence contribution beyond the prior repository summaries | Best-fit artifact decision | Main boundary |
|---|---|---|---|
| [Repo-To-Skill v1](references/repo-to-skill.md) | Distinguishes source-anchored construction from task-conditioned pools; verification and construction cost are separate from downstream score | Existing factory's evidence/admission contract; retain a source-local case when the reusable workflow is not established | The benchmark gains are not a controlled test of the entire public repository library |
| [Learning to Commit v1](references/learning-to-commit.md) | A historical expert patch is a contrastive reference for the agent's own attempted change | Repository-scoped persistent knowledge, or a revision/deprecation of an existing convention | Chronology prevents the specified adaptation leakage, not every possible contamination path; accepted code is not necessarily the unique correct solution |
| [Trace2Skill v5](references/trace2skill.md) | Separates causally investigated errors from successful procedures; studies interactions among patches | Consolidated procedural knowledge and a candidate update to an existing skill | Faster parallel construction is not proof of lower aggregate compute or reliable routing to the skill |
| [SkillOpt v2](references/skillopt.md) | Separates proposed edits, accepted skill state, rejected-edit history, and optimizer-only memory | A bounded change proposal with an independent acceptance decision | Selection improvement is neither a formal generalization guarantee nor a permission to deploy |

## P — Artifact selection rule

- **Case:** preserve a bounded observation when the source is singular, applicability is uncertain, the explanation is unverified, or a negative example is most informative. Store the original outcome and alternatives; do not silently turn it into a universal instruction.
- **Persistent knowledge:** retain a stable source contract or a supported reusable relationship. State repository/model/harness/version scope and evidence strength. A procedural claim can remain knowledge until a reliable trigger and validation contract exist.
- **Bounded update:** choose this when a current skill already owns the workflow and the evidence supports a specific correction. Identify the exact incumbent version, target passage, expected behavioral change, possible regressions, and rollback. No current body means no literal patch application.
- **New skill:** choose this only for a separately triggerable, materially distinct workflow with inputs, procedure, constraints, outputs, and checks. A new paper, repository, or failure does not by itself justify a new skill.
- **No promotion:** keep the item as a case or knowledge record when causality, scope, source integrity, or the evaluation signal is insufficient.

## P — Reconciliation rather than a universal winner

Broad offline consolidation and cautious incremental editing solve different problems. Use consolidation to assemble a coherent candidate from an independent evidence pool. Use bounded updates to preserve an incumbent whose value is already known. The combination is a proposal here; none of these four papers establishes that this combined policy is optimal for InferRSI.

A historical merge, static documentation check, execution correctness check, held-out behavioral win, and cross-model transfer result answer different questions. Keep separate fields for each rather than a single “verified” flag. Make source availability and empirical validity independent of whether an artifact has been extracted.

## P — Cost decision

Record construction cost, candidate-selection cost, deployment context cost, and downstream task cost separately. Amortization is a workload hypothesis: benefit across future uses must exceed one-time construction plus repeated context/selection cost. Faster wall time, a small exported file, or fewer accepted edits alone does not establish that inequality. This pack does not select an optimizer, compute budget, or hardware target.
