# Yibuapi Skill Eval access preflight

Refs #101. This is a proposed integration design, not a configured execution
environment or evidence of a successful model call. The owner approved a single
smoke with a total CNY 10 limit including preflight, without automatic retries.
Effective pricing, enforceable provider-side spending control, credential setup
and the newly frozen exact plan remain prerequisites.

## Confirmed interface and remaining compatibility question

The provider's [model configuration example](https://yibuapi.apifox.cn/9557607m0)
names `claude-opus-5-5` under an Anthropic provider at
`https://yibuapi.com/v1`. Its [Messages reference](https://yibuapi.apifox.cn/6777246m0)
documents `POST /v1/messages`, `x-api-key`, an `anthropic-version` header,
`tool_use` / `tool_result`, stop reasons and token/cache usage.
Another [function example](https://yibuapi.apifox.cn/382404323e0) uses Bearer auth
and contains an OpenAI-shaped response example. These documents do not establish
that every model/group implements the same protocol correctly.

A credential-free public read of [the pricing catalog](https://yibuapi.com/api/pricing)
on 2026-10-27 returned this exact model with endpoint types `anthropic` and
`openai`, model ratio 2, completion ratio 5, cache ratio 0.05 and cache-creation
ratio 1.25. Enabled groups include default, claude-code and claude-code-pro
(public group ratio 2), plus other groups with different ratios. These are
catalog ratios, not independently established CNY-per-token prices or a
confirmation of the owner's effective group. The [pricing page](https://yibuapi.com/pricing)
and [provider usage guide](https://yibuapi.apifox.cn/8994238m0) identify model/group
rates, but the static page read did not expose currency/unit conversion or hard
quota enforcement semantics.

No model endpoint, key validation or paid preflight was called. Model-specific
tool round trips, output schema behavior, usage completeness and actual billing
remain unverified. Generic Responses support does not prove Codex agent,
streaming or output-schema compatibility.

## Smallest proposed client boundary

Keep the current CodexClient command, config isolation and trace parser unchanged
for existing plans. Introduce an opt-in Anthropic Messages agent client, reusing
the existing process deadline, trial directories, verifier, receipts, paired
schedule and retained-result publisher. Do not replace an agent trial with a
single plain chat completion.

The agent would expose only bounded list/read operations over the prepared
workspace and a structured answer submission tool. A successful task.json read
and subsequent tool-result round trip must precede final submission. The
workspace contains only the validated case and that arm's selected bundle.
There are no shell, write, web, subprocess, plugin, memory or external-agent tools.

Use non-streaming Messages first. Each request is sent once; HTTP failures,
uncertain responses and timeouts terminate the attempt without replay or model
fallback. Enforce request count, serialized input bytes, complete-file read
bytes, output-token limits, tool count and the existing whole-trial deadline.
Reject symlinks, traversal, unexposed paths, malformed/ambiguous protocol data,
unexpected model identities, unsupported schemas and premature answers. An
oversized resource fails explicitly rather than being silently truncated.

Retain a distinct agent trace: bounded request hashes/lengths, normalized tool
reads and hashes, terminal status, provider-reported model, token/cache
observations and errors. Do not label provider events as Codex trace events.
Normalize Anthropic total input from uncached input plus cache read/creation;
missing usage stays unknown and stops further paid requests. Preserve an
interrupted attempt as consumed and incomplete evidence as INCONCLUSIVE.

## Frozen identity and authorization

A new plan must bind client kind/protocol version and source hash, provider,
endpoint/auth scheme/API version, model and reported-model policy, selected
provider group, every agent bound, sampling/thinking policy and the complete
monetary limit/control evidence. Both absent/old and new arms use the same
identity. No mapping from Codex `xhigh` to this model is assumed.

Keep exact case/split/schema/grader and both bundle identities, holdout
separation, verifier and artifact/source-run provenance. A changed client,
settings, renderer/adapter hash or trusted implementation requires a new freeze
and exact approval. Previous Codex plans/approvals cannot authorize this model.
Do not rewrite or relabel retained results.

Default mapping and hosted execution remain unchanged by this design. Current
hosted execution checks only `codex --version`; conditional provider preflight,
credential injection and new client selection need their own reviewed
implementation before any hosted provider run.

## Proposed credential destination and payload

After action-time security approval, the owner would provision a dedicated,
single-smoke provider key as GitHub Actions Secret `SKILL_EVAL_YIBUAPI_KEY`.
Map it to the same environment name only in the model execution step. The key
is sent only in the authentication header to
`https://yibuapi.com/v1/messages`; it is never a command argument, plan field,
trace, artifact or comment. Do not read or reuse existing auth/config stores.

Provider/model/group/endpoint/settings belong in the frozen plan, not mutable
ambient overrides. Keep GitHub publication credentials out of the model process.
Do not configure the Secret, key, workflow access or repository settings merely
because the CNY 10 spending intent was approved.

The transmitted payload is the evaluation prompt, validated task.json case
inputs/contract, exposed selected skill/resource bytes when the agent reads
them, output schema/tool declarations, and the bounded conversation/tool
results. Exclude held-out expected answers, verifier/check implementation,
unrelated repository/user files, credential stores and key material.

## Setup and spending prerequisites

1. Confirm the exact model/group permits direct Messages tool use; obtain the
   effective input/output/cache prices with currency, units and any minimum,
   request, long-context or group charges. Do not infer prices from ratios alone.
2. Establish an enforceable total limit including preflight and both arms.
   Confirm whether a dedicated provider-key quota rejects before an over-limit
   request, can overdraw during settlement, or uses preauthorization. A finite
   label, observed-token stop, CLI estimate or operator attestation alone is not
   proof of a hard monetary cap. If strict provider enforcement is unavailable,
   require a documented conservative worst-case reservation from verified prices
   and bounded requests before proceeding.
3. Obtain explicit security approval for the dedicated key and Secret exposure;
   the owner provisions them without sending the key in chat or committing it.
   No unlimited quota, automatic recharge or unrelated key use for this smoke.
4. Review and merge the bounded client implementation and any separate summary
   renderer change. Prepare one new exact plan with the approved total limit,
   group/pricing/control evidence and finite request/input/output ceilings.
5. Only after readiness and exact-plan approval, perform the single smoke.
   Prefer the first approved baseline trial as the compatibility observation
   rather than adding an unbudgeted paid test. Retain failure/partial evidence;
   do not retry automatically or expand into multiple addition/update campaigns.

Open blockers are effective price units/group, enforceable total-cap semantics,
owner-provisioned isolated credentials, offline-reviewed client wiring and the
new exact execution plan. No whole-#101/#88 or efficacy acceptance follows from
this preflight design.

## Offline implementation boundary

The opt-in comparison `client` settings select the bounded Messages read/submit
contract. Preparation freezes provider/protocol/endpoint/model, request/output/
read/tool ceilings, source hash and maximum API-request count across both arms.
The model effort must be `not_applicable`; the Codex default is unchanged.

This implementation slice is offline-only. The core loop accepts an explicit
transport for mocked tests, and HTTP construction is tested with fake keys.
Comparison execution refuses this provider before creating start/trial evidence,
even with an injected client. There is no live worker, environment-approval
shortcut, credential lookup/injection or hosted workflow change. Reviewed
pricing/cap enforcement and runtime credential wiring remain a separate required
implementation before live execution can be enabled. Preparation or green offline
CI is not provider compatibility, monetary control or real-evaluation acceptance.

Only complete UTF-8 reads of exposed workspace files and structured answer
submission are supported. A task-read/tool-result round trip is mandatory;
plaintext answers, shell/network tools and general coding actions are unsupported.
Schema support is limited to the existing audit/extract vocabulary. The normalized
agent trace records request hashes/lengths, reads/hashes, provider model, usage and
terminal errors without provider text or key material. Interrupted/unknown usage
remains unverified, with known partial observations retained separately.
