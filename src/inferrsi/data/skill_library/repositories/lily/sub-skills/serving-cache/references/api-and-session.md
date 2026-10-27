# Lily API and session contracts

Bounded static read of `perplexityai/pplx-garden/lily` at monorepo commit
`1ed972ed3f0bd5616c997c9507c25616c63394fc`. All guidance is bundled here;
source paths below identify evidence, not files a future user must reopen.
Native Rust/Metal, actual checkpoint tokenization and real inference were not
executed by this author lane.

## A deliberately small API

| Method/path | Meaning |
| --- | --- |
| `GET /health` | HTTP handler health after engine startup |
| `GET /v1/models` | The one served ID, `Qwen3.6-35B-A3B` |
| `POST /v1/chat/completions` | Serial, text-only, greedy completion |

Other routes return 404. This snapshot does not implement Responses, Anthropic
Messages, streaming, tool calling or structured-output endpoints. The inspected
server has no application authentication/TLS layer; keep a separately authorized
deployment local or behind the appropriate independently reviewed protection.
Do not add a permissive public bind merely to make an SDK connect.

### Exact request surface

```json
{
  "model": "Qwen3.6-35B-A3B",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 32,
  "stream": false,
  "prompt_cache_key": "conversation-a"
}
```

- `model`: required string, exactly the served ID; it does not hot-load weights.
- `messages`: required nonempty list, ending in a `user` message. Each object
  has exactly `role` and string `content`; roles are `system`, `user`,
  `assistant`. The checkpoint template can impose further history constraints.
- `max_tokens`: optional positive native unsigned integer; default 128. Zero,
  negative numbers, booleans, fractional values and null are not valid here.
- `stream`: optional boolean default false; true is rejected, null is not the
  same as omission.
- `prompt_cache_key`: optional string or null. The native field does not
  require a nonempty string, and the helper does not invent that restriction.

Request and message structs deny unknown fields. Thus `temperature`, even zero,
`top_p`, `seed`, `tools`, `tool_choice`, `response_format`,
`max_completion_tokens`, `chat_template_kwargs`, reasoning fields and image
content arrays are not supported request substitutions. The total body is
limited to 1 MiB. Malformed/unsupported input is a 400
`invalid_request_error`; internal failures are 500 `server_error` with a generic
public message while diagnostic detail stays in the server log.

The bundled helper's native-sized integer screen targets the supported
64-bit Apple runtime. It intentionally does not emulate the tokenizer, load
weights, check GPU capacity, start a service or validate a real response.

## Template, capacity and greedy generation

The tokenizer reads `tokenizer.json`; the template comes from
`chat_template.jinja`, falling back to the string `chat_template` field in
`tokenizer_config.json`. It renders with an assistant generation prompt and
no tools. Encode does not implicitly add special tokens because the rendered
template already owns its markers.

The HTTP engine chooses `Thinking::Disabled`. Earlier assistant history turns
receive the closed empty reasoning block where the checkpoint template would
otherwise drop it. This deliberate history rewrite keeps exact multi-turn
prefixes stable for direct answers. It does not expose configurable reasoning
or make this server a sampling-compatible replacement for other runtimes.

Request capacity uses checked addition:

```text
required_tokens = rendered_prompt_tokens + max_tokens + 1
required_tokens <= effective_max_seq
```

The engine clamps configured capacity to the checkpoint's declared
`max_position_embeddings` when nonzero. This is more specific than a
prompt-plus-response-only estimate: an exact boundary without the extra token
fails. An offline character count is not a substitute for rendered token count.

Generation prefills the nonempty uncached suffix and selects greedily. It
recognizes configured tokenizer/config stop tokens. A stop token at the output
limit still makes the finish reason `stop`; otherwise exhaustion is `length`.
Pipelined work may already be submitted when a stop is observed and is waited
for. Do not confuse returned response tokens with tokens actually fed into
the retained decode state.

## Two-entry exact-prefix store

Each `Session` owns its token history, `DecodeState`, optional preferred key and
last-use clock. `SessionStore` holds released sessions with configured state
capacity; the HTTP engine constructs it with exactly two entries. The server
handles requests serially with one shared scratch object, not a concurrent
multi-lane scheduler.

Selection proceeds in this order:

1. Filter every entry by `cached_tokens.len() < new_prompt.len()` and exact
   `new_prompt.starts_with(cached_tokens)`.
2. Among those valid prefixes, rank a matching explicit key before a
   nonmatching key, then prefer the longer prefix.
3. Remove the chosen session from the store for exclusive use and verify
   `state.pos == cached_tokens.len()`.
4. If none matches, reuse/reset the least-recently-used released state when
   the two-entry store is full; otherwise allocate a new state. Return no
   cached token prefix for this cold path.

The explicit key is a selection preference **only**. It does not bypass token
equality, partition entries by caller, provide authentication, persist a
conversation or guarantee a hit. A different-key entry may still be selected
if it has a valid prefix and no preferred valid candidate outranks it. An
equal-length exact prompt is deliberately not a strict prefix and cannot
produce an empty generation suffix through this path.

On completion the retained token history appends the prompt suffix, then only
`generation.fed - suffix.len()` generated tokens. This tracks the actual
decode-state position; appending all returned tokens indiscriminately can make
state/history inconsistent. The code verifies equality before release. Release
drops an inconsistent session instead of caching it; successful release stamps
recency and replaces its preferred key with the current request's key.

The response reports the selected prefix length as
`usage.prompt_tokens_details.cached_tokens`; prompt usage remains the full
prompt count. The store is in process memory, not a persistent disk API or
durable remote conversation service. Restart, eviction, changed template or a
non-prefix transcript can legitimately require full prefill.

## Smallest diagnostic and evidence limit

Use a fixed supported checkpoint/template and compare: an exact continuation,
same key with an edited earlier turn, another key with a genuine prefix, and a
repeat equal-length prompt. Keep recent request order fixed to distinguish
identity from LRU eviction. Compare exact token arrays, cached-token usage and
state position, not human-visible semantic similarity. No native values are
available from the offline helper.

Source predicate/unit tests are inspected evidence. Without Cargo/rustc, the
supported M5+/macOS 26 Metal runtime and checkpoint, neither their execution nor
model-state correctness is established. Required gaps remain
`BLOCKED_REQUIRED_BACKEND`; Python structural tests do not clear them.

## Bounded source readset

Paths are relative to the `lily/` subdirectory of the pinned monorepo.

- `README.md`: supported model/hardware/API/cache and test boundaries.
- `src/serve.rs`: 20–46 model ID/request schema/budget; 90–128 error classes;
  134–257 engine load, validation, completion and state-history accounting;
  261–362 serial HTTP loop, route dispatch and body limit.
- `src/serve/session.rs`: complete file (1–87): strict prefix, preferred-key
  ranking, checked-out state, LRU reset, consistency-checked release.
- `src/chat.rs`: complete file (1–54): roles and text-only message schema.
- `src/generate.rs`: complete file (1–133): tokenizer-backed greedy loop,
  stop semantics, actual fed-token count and pipelined completion waits.
- `src/tokenizer.rs`: complete file (1–252): checkpoint tokenizer/template
  loading, no implicit special tokens and disabled-thinking history rewrite.
- `tests/unit/serve.rs`: complete file (1–44): unknown fields, token-budget
  overflow and public/internal error boundaries.
- `tests/unit/serve/session.rs`: complete file: strict versus equal-length or
  changed-token prefix examples; `tests/unit/generate.rs`: complete file
  (1–8): stop-token classification at the generation limit.
