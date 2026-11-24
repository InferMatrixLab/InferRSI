---
name: inferrsi-jiusi
description: Explicitly requested InferRSI-Jiusi interview to clarify an inference optimization task before running InferRSI. Use only when the user invokes this entry for the current task.
---

# InferRSI-Jiusi

Interview the user about the decisions that will shape an inference experiment,
then hand the confirmed task to [InferRSI](../inferrsi/SKILL.md). This entry is
opt-in for the current task; ordinary InferRSI keeps its existing workflow.
Discussing or quoting this entry's name is not an instruction to run it.

## Interview before execution

Read the bundled [grilling procedure](references/grilling.md) before asking the
first round. It supplies the decision tree, dependency-aware rounds and
completion rule; a separate grilling skill installation is unnecessary.

Start with the user's request, prior answers and accessible repository facts.
Inspect existing configurations, benchmark entrypoints and quality checks to
avoid asking the user for facts you can establish. Keep repository observations,
user-reported experience, preferences and unverified hypotheses distinct.
Follow the original entry's primary-skill selection before an inference evidence
search; reading guidance is preparation, not permission to execute it.

During the interview, use read-only investigation and discuss a proposed plan.
Candidate edits, campaign creation, measurements, service launches and device
work wait for the user's confirmation of the task brief. Resource rules still
apply after confirmation. If facts need measurements, record a calibration step
with its scope and budget rather than inventing the result.

Use the user's language. Ask each round's independent questions together and
wait for the answers before asking questions that depend on them. Include a
recommended answer and its tradeoff when evidence supports one. A recommendation,
silence or elapsed time is never a submitted answer. Reuse settled answers and
explicit delegation such as "you decide" instead of asking them again.

## Confirm the task

When the grilling procedure's completion rule is satisfied, use the
[brief template](references/brief-template.md) to state the agreed task in the
conversation. Adapt its fields to the actual deliverable. Preserve unknown
measurements and distinguish an approved diagnostic step from a qualified
optimization result. Ask the user to confirm or correct this concrete brief.

If the user corrects it, reopen the affected decisions and their dependents.
If the user explicitly switches to ordinary InferRSI or asks to skip the
remaining interview, honor that direction and carry settled answers forward;
ordinary InferRSI still resolves its own required inputs. Cancellation ends this
entry. Invocation does not create a persistent preference for later tasks.

## Continue through InferRSI

After confirmation, continue through [the original entry](../inferrsi/SKILL.md),
reading it now if it was not already loaded for read-only preparation. Use the
confirmed decisions. Resolve its existing launcher at
`../inferrsi/scripts/inferrsi.py` relative to this skill directory, while keeping
the working directory in the user's target workspace. The original entry's
`scripts/inferrsi.py` reference is relative to its own directory.

Carry the brief into the existing task instructions and protocol inputs as
appropriate. The brief is a record of intent; actual measurement and quality
scripts must implement the accepted checks. Preserve the original primary-skill
selection, knowledge condition, candidate assessment and independent final
evaluation. A frozen benchmark's task and gates remain the benchmark's inputs;
the interview may resolve allowed configuration, not rewrite that task.

Run the interview once for this task. Revisit decisions when a material goal or
constraint changes; follow the existing workflow for changed frozen protocols.
Retain useful user experience as attributed context and test its applicability
with measurements. Report actual execution and quality evidence through the
original workflow. Faster convergence is a hypothesis, not a result of merely
completing the interview.
