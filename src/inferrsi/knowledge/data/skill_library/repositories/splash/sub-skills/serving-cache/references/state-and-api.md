# Splash state and API contracts

Bounded static evidence at source commit
`39a97385f8560cf8a93972cec9b0a963c9195250`. The source paths/line spans at the
end identify the inspected material; they are not runtime dependencies or
instructions to reopen the original checkout. No native implementation,
accelerator, model, service-quality or performance result is claimed.

## Identity and lifetime ledger

| State | Key / owner | Required boundary |
| --- | --- | --- |
| Native target KV | Parent block, exact full-page token block and block identity | Identity includes intersecting image digest, grid and alignment; the first block also folds the request salt into the chain |
| Composite state | Immutable target-recurrent plus draft-context state attached to a complete KV block | The pair restores atomically; model-owned physical cells are separate from cache-owned leases |
| Active request | Page leases, cached-block references, pending restore waiters and resource commitments | Ending one request cannot free shared/submitted transfers another owner still needs |
| Disk prefix tier | Namespace plus recorded KV and state labels/copies | A reusable point requires a valid state and its complete chain; a cache file or matching tokens alone is insufficient |
| Responses history | Process-local response ID and retained input/output history | Bounded LRU, lost at restart; independent of native prefix persistence |
| Python memo cache | Owner-supplied key and byte size, optional entry capacity | Owner locking protects cache use; this is not the native C++/Metal state implementation |

### Salts and image identity

The optional request field `cache_salt` must be a nonempty string. The frontend
hashes it to 128 bits using personalized BLAKE2b; an absent salt uses zero.
The native block key combines its parent and exact tokens with image identity.
Salt is mixed into the first block, so descendants of different salts part at
the root even when their visible prompts or tokens are equal.

This governs cached prompt KV and associated states. It does **not** make all
caches private: the encoded image-row cache is shared across requests and
keyed by image rather than salt. Nor is a caller-provided salt an API key,
filesystem permission or tenant authentication mechanism. A salt-specific miss
may coexist with an image-encoding hit; that does not by itself violate the
prompt-cache rule. Preserve image order, digests, patch/grid dimensions and
block alignment when comparing a multimodal prefix.

`Cache::extendMatch` limits matches to whole blocks before the final real input
token. The remaining token regenerates request-specific anchor logits. Cached
KV can extend deeper than a retained composite state; `stateTokens` chooses a
state-bearing boundary. A hybrid model cannot continue from arbitrary KV alone
after recurrent state has been reclaimed.

### Ownership, admission and reclaim

The scheduler distinguishes queued, waiting-for-resources, waiting-for-prefix,
prefill, decode, waiting-for-mask and terminal phases. Resource admission and
suspended-resource resume are different transitions; resume preserves a replay
input token. Priority then arrival order governs the admission candidate order.
HTTP queue saturation, a missing native lane and memory refusal are different
waits and should not all be called GPU saturation.

The source's reclaim order is conditional: disposable checkpoints first, then
dead KV leaves, then ordinary state/KV recency, with in-use recovery state later
only when the reclaim class permits it. Active request pages and pinned restores
are not arbitrary eviction candidates. A background pressure pass differs from
a pass needed by running work; do not turn the ordering into a universal LRU.

Three outputs matter independently:

- `madeProgress`: ownership or a victim changed; it need not release an extent.
- `reclaimedBytes`: actual released KV extent bytes. Free reusable pages inside
  an allocated extent are not the same as memory returned to the governor.
- `pending`: a demotion/restore/state write can return the required resource
  after completion. It is not proof the cache is empty or safe to over-evict.

State RAM can return to a model pool before that pool returns memory to the
host. In-flight restoring bytes remain unusable until the restore lands.
Failed KV restores mark waiters failed and poison the block/invalidate its
state; descendants cease to be reachable cache matches. Failed writes do not
authorize dropping the original valid page; spill commitments are reconciled.

Cancellation resets scheduler passes and marks a nonterminal request cancelled.
Removal rejects an active batch member. Cache request teardown releases its
commitments, held pages and active chain reference, removes its waiters and may
abandon unsubmitted unshared restores; submitted/shared transfers retain their
ownership. Keep completion/drain and publication lifetime separate from a
client's cancellation signal. Progress checkpoints can survive cancellation,
but remain disposable rather than automatically durable.

## Disk persistence is a recovery protocol

`--max-cache-disk` controls SSD tier quota; `0` disables it.
`--persistent-cache` additionally retains recorded copies across restarts and
cannot be combined with a disabled SSD cache. `--cache-dir` selects the
persistent root, not every temporary file location. Temporary cache files are
session-lifetime, even when cached prefixes were usable before shutdown.

The namespace derives from the weight manifest, KV and recurrent-state layouts,
YaRN factor and cache-format identity. The documented manifest includes weight
image paths/declared sizes/headers and an assembly `model.json` digest. This is a
declared source/representation identity, not a new independent full-weight-byte
integrity proof. Model/format/scaling changes may select a cold namespace;
matching a human-readable model name is not sufficient. Do not manually move
copies between namespaces to force reuse.

Only one engine holds a persistent namespace directory at a time. Contention,
unsuitable volume or insufficient disk room may select temporary files. Root
quota and recency also account for idle model namespaces; persistence is not
indefinite retention or a backup guarantee.

Write-behind is delayed, not transactional persistence at every response. In
this source snapshot it queues suitable ordinary restore points at least 2048
tokens deep for a 10-second delay. A point superseded before writing may become
unneeded. A disk write budget can leave it waiting; quota can refuse it. State
is written before its KV chain. A clean stop attempts a bounded newest-first
flush; after a crash only landed, complete recorded points can be adopted.
Startup probation may intentionally begin empty after repeated early failures.

The native adoption code rejects invalid/duplicate labels, broken parent
ordering, unsupported page forms, token-depth mismatches and incomplete chains.
Track `disk.persistent`, `taken_back`, KV copies, write-behind counters and
write-gate reasons, not just the directory's existence. Do not patch formats,
labels or validity markers to suppress these failures.

## Local HTTP and API preparation

The default service binds `127.0.0.1:8000`. An authorized installed service
exposes Chat Completions, legacy Completions, Responses and Anthropic Messages;
`/v1/models` identifies its served model/aliases. Chat/Completions/Responses may
use the served default when `model` is empty/absent; Messages requires a model.
A different unsupported name yields a model-not-found error, not a new load.

| Intent | Endpoint / field boundary |
| --- | --- |
| Chat | `POST /v1/chat/completions`, `messages`, `max_completion_tokens` or `max_tokens`, optional `reasoning_effort` |
| Responses | `POST /v1/responses`, `input`, `max_output_tokens`, `reasoning.effort`; `previous_response_id` only while retained history exists |
| Anthropic | `POST /v1/messages`, `messages` and required model; omitted `thinking` normally means off |
| Template/token diagnosis | `/apply-template`, `/tokenize` and Messages `count_tokens` do not run generation, but still need an authorized prepared service/model |
| Lifecycle | `/health` says HTTP answers; `/ready` says engine ready. Neither proves workload correctness or completion |

The Responses history store is a process-local bounded LRU (documented 64 MiB).
On `previous_response_not_found`, resend full history. `--persistent-cache`
does not preserve that ID store. An oversized response may report `store:false`.
Delete/get response routes act on history, not on the native disk-cache graph.

Thinking defaults are template/protocol dependent, not a fixed token budget.
Chat `reasoning_effort` and Responses `reasoning.effort` may take the configured
fallback; explicit template kwargs can override thinking selection. Messages
retains its omitted-thinking semantics. Record effective template behavior
before asserting that nominal effort names produce identical prompts.

Structured output uses Chat `response_format`, Responses `text.format` or
Messages `output_config.format`/`output_format`. Shapes differ: Chat wraps its
JSON schema in `json_schema`, Responses does not. Constraints guide generation
and final validation; they do not add formatting instructions to the prompt.
Remote schema references and certain schema combinations are rejected. A stop
string or output-token cut can truncate JSON/tool arguments; a cut structured
answer is not validated as a complete success.

Image/PDF inputs are inline, not arbitrary URLs or server files. A
`--language-only` service rejects them. Context and input/media limits remain
separate from output-schema validation; do not execute a fetch to work around
an intentionally rejected URL input.

### Host, Origin and credentials are separate checks

`--host` chooses the bind address. `--allowed-host` adds accepted Host names;
it does not change the bind or allowlist client IPs. Exactly one Host and at
most one Origin are required. Origins match exact scheme/host/port; wildcard
subdomain patterns are not accepted. A bare `*` is broad access, not protection.

When a key is configured, `Authorization: Bearer ...` or `x-api-key` must match;
duplicate credential headers or one wrong credential among multiple supplied
ones fail. Credentials do not fix an unallowed Host/Origin. Public chat/health/
ready surfaces have their own exceptions, so a 200 health response is not proof
an authenticated inference request will pass. Inject credentials securely;
never put actual keys in generated request artifacts, shell arguments or logs.

## Python/native protocol boundary

The source has a versioned binary protocol between Python frontend and native
engine (version 11, 16-byte header, little-endian fields at this snapshot).
Framing, payload lengths, enum/count ranges, request IDs, sampling and mask
constraints are validated. A request error can reject one request while keeping
the stream; engine-unhealthy calls for engine replacement; protocol-fatal means
the stream is no longer trusted. Do not convert all three into retryable 400s.

The Python call's cancel method is idempotent while cancellation is pending.
It sends a native cancel frame and waits for acknowledgment; a cancel write
timeout or missing acknowledgment invalidates the generation as unhealthy.
CPU codec tests can check Python serialization and golden expectations. They
do not execute native cache policy, real IO completion, device cancellation or
Metal/ANE inference, even when the Python/C++ protocol constants agree.

## Bounded source readset

- `DEVELOPMENT.md`: 78–190 server/network settings; 418–591 precision/SSD and
  persistence; 742–785 reasoning; 893–998 API fields/salt; 1375–1423 schema,
  media and Responses history; 3302–3406 admission/replay/reclaim.
- `runtime/engine/KvCache.hpp`: 24–176 identity, tiers, references and transfers;
  `KvCache.cpp`: 30–67 image/salt key body and 663–719 eviction guards.
- `runtime/engine/Cache.hpp`: 27–44 lookup, 253–280 reclaim result, 331–345
  ownership, 600–689 reclaim contracts; `Cache.cpp`: 47–159 adoption,
  175–205 request teardown, 212–247 matching, 405–440 publication,
  568–652 reclaim and 1740–1828 transfer completion/failure.
- `runtime/engine/StateCache.hpp`: 125–224 composite restore/publication/use/
  persistence; `StateCache.cpp`: 12–99 lease/acquisition, 111–151 use lifetime,
  256–294 resume-point state, 360–397 reclaim guards, 472–497 failed offload,
  558–574 release.
- `runtime/engine/Scheduler.cpp`: 59–219 transition/cancel/removal/deadline
  bodies; 222–237 admission order; 575–649 completion validation.
- `runtime/engine/WriteBehind.hpp` and `.cpp`: complete bounded source files;
  `RuntimeResources.mm`: 480–577 identity/namespace body and 1025–1043 tier binding.
- `runtime/engine/Protocol.hpp`: 21–60 version/failure classes, 103–115 limits;
  `Protocol.cpp`: 26–88 framing/request-error classification.
- `server/frontend.py`: 604–617 salt validation/hash;
  `server/lru.py`: complete file (owner locking, byte/capacity accounting and
  compute-outside-lock memoization); `server/protocol.py`: 18–52 framing,
  738–779 selected sampling/mask/salt validation.
- `server/http_security.py`: 12–42 credential checks and 91–131 Host/Origin;
  `server/origins.py`: 14–64 authority/origin validation.
- `server/runtime.py`: 220–235 result/cancel, 1021–1051 cancel acknowledgment,
  1130–1155 protocol/ready handling and 1242–1288 error/mask dispatch.
- `dev/tests/server/test_lru_cache.py`: complete file, and
  `dev/tests/server/test_protocol_python.py`: 1–120 fixture/golden-test setup;
  inspected as native-candidate evidence, not executed in this author lane.
