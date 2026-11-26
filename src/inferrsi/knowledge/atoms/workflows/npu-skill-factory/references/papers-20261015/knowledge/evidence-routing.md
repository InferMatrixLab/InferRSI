# Candidate knowledge: evidence-to-artifact admission

Status: candidate. Validation: not_run. All rules in this file are P, proposed for reconciliation with existing methodology artifacts. The four [paper ledgers](../COMPARISON.md) provide the F basis; this is a synthesis, not an implementation reproduced from one author.

## Objective and assumptions

Retain evidence at the narrowest useful abstraction without losing counterexamples, increasing instruction conflicts, or claiming behavioral improvement that has not been measured. Assume the source identity and its inspected boundary are known. If they are not, retain a lead rather than authoritative knowledge.

## Decision variables and constraints

Choose artifact type, scope, owner, applicability trigger, evidence strength, and revision boundary. Constraints are the actual task contract, source version, authorized actions, known counterexamples, and whether the current incumbent can be inspected. Artifact count, repository popularity, and the number of source files are not objectives.

## Proposed decision procedure

1. **Identify the evidence unit.** Is it a versioned API/implementation contract, an expert's accepted historical diff, an individual execution, a repeated pattern, or an aggregate controlled evaluation? Do not combine them into an undifferentiated confidence score.
2. **Preserve the case first when necessary.** Capture the input/state, observed behavior, outcome, comparator, and alternatives. Separate direct observation from the proposed cause. A log message alone can identify a lead without establishing the cause.
3. **Determine whether generalization is supported.** A versioned contract may justify scoped knowledge directly. An empirical behavior needs recurrence or an intervention consistent with the proposed cause. A source-local exception can remain a case even when it challenges a general rule.
4. **Check ownership and overlap.** Read the current relevant skill body. If it already owns the trigger and procedure, propose a localized correction or reference. If its body is unavailable, provide a semantic amendment specification and defer literal patching. Do not create a second skill merely to avoid the missing comparison.
5. **Select the smallest durable representation.** Put stable preconditions and decision rules in knowledge; put uncommon examples in cases/references; put broadly reused procedure in an existing skill. Create a new skill only if a distinct workflow remains unowned.
6. **Define acceptance separately.** Static coherence, source fidelity, functional correctness, behavioral improvement, and transfer have separate evidence statuses. A source-derived candidate may be useful before empirical testing, but must keep not_run and unresolved branches visible.
7. **Preserve rejection and expiry.** Record what change was tried, which scope it targeted, why it was rejected, and when the evidence stops applying. Do not generalize “failed here” into a timeless ban. Conflicting newer evidence can narrow, replace, or retire a rule.

## Required information, not a new schema implementation

- Source/version and exact evidence locator; read versus inferred status
- Evidence unit and provenance lineage; independent examples versus correlated copies
- Applicable task, repository, model, harness, and environment conditions
- Claimed mechanism and plausible alternative explanation
- Expected benefit plus construction, selection, context, and downstream cost dimensions
- Known negative cases and disallowed extrapolations
- Current artifact owner and proposed operation: retain case, add knowledge, revise, deprecate, or create
- Verification already available versus future checks; outcome stays not_run where appropriate

These are editorial requirements. This pack does not add a catalog, database, router, evaluator, optimizer, installer, or scheduled update mechanism.

## Resource benefit and cost

Potential benefit is less repeated rediscovery and fewer conflicting instructions. Cost includes investigating causes, retaining provenance, deduplicating, and evaluating candidate changes. Selective reading can reduce context burden, but instruction-guided agents may also perform more work. No break-even point is known for InferRSI.

## Limits and counter-signals

- More repeated text can reflect shared prompts or duplicated cases rather than independent evidence.
- A maintainer-approved historical patch may encode a temporary compromise rather than a lasting convention.
- A higher aggregate score may hide correctness, task-contract, latency, or subgroup regressions.
- A protected text region helps preserve editing boundaries but can also preserve an outdated rule; it still needs a revision authority and expiry test.
- An edit-count cap does not cap the number of behavioral changes. Inspect the actual replacement and retain a reversible incumbent.
- Test-set separation alone does not prove causal mechanism; matched controls and alternate explanations still matter.

## Output for this pack

The justified output is one admission-policy knowledge note, counterexample cases, and bounded update specifications for existing artifacts. No new skill and no empirically promoted update are warranted by the inspected evidence alone.
