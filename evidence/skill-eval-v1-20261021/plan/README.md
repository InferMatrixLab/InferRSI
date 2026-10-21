# Frozen report-audit pilot

Governing acceptance: [InferRSI #40](https://github.com/InferMatrixLab/InferRSI/issues/40).
The human delegated implementation, testing, independent review and integration
to the accountable Codex agent, retaining final Issue acceptance/closure.
Scope is two existing skills and one CPU-verifiable task family, not an
evaluation platform or a hardware experiment.

## Reuse and callable path

- `KnowledgeReader.read("checkout:<id>")`: exact identity, bundle bytes and
  declared resource/dependency revisions. No new catalog/store/matrix.
- `CodexClient.command(...)` → `infra.executors.local.execute_command(...)`:
  real `codex exec`, ephemeral session, JSON events, final structured artifact,
  bounded runtime and process cleanup. Existing numeric performance evaluation
  is not repurposed as artificial task-success scores.
- `tools/skill_eval_pilot.py prepare|execute`: small orchestration seam;
  `tools/skill_eval_verifier.py`: independent CPU artifact checks.
- The sibling `npu-skill-factory` pilot informed fresh-session, frozen-verifier
  and cost reporting methods. Its old no-skill/human/distilled controller and
  external evaluation platform source were not copied. No new dependencies,
  service, CI lane or license-bearing external implementation were introduced.

## Comparison and gates

N receives the task; E-benchmark/E-evidence receives the same task plus one exact
complete skill bundle; R receives both through native `.agents/skills` discovery.
The same client/model request, tools, task input and deadline apply. Input
hashes detect edits. Expected answers and the verifier stay outside the task
workspace. The verifier reads JSON only and does not execute model code.
Conditions are counterbalanced and paired on task/repeat. Seeds are not exposed
by this client. Provider cached input is recorded, not treated as a fresh output.

The task audits historical latency slices with explicitly counterfactual
metadata. Its own frozen contract specifies the gain, quality, all-request,
scope and spread requirements. Each valid comparison uses the median of the
per-trial request means; a lower-quality or incomplete report must not pass.
Correctly rejecting a report can pass the agent task. The fixed fixtures all
satisfy the spread gate; the verifier is not a general benchmark-policy engine.
Manual review separately checks reasons, smallest next actions and actual skill
application. No LLM preference score or copied trajectory is the outcome oracle.

## Retained development and revised final phase

The [v1 freeze](https://github.com/InferMatrixLab/InferRSI/issues/40#issuecomment-6319880610)
preceded all task calls. Nine of its 33 scheduled calls were attempted before a
contract ambiguity was diagnosed; original strict verdicts are preserved. The
[clarification](https://github.com/InferMatrixLab/InferRSI/issues/40#issuecomment-6320268599)
states report-verdict, numeric-null and scope meanings for every condition.
Neither skill content nor the verifier changed. The
[v2 freeze](https://github.com/InferMatrixLab/InferRSI/issues/40#issuecomment-6320399836)
precedes the revised final instances: different historical baseline values,
four audit types (18 N/E calls) and three native discovery probes. These are
revised final instances of the same task family, not independent new task types.
No skill was selected or tuned using final outcomes.

Combined ceiling: 33 task calls, 5,400 campaign seconds and 3,000,000 observed
input-plus-output tokens. The revised phase reserves 21 calls / 3,600 seconds /
2,000,000 observed tokens. No automatic retries. The token threshold stops new
calls after observed usage reaches it, rather than limiting provider generation.
Unobserved interrupted usage and billing cost remain unknown. Two separately
recorded readiness calls are not efficacy trials.

## Isolation and publication

The human explicitly allowed relaxed isolation after native Windows confinement
failed. Fresh workspaces/sessions and local client-only disabling of global and
bundled skills, plugins, apps, memory and web control exposure. Broad host file
access remains possible. Protected roots are audit metadata, not enforcement.
Observed out-of-workspace/answer/target leakage invalidates that trial;
unobserved or implicit exposure remains a causal limitation.

`protocol-v1.json` / `protocol-v2.json` are labelled redacted plans with original
private digests. Task/schema/verifier bytes retain their original identities.
Each public trial includes reconstructed task bytes (checked against the saved
input hash when present), original answer bytes, checks and redacted command
excerpts. Raw service/session events, host paths and process identifiers remain
in private originals; excerpt truncation is explicit. Public copies have their
own `integrity.json`. This bundle cannot reproduce private service execution or
attest unseen host access.
