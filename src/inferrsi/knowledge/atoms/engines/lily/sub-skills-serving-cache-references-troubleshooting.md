# Lily interface and cache diagnostics

These are source-grounded hypotheses and proposed checks, not observations from
a running engine. Read [API and session contracts](api-and-session.md) before
adapting a client from a broader OpenAI-compatible implementation.

| Symptom | Distinguish | Smallest useful check | Safe recovery / stopping boundary |
| --- | --- | --- | --- |
| Request with `temperature: 0` is rejected | Greedy behavior versus a supported sampling field | Screen the top-level keys with the bundled request helper | Remove unsupported settings only if that preserves the user's intended semantics; do not claim non-greedy sampling works |
| Streaming/tools/schema request fails | Deliberately unsupported capability versus malformed syntax | Identify the actual endpoint and unsupported fields | Offer the strict text-only nonstreaming subset; use a separately chosen runtime if the user requires these features |
| Final assistant message fails | History continuation versus the required final user query | Check message roles and last role | Preserve complete history but finish with the intended user turn; do not forge a user message merely to hide an incompatible workflow |
| Same `prompt_cache_key` misses | Key preference versus exact strict token-prefix eligibility | Compare actual rendered token arrays and lengths, not only the key/text | Re-prefill is correct for edited history, equal-length prompt or a non-prefix; never mark old state valid from the key |
| Another key appears to reuse a prefix | Preference versus caller partitioning | Check whether it is a strict prefix and whether a valid matching-key candidate existed | This store is not key-isolated. Do not use keys as authentication or a confidentiality guarantee |
| Only two recent sessions remain warm | Fixed two-entry LRU and serial checkout/release | Repeat with a frozen request order; identify the reset oldest released state | Treat expected eviction separately from a leak; increasing concurrency is not an exposed cache option |
| Visible history matches but token prefix diverges | Checkpoint template/tokenizer and empty reasoning-block rewrite | Freeze exact files and rendered bytes/tokens across the earlier assistant turn | Restore matching template semantics; do not retokenize old KV under a different template |
| `request needs ... tokens` at an apparently exact fit | Native rendered prompt plus output plus one extra token | Apply `prompt_tokens + max_tokens + 1`, then the clamped effective capacity | Reduce requested output/history or choose supported capacity within actual memory; character counts do not prove fit |
| Token/state position mismatch | Returned tokens versus tokens fed into decode state | Compare retained history count with `DecodeState.pos` and source `generation.fed` accounting | Drop/rebuild invalid state; do not append every response token or repair only the vector |
| Stop at max output reported as `stop` | Stop-token termination versus simple length exhaustion | Check whether the final returned token is configured as a stop | Preserve source stop semantics; finish reason alone is not evidence of output-quality success |
| New request fails after an internal generation error | Selected state removed from store versus successful release | Verify the error category and whether a consistent session was returned | Retain failure and cold-rebuild; do not advertise persistence/recovery guarantees absent native evidence |
| Client expects Responses/Anthropic routes | Minimal Chat subset versus general proxy | Compare requested path against the three implemented routes | Use supported Chat shape or another explicitly selected engine; no route rewrite can add missing semantics |

## Offline helper boundary

The sibling `scripts/request_template.py` adapts request screening from the
source request/message structs and `validate_request`. It constructs a tiny body
or checks an existing body using only Python's standard library. It rejects
unknown keys, wrong types, unsupported roles/streaming and an incorrect model,
but it cannot load the checkpoint or validate its template. It prints JSON only;
it never sends a request, starts a listener, loads a model or contacts a network.

The source native tests are not copied as runnable Python replacements. Their
Rust serde, tokenizer and device-state behavior must be tested by the original
implementation on the appropriate toolchain/hardware. A helper pass is only
evidence about the helper, not parity or native usability. Preserve the missing
compiler and `BLOCKED_REQUIRED_BACKEND` state explicitly.
