# Grilling for an inference task

Adapted from Matt Pocock's [grilling skill](https://github.com/mattpocock/skills/blob/abeeaf95660ba9e8b7c753eb38f441ca707a8823/skills/productivity/grilling/SKILL.md),
revision `abeeaf95660ba9e8b7c753eb38f441ca707a8823`, under the
[MIT license](grilling-LICENSE). This adaptation keeps its decision tree,
frontier, rounds, agent-led fact finding and explicit confirmation, and bounds
the interview to decisions needed for the requested inference task.

## Build the decision tree

Map the task as decisions and their dependencies. The frontier contains only
decisions whose prerequisites are already settled. Ask that frontier in one
round, then wait for the user's answers and recompute it. A question depending
on an unanswered question belongs in a later round. Avoid a fixed questionnaire
or a fixed number of rounds; ask what can change the experiment or its acceptance.

Use these topics where they affect the user's task:

| Topic | Decisions worth resolving |
| --- | --- |
| Deliverable and target | Existing engine or another requested deliverable; fixed framework or alternatives allowed; target checkout and baseline |
| Workload | Representative requests, concurrency or arrival pattern, input/output sizes, modalities and important tail cases |
| Objective | Latency, throughput, memory or cost; priority among them; required service constraints and measurement scope |
| Quality | Existing oracle, precision, allowed approximations and what output changes are acceptable |
| Search space | Editable areas, dependency or deployment changes, upstream compatibility and maintenance preferences |
| Prior experience | Attempts already made, their conditions and evidence, failure reasons and conditions that could justify a retry |
| Budget and delivery | Allowed resources, time or cost, stopping conditions, final retest allowance and desired deliverables |

Discover repository and environment facts yourself. When delegation is available,
use a fresh-context subagent for independent fact finding; otherwise inspect
directly. An unresolved investigation is an unsettled prerequisite: continue
with independent questions while its dependent questions wait. Discovery does
not reserve a device or authorize a benchmark.

Treat a user's technical diagnosis as a hypothesis unless supporting evidence
establishes it. Treat an explicit user constraint as a constraint. If a new
answer contradicts an earlier one, surface the conflict before choosing between
them. Explain a recommended answer's reason and tradeoff so the user can disagree.

## Ask a round

Number the questions, explain their consequence, and give a supported
recommendation. For example:

```text
Q1 — Objective: Should we maximize throughput while preserving the current
tail-latency requirement? If so, what requirement and traffic cohort apply?
Recommendation: keep the existing service requirement, then optimize throughput
inside it. This makes a throughput improvement usable at the target load.
```

Use the host's question tool when suitable, or ask in the conversation. Wait for
the user's actual answer. A partial answer settles only the decisions it covers.
Explicitly delegated choices are settled with the recorded delegation and the
agent's resulting choice. A measurement still to be made remains unknown.

## Reach a shared understanding

Finish when no unresolved user decision can change the proposed first diagnostic
or experiment, quality contract, permitted search space or resource budget.
Every relevant branch must be settled, explicitly delegated, or deferred with a
reason showing that it does not affect the proposed next step. Unknown empirical
facts may become bounded calibration work; unknown acceptance thresholds are
not guessed. If quality cannot yet be assessed, state a diagnostic-only scope
and what evidence is needed before an optimization can be accepted.

Return to the entry's brief-and-confirm step. The user's confirmation of the
brief completes the interview and permits the existing workflow to proceed
within that scope. Later explicit user corrections, cancellation or a request
to switch modes take precedence over this procedure.
