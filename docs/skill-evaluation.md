# Bounded skill evaluation

Skill evaluation measures discovery, correct application and task outcomes for an
exact knowledge revision. It is separate from the numeric engine-performance
evaluator and from InferRSI's L0–L4 system-validation ladder.

The small report-audit driver reuses `KnowledgeReader` bundles, the real Codex
CLI and `infra.executors.local.execute_command`. It adapts the sibling pilot's
fresh-session, event and independent-verifier methods; its old fixed
no-skill/human/distilled controller is not imported. No external evaluation
platform source is copied. Existing knowledge retains its source/license limits.

## Conditions and outcomes

| Condition | Exposure | Purpose |
| --- | --- | --- |
| N | No target instructions or resources | Same-client baseline |
| E-benchmark / E-evidence | One explicit, complete reader bundle | Attribute each skill's effect separately |
| R | Both skills through native `.agents/skills` discovery | Observe relevant, ambiguous and irrelevant activation |

Each trial starts a fresh ephemeral client and workspace. Global/bundled skills,
plugins, apps, memory and web are disabled for that client only. For this pilot,
the owner explicitly authorized relaxed host isolation after native Windows
isolation failed. Local commands have broad access: this is controlled knowledge
exposure, not OS-enforced read confinement. Keep known knowledge copies,
verifiers/answers and other trials outside the task workspace; list their roots
with `--protected-root` for the access audit. Invalidate observed exposure to them.
Unobserved/implicit exposure remains a limitation of the causal comparison.

Skill bundles keep their original relative paths and declared shared resources.
Other cross-skill navigation is not automatically made available. Skill identity,
content revision and resource/dependency revisions come from the existing reader.

Agent execution status and trial verdict are separate. Completed wrong or missing
answers fail; timeouts, client errors and unavailable verification are
INCONCLUSIVE. Rejecting a bad performance report can correctly pass an agent
task. Missing token/cost observations stay unknown. Cached input is a subset of
input tokens, not an additional charge. Paired regressions and recoveries remain
visible, including neutral/negative results.

## CPU checks and paid execution

After the normal development setup, with checkout `src` on `PYTHONPATH`:

```console
pytest tests/test_skill_evaluation.py
python tools/skill_eval_pilot.py prepare --output <PRIVATE_OUTPUT> --model <EXACT_MODEL> --effort <EFFORT> --protected-root <KNOWLEDGE_AND_EVIDENCE_ROOT>
```

`prepare` writes a plan without model calls. Review and record its digest, budget
and revisions in the governing Issue before execution. Keep private output
outside the source checkout and audit accesses to the listed knowledge/history
and answer roots. Then the separately authorized call is:

```console
python tools/skill_eval_pilot.py execute --output <PRIVATE_OUTPUT>
```

Use `--max-new-trials 1` for the first real development trial. Reinvocation resumes
unattempted entries without retrying completed or incomplete calls. A client
execution failure stops scheduling until its cause is investigated. Campaign
time and observed-token limits carry across resumptions; the token threshold
stops new trials after recorded usage reaches it, rather than imposing a provider
generation limit. Unavailable billing cost stays unknown.

Default tests use deterministic fixtures; no CI model calls or new CI lane is
introduced. Fixture latency arrays reuse the historical Qwen review summary.
Counterfactual metadata is explicitly labeled as a test fixture, never as a new
GPU result. Two development instances and four sealed instances are selected
before calls. Do not tune skills or gates on the final held-out results.

The initial development campaign exposed a task-contract ambiguity: agents could
correctly reject a kernel-to-service claim while using FAIL where the hidden
oracle expected INCONCLUSIVE. Preserve those original calls and verdicts as
development diagnostics; they are not skill-harm evidence. Revised task inputs
state verdict and output-field semantics explicitly. `prepare --final-only`
selects four revised instances with a distinct historical baseline slice and
three R checks; two final instances repeat twice and two once (21 calls). Freeze
the revision and remaining `--campaign-seconds` / `--token-limit` before those
calls. Keep original and revised contracts separate and respect the Issue's
combined call cap; do not silently reinterpret old outputs.

The verifier runs outside the agent command sandbox and never executes generated
code. It checks structured answers, numeric results, findings and evidence keys.
Raw client captures remain private. Publish reviewed redacted evidence with its
own identity, per-trial outputs/checks, source revisions, missing observations,
resource definitions and a reproducible verifier invocation. A small pilot is
descriptive evidence for that skill/task/client/model, not automatic promotion or
a hardware performance claim.
