# Splash serving/cache diagnostics

Use source-derived hypotheses, not a claim that the proposed diagnostic ran.
Read the bundled [state and API contracts](state-and-api.md) for the mechanism
behind each check. Preserve actual failure evidence and redact private content.

| Symptom | Mechanism to distinguish | Smallest falsifier / observation | Safe next step and stop |
| --- | --- | --- | --- |
| Equal prompts do not reuse after a salt change | Prompt KV/state key versus visible text | Hold exact input fixed; compare no salt, same nonempty salt and a different salt; separate encoded-image hits from prompt-KV hits | A different salt should not match that prompt chain. Do not remove salts to force cross-caller reuse or claim all image caches are isolated |
| Equal text with changed images appears warm | Image encoding versus native KV block identity | Compare ordered digests/grid/alignment, then the prefix-state boundary; measure the correct cache counter | Rebuild the changed image-dependent chain. Equal placeholder tokens do not authenticate pixel-dependent KV |
| Matched KV still requires prefill | Missing target-recurrent/draft composite state or final anchor token | Compare deepest KV match, selected state-bearing boundary and real input-token remainder | Replay from a valid state; never fabricate recurrent state or splice arbitrary KV into a new lane |
| Evictions increase but allocated bytes stay high | Victim removal, free pages, allocated extents and model-owned pooled buffers | Check `madeProgress`, `pending`, released extent bytes and state-pool observations separately | Wait for a relevant transfer or reclaim the right resource class; a victim count is not physical-memory release |
| New requests queue despite a free lane | HTTP cap, priority, held-behind-refusal, missing state memory or prefix wait | Inspect admission reason and host-growth permission before changing concurrency | Preserve earlier refusal/priority semantics; do not label all waits GPU saturation or disable the governor |
| Cancelled request still has IO or device work | Cancel signal versus active-batch completion and owned transfers | Check terminal acknowledgment, active batch and outstanding/shared restore ownership | Drain/await the matching completion; no use-after-free shortcut. Missing native acknowledgment is an unhealthy generation, not cancellation success |
| Disk cache is present but restart is cold | Namespace, complete landed point, lock/fallback, quota/write budget and probation | Compare persistent mode/namespace, taken-back counts, write-behind and write-gate reason | Cold replay may be correct. Do not rename namespaces, patch labels or copy another model's slots |
| Latest short tool turn is not durable | Delayed minimum-depth write-behind and superseded points | Inspect whether a qualifying point was queued, superseded, refused or still writing | Retain full history and accept recomputation; a generated response is not a durability receipt |
| A crash loses the most recent continuation | RAM publication versus landed state and complete KV chain | Compare the last complete disk restore point, not only response completion | Recover only whole valid points; do not call a partial chain a successful restore |
| `previous_response_not_found` after restart with persistent cache | Process-local Responses history versus native disk prefix state | Check response-store lifetime independently of disk cache | Resend full history; persistence does not retain response IDs or API conversation objects |
| Browser gets 403 while a shell client works | Host allowlist, Origin exact match, bind and credentials | Inspect the actual Host and Origin without publishing private addresses | Authorize only the intended name/origin. Do not default to wildcard origins or public binding as a generic fix |
| Authentication fails when two headers are supplied | Every supplied credential must match; duplicates are rejected | Confirm one correctly injected allowed header; keep keys out of logs | Correct client configuration; a valid bearer value does not excuse a wrong `x-api-key` |
| Structured answer is truncated or unparsable | Schema-constrained completion versus output/stop cut | Check finish/stop reason, complete output and endpoint-specific schema shape | Do not mark the schema result validated. Adjust the authorized request budget/prompt and retry only within scope |
| Nominally equal effort has different prompt behavior | API default, explicit effort and template kwargs | Compare effective rendered template/thinking settings without generation if a prepared service is authorized | Match effective semantics; effort labels are not fixed reasoning-token budgets |
| Framing/version error is treated as a normal request error | Request-local, engine-unhealthy and protocol-fatal classes | Preserve error class, request identity and engine generation | Fail/recover the right scope; do not keep decoding an untrusted stream or blindly replay work |

## Support-tool decisions

The native cache/scheduler tests are evidence and future verification candidates,
not portable user utilities: they instantiate engine objects and need the native
build/backend or mocks. Copying them as a Python cache checker would replace the
implementation being tested. The Python codec is coupled to the versioned native
wire contract, not a user-facing general request builder. No codec, engine
runner, service launcher, model downloader or persistent-cache mutator is bundled
by this sub-skill.

An offline request builder owned by the root may help construct a bounded body;
it still cannot validate a loaded tokenizer/model, authenticate a service,
reproduce native cache ownership or prove a disk point durable. A Python LRU
unit pass establishes its byte/entry bookkeeping only. Concurrent memoization
computes outside its owner lock, so multiple misses can perform duplicate work;
it is not a single-flight guarantee or a native scheduling test.

## Evidence boundary

Record exact source/runtime version, manifest/layout identity, request history,
cache salt, lifecycle phase, observation, alternate cause and proposed check.
Use local placeholders rather than private paths, hostnames, keys or prompts.
Reading these instructions does not authorize inference, startup/restart,
deletion, filesystem permission changes or remote access. Required native
Metal/ANE/model/real-IO/service validation remains `BLOCKED_REQUIRED_BACKEND`
when unavailable; source analysis, synthetic cases and Python tests cannot
clear it.
