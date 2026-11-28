# API history and background lifecycle

## Scope and evidence

Read for request construction, history lookup, background recovery and structured
output. Source snapshot: Project Maya `1.1.34`, commit
`249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`. The relevant contracts are
[Responses normalization](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/serve/responses.py#L99-L278),
[history storage](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/serve/response_store.py#L18-L201),
[job ownership](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/serve/response_jobs.py#L16-L264),
and [HTTP callsites](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/serve/server.py#L3792-L3908).
These are source observations, not a live-server compatibility test.

## Request and continuation contract

- `POST /v1/responses` accepts text/image input, function tools and supported
  reasoning fields; it is a subset, not every OpenAI Responses feature.
- `store` defaults to `false`. `background:true` requires **explicit** `store:true`.
  `stream`, `store`, `background` and `parallel_tool_calls` must be booleans.
- `max_output_tokens` must be a positive integer. Only `truncation:"disabled"`
  and `service_tier:"auto"` are supported. Unsupported parameters are rejected,
  not silently accepted as functional.
- A nonempty `prompt_cache_key` of at most 256 characters is validated and echoed.
  It neither forces reuse nor partitions native caches. `client_metadata` must
  be string-to-string; it is an accepted diagnostic input, not retained history.
- A retained `previous_response_id` supplies that response's complete input plus
  its output; newly supplied input is appended. The referenced status must be
  `completed` or `incomplete`; an active background response returns `409`.
  `store:false` can continue a retained response without saving the new result.
- Tools, instructions and generation settings are not inherited. Explicit system
  or developer items already in input history remain history. Preserve function
  call IDs and exactly one matching result per call. Results are ordered to their
  calls by normalization before template conversion; unmatched/duplicate results
  fail. Do not fabricate results or rerun a side-effecting tool to repair history.

The offline [request helper](../scripts/request_template.py) constructs only a
small string-input subset. For complex image/tool histories, follow these
contracts rather than treating the helper as a comprehensive API validator.

## Authentication, owner and memory

The HTTP handler selects a Bearer credential when present in Bearer form,
otherwise `x-api-key`. With configured keys it compares against the configured
list and hashes the selected credential for history ownership. The same key in
either form shares history; another key sees `404`, not a cross-owner record.
Without configured authentication the owner is `public` for everyone. This JSON
ownership rule does **not** establish credential-partitioned GPU/KV/slot state.
Do not claim both credential headers must match: this handler selects one.

Ordinary history is process-memory only. Defaults are 128 entries and 64 MiB of
serialized unique blocks, metadata and references; one entry is also limited to
64 MiB. Owner quotas default to zero, meaning disabled. Each owner has separate
immutable content-block identity. Descendants reference the required blocks
directly: deleting an ancestor does not recursively delete a retained descendant.

Entries expire after a fixed default 3,600 seconds from insertion at completion.
Reads move the LRU position but do not renew the deadline. Capacity pressure
evicts LRU entries; an impossible insertion plans first and does not evict valid
records merely to fail. Unknown, expired, deleted, evicted, other-owner and
post-restart IDs return `404`. Never silently discard the missing history.

Expanded snapshot assembly has a separate serialized-byte admission budget
(default 64 MiB), returning `503` under pressure. These are not Python RSS caps:
object overhead, request-expanded histories and background records are separate.

## Resources and replay

| Operation | Path / constraints |
| --- | --- |
| Retrieve | `GET /v1/responses/{id}`; background lookup precedes ordinary cache lookup |
| Delete | `DELETE /v1/responses/{id}`; no query options; active background record gives `409` |
| Inputs | `GET /v1/responses/{id}/input_items`; excludes the response's own output |
| Input paging | `order=asc\|desc` (default desc), `limit=1..100` (default 20), `after=<item_id>` |
| Cancel | `POST /v1/responses/{id}/cancel`; background only, not a native STOP broadcast |
| Resume SSE | `GET /v1/responses/{id}?stream=true&starting_after=<nonnegative_sequence>` |

Ordinary snapshot retention, background records and event retention are separate.
Default background limits: 2 worker threads, 16 records/active admission slots,
4 active jobs per owner, 300-second deadline from submission, 900-second completed
record retention and 2 MiB initial input snapshot. Ordinary LRU eviction does not
remove an active job. Completed records may be evicted to admit new records.
Worker count is not native parallel decode capacity: the service's engine FIFO
follows actual `READY ... multi=N`, including after an engine restart.

Each job retains at most 4,096 events and 2 MiB serialized events by default.
An event too large is `413`; oldest events are dropped for retention. A cursor
behind the retained range is `410`: retrieve the current response snapshot and
resynchronize explicitly; never pretend missed events were delivered. A cursor
beyond the latest event is `400`. Missing background event history can be `409`
even while an ordinary final snapshot remains retrievable.

Reader admission defaults to 32 globally and 8 per owner; capacity is `429`.
Closing a background SSE reader releases the reader slot without cancelling the
job. Foreground disconnect instead requests cancellation and does not store its
unfinished result. Terminal successful/incomplete storage happens before its
terminal event; a storage failure is not published as successful completion.

## Cancellation and stopping

Queued cancellation completes without starting generation. Running cancellation
sets a cooperative event and waits up to five seconds; the returned response can
still be `in_progress`. Poll it. A cancelled background response uses status
`cancelled` and standard SSE `error` with code `response_cancelled`, not an invented
`response.cancelled` lifecycle event. Deadline expiry is failure, not a successful
answer. Shutdown joins workers with a bound and reports still-live workers.

The worker closes its Python generator before terminal publication. However,
[single and multi native drains](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/serve/server.py#L1035-L1223)
can time out, warn that the engine may still be writing, and release/drop the
route. Multi request-quiet timeout also stops/drops a route without proving its
native completion. **Neither Python terminal status nor a released FIFO place
proves GPU work or native state ownership has ended.** This is an unverified
backend boundary. For a wedged drain, stop dependent submissions and use an
authorized operator restart/termination procedure; do not send a bare native
`STOP` that would cancel other requests.

## Structured output: publication, not constrained decoding

[Validation code](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/serve/response_schema.py#L36-L181)
supports `text.format` types `text`, `json_object`, and `json_schema`. Schema
format requires `name` and an object-root schema; `strict` must be boolean.
Strict object schemas disallow extra properties and require every declared
property. Supported bounded Draft 2020-12 validation rejects references,
definitions, patterns, formats, conditionals and unknown keywords before
generation; do not use it for arbitrary remote-schema resolution.

JSON instructions are added to the prompt. Structured text/strict tool events are
held under an estimated 4 MiB buffer until a complete stopped result validates.
Schema limits are 64 KiB, 512 nodes and depth 24; instance limits are 65,536 nodes
and depth 32, with a one-second traversal budget and cancellation checks.
`jsonschema` is required for schema validation, not ordinary text.

Lifecycle/heartbeat events can arrive before content. Invalid output fails with
usage but without publishing invalid content/tool deltas. Output exhaustion gives
`response.incomplete` and usage without releasing unvalidated held content. There
is no automatic retry and no token-level constraint guarantee. Never execute
unvalidated or incomplete function arguments.
