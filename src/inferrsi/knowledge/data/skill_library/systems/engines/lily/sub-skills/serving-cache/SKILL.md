---
name: serving-cache
description: "Prepare Lily's strict text-only greedy Chat Completions requests and diagnose its two-entry exact-token-prefix session cache, key preferences, template history and decode-state lifetime."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Lily serving and session cache

Use for a rejected OpenAI-style client request, a changed multi-turn prefix, an
unexpected cache miss or an incorrect assumption about `prompt_cache_key`.
This is source-derived candidate guidance, not native Rust/Metal/model
validation. Read [API and session contracts](references/api-and-session.md)
for exact fields, cache-selection rules and the bounded readset; use
[troubleshooting](references/troubleshooting.md) for recovery and falsifiers.

## Establish the contract

Record source/build version, exact supported checkpoint and tokenizer/template,
macOS/GPU, `--max-seq`, full ordered text messages, requested output length,
optional cache key and recent request order. Lily is a serial, single-checkpoint
server, not a general OpenAI proxy, streaming server or multi-tenant session
service. The supported model identifier is `Qwen3.6-35B-A3B`.

Do not add fields a general SDK normally sends. Sampling controls, tools,
structured output, multimodal content and thinking switches are not this
server's request API. `temperature: 0` is still an unknown field; greedy decode
is inherent, not configured through that parameter.

## Procedure

1. **Screen the request offline.** Use the bundled
   [request helper](scripts/request_template.py), which constructs or checks
   only the documented JSON surface and never contacts a server. The accepted
   fields are `model`, `messages`, `max_tokens`, `stream` and
   `prompt_cache_key`; messages have only `role` and string `content`.
2. **Require the supported conversation shape.** Roles are `system`, `user` or
   `assistant`, and the final message must be `user`. `messages` must not be
   empty. `stream` must be false/omitted and `max_tokens` positive. Unknown
   fields are errors, not ignored options. Template-level constraints remain
   authoritative after this structural screening.
3. **Freeze tokenization and thinking semantics.** The server always chooses
   disabled-thinking rendering from the checkpoint template. Lily deliberately
   retains a closed empty reasoning block in earlier assistant turns to keep
   direct-answer histories prefix-cacheable. Do not compare visible strings
   alone or replace the template/tokenizer with another checkpoint's files.
4. **Budget the actual rendered tokens.** Source validation requires
   `rendered_prompt_tokens + max_tokens + 1 <= effective_max_seq`, with checked
   arithmetic. The extra token is reserved by the implementation. The effective
   limit is clamped to the checkpoint's declared position capacity. The offline
   helper cannot compute native template/token counts or prove that capacity.
5. **Check exact prefix before the key.** A cached token sequence must be
   shorter than, and exactly equal to the beginning of, the new prompt. Same
   key, semantically equivalent text or an equal-length exact prompt cannot
   bypass that strict predicate. Among valid candidates a matching explicit
   key is preferred, then the longest prefix; another key is not an isolation
   barrier.
6. **Trace owned state, not response text.** The selected session is checked
   out of the store while used. Its state position must equal retained token
   count. Generation feeds the uncached suffix, then the greedy decode loop;
   the retained history appends only generated tokens actually fed into the
   decode state, which need not be every token returned to the client.
7. **Explain eviction and error paths.** The store holds at most two released
   sessions. With no matching prefix and a full store, it resets and reuses the
   least-recently-used entry's state; otherwise it allocates a new state. Only
   a successful position-consistent session is released back. Failure is not
   permission to synthesize KV state or repair only the token vector.
8. **Choose one smallest falsifier.** Compare the exact rendered token prefix,
   state position, request order and reported
   `usage.prompt_tokens_details.cached_tokens`. Test same-key/different-prefix
   and different-key/valid-prefix separately. Execute native comparisons only
   with the supported authorized hardware/model and a frozen request sequence.

## Report and stop

Return the JSON/API decision, effective token budget, strict-prefix decision,
key preference, retained-state boundary, LRU context, observed result and one
counter-explanation. A helper pass proves only its own structural checks; a
health/model-list response is not model correctness or performance evidence.

Stop before unapproved service startup/exposure, model downloads, toolchain
installation or unavailable native execution. Rust tests were not run where
Cargo/rustc are unavailable; M5+/macOS 26/Metal/model checks remain
`BLOCKED_REQUIRED_BACKEND`. Python request construction is not Rust API, cache,
tokenizer, device-state or service qualification.
