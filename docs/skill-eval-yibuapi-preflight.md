# Direct Yibuapi skill evaluation

The opt-in Messages client uses the existing Python interpreter, comparison
schedule, fresh workspace, timeout/process cleanup and trusted verifier. It
exposes only read_file and submit_answer. Codex remains the default when no
provider configuration is supplied. No external agent executable is required.

## Configuration and cost reservation

Supply public JSON as the workflow_dispatch provider_config input, unchanged
between planning, execution and any retained-publication retry. It has four
required top-level fields and one narrowly scoped optional override:

| Field | Required content |
| --- | --- |
| model | name and effort; effort is not_applicable, with no Codex xhigh mapping |
| client | kind, provider, endpoint, api_version and all five integer bounds below |
| pricing | exact model/group/currency/units, all effective rates, fees, full context bound, evidence and expiry |
| spend_limit | currency and approved finite amount as a decimal string |
| limits (optional) | exactly token_stop_new_trials as a finite positive integer |

The client identity is kind=anthropic-messages-agent-v1, provider=yibuapi,
endpoint=https://yibuapi.com/v1/messages and api_version=2023-06-01. Its required
positive integer bounds are max_requests (at least two), max_output_tokens,
max_request_bytes, max_read_bytes and max_tool_calls. These are issue-scoped
execution choices; approve them in the exact frozen plan. max_requests counts
every attempted Messages request in a trial, including failed/uncertain requests.
No additional compatibility probe is sent: the first baseline request is the
compatibility observation.

For a paid pair, optional limits.token_stop_new_trials overrides only that
mapping limit. Other limit overrides, zero/negative values, booleans and strings
are rejected. Omitting limits preserves the existing mapping and Codex defaults.
The effective limit is frozen in each comparison, the PR plan, and the complete
Budget JSON; changing it requires a new exact plan and approval. Monetary
reservation, request/tool/read/output/deadline bounds and unknown-usage stops
remain unchanged.

Token usage is cumulative across both arms and checked before every new trial.
If a completed baseline reaches the threshold, candidate is not started. Choose
explicit finite headroom appropriate to the whole authorized pair; it is neither
a per-arm limit nor a hard provider token/money cap. Do not reuse an older plan
or retry a consumed paid run after changing headroom.

pricing requires currency (USD or CNY), unit=per_million_tokens, model, group,
rates, request_fee, max_input_tokens, rate_evidence and expires_at. rates contains
explicit nonnegative decimal strings for input, output, cache_read and cache_write.
Use final effective group prices, including every applicable billing tier and
the highest possible cache-write rate; do not infer a write price from a read
price or a group multiplier. request_fee is the verified maximum per-request fee,
including error/uncertain requests. Zero is explicit, not an unknown default.
No FX conversion is inferred.

rate_evidence is the reviewed repository Issue-comment record linking the
provider's effective units/group/rates/fees and their verification.
expires_at is that record's Unix expiry. Software validates the frozen record
and arithmetic; the operator/reviewer must verify the external billing facts.

The live model registry currently supports claude-opus-5-5 with its complete
1,000,000-token context bound from the
[model specification](https://platform.claude.com/docs/en/models/opus-5-5/overview).
max_input_tokens must be at least this full bound. Reservation uses the whole
model context for every possible request, including tool/system framing, rather
than an unverified characters-to-tokens estimate:

    per request = full input ceiling * max(input, cache_read, cache_write) / 1e6
                  + output ceiling * output rate / 1e6 + request_fee
    total = sum(trials * max_requests * per-request cost over all comparisons)

Decimal amounts round upward; the complete reservation must fit spend_limit.
No cache discount, successful response or later token stop reduces the upfront
allowance. Both arms, all selected cases and all possible loop requests count.
Any unknown/expired rate, currency mismatch or insufficient total prevents
authorization. The allowance is conditional on the verified model/context and
provider billing contract; it is not proof that a provider will honor false or
changed external facts.

## Credential setup and execution

After explicit approval of the credential exposure, the owner provisions GitHub
Actions Secret SKILL_EVAL_YIBUAPI_KEY. The workflow exposes it only to the
conditional Yibuapi model-execution step. plan, authorize and publish do not
receive the key. The model child receives a filtered environment without GitHub
or Actions publication/runtime credentials; the verifier receives no provider
key. Never place a key in provider_config, command arguments, Git, logs or chat.

1. Prepare action=plan with the exact provider_config and target PR. Inspect the
   frozen model/group/rates, context/request bounds, paired cases and reservation.
2. Approve the new exact plan SHA, trusted version, base/head and full Budget JSON.
   Execute with the same provider_config and all approval inputs.
3. Inspect retained outcomes and feedback. Failed/uncertain requests stop without
   retry or model fallback. Use action=publish with the original source_run and
   identical configuration for publication-only recovery.

Price readiness is checked before authorization/history checks; key presence is
checked before the local execution claim and first request. plan cannot inspect
a Secret it does not receive. GitHub dispatch history still records a failed
attempt, so missing-key/failed executions must not be blindly rerun. Preserve
one-shot history and prepare a newly reviewed plan after investigating a failure.
An expired rate record blocks new execution, but retained historical results can
still be rebuilt/regraded/published without a model call.

Opus 5.5 uses adaptive thinking and does not support forced tool choice. The
client uses auto, preserves returned thinking/signature blocks opaquely for the
tool round trip, and never logs their content. See the
[model protocol notes](https://platform.claude.com/docs/en/models/opus-5-5/overview).
A task-read/tool-result round trip and schema-valid submit_answer are required.
Unknown usage, malformed responses or exceeded bounds stop the paid path.
The publisher independently regrades supported outputs with trusted code.

Only selected public task inputs, exposed selected-arm skill/resources, tool
schemas and their bounded conversation/results are sent to Yibuapi. Held-out
expected answers, verifier implementation, unrelated files and authentication
stores are excluded. The key goes only in the fixed endpoint's authentication
header. No paid preflight, model fallback or automatic retry is part of setup.

Offline tests use fake keys/transports and retained-publication fixtures.
Passing them establishes software behavior; actual provider compatibility and
addition/update efficacy require the separately approved real run and evidence.
