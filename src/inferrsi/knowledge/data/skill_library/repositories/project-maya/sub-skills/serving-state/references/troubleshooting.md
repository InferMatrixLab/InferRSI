# Serving-state troubleshooting

Use sanitized synthetic requests first. A diagnosis below is a discriminating
check, not proof that a CUDA/HIP backend is correct. Do not install a model or
toolkit, run an installer, delete slots, or restart a shared engine implicitly.

| Symptom | Smallest falsifier / likely cause | Recovery and stopping boundary |
| --- | --- | --- |
| `previous_response_id` gives `404` after restart although slot files exist | Was this JSON response stored in this same running service under the same authenticated key? API IDs do not survive restart; native files are another plane. | Recover using client-held full history, tools and current instructions/settings. Never discard missing history silently or assume a disk slot recreates its API ID. |
| A different client can read history | Is authentication disabled, or do the clients share the same selected key? No-auth ownership is `public`; CORS is unrelated. | Configure authorized credential/access controls before private use. Do not claim `prompt_cache_key` isolates tenants or that JSON ownership partitions native caches. Stop if security configuration changes are not authorized. |
| `background:true` rejected before generation | Confirm explicit boolean `store:true`; strings such as `"true"` are not booleans. | Use the bundled [request constructor](../scripts/request_template.py), which rejects background without `--store`. It prints JSON only and cannot prove server acceptance. |
| Stored continuation loses old instructions/settings | Were they current request fields rather than explicit historical input items? | Resupply instructions, available tools and desired settings. Preserve call/result IDs; do not repair a mismatch by executing a tool twice. |
| Storage failure or `503` during history lookup | Check serialized entry/cache/assembly pressure separately; LRU and fixed TTL are independent. Re-reading does not renew expiry. | Retry transient assembly pressure; reduce saved content or use complete client-held history. Increasing a cap needs a memory plan; serialized limits are not RSS limits. |
| Background queue/reader returns `429` | Distinguish active-job admission from event-reader slots and native sequence capacity. | Back off; close abandoned readers. Do not increase workers as a substitute for GPU capacity or cancel unrelated work. |
| Reconnect gets cursor `410` | Cursor predates oldest retained event; not evidence the job failed. A future cursor is `400`, absent background event history can be `409`. | Retrieve current snapshot and resynchronize explicitly; do not silently skip missed tool/content events. If snapshot is also missing, recover from client history; do not rerun side effects. |
| Closing a background stream does not stop generation | Reader cleanup is not job cancellation. | Use the background response's cancel endpoint under its owner, then poll. Foreground disconnect behavior is different. |
| Cancel returns `in_progress`, or later terminal status appears while native drain warns | Cancel waits only five seconds. Native single/multi drain can time out; a dropped route/FIFO release does not prove native `DONE`. | Observe job status plus backend completion separately. Stop dependent submissions on uncertain ownership; an operator must authorize safe restart/termination. Never broadcast bare native STOP to resolve one tenant's request. |
| JSON/schema stream shows lifecycle but no text | Validate-before-publish buffers content; schema mismatch fails, budget exhaustion is incomplete without unvalidated held deltas. | Check terminal status/error/usage before consuming output. Use supported object-root schema and limits; do not call this constrained decoding or execute incomplete tool arguments. |
| Same text but edited image reuses too far, or seems cold | Visible text misses actual token/image identity. GLM parked slots exclude images; DS4/MM3 compare image marks/positions. | Use a tiny synthetic changed-image reproduction only on an authorized real backend; compare actual reuse boundary and output. Do not force cached state or infer identity from equal placeholder tokens. |
| Expected persisted GLM state is absent | Was RAM-only mode selected, keep disabled, slot too short, image-bearing, expired, invalid, or save refused by disk guard? | Inspect sanitized family settings/save notices. RAM mode intentionally dies with the run and does not clean the disk folder. Never patch metadata to bypass checks. |
| DS4/MM3 parallel startup uses more VRAM or fewer features | Private per-sequence state costs memory; MM3 parallel disables KV streaming/DSpark. Worker count and READY capacity are different. | Reduce context/parallelism only within an authorized configuration change. Do not assume shared weights imply a single shared KV or identical feature support. |
| Some parallel DS4 conversations fail to restore after QUIT | Current exit code flushes parked RAM states and the bound resident state, without an obvious save-all-resident-sequences loop. | Treat all-sequence graceful persistence as unverified. Recover full client history; require a real multi-sequence save/restart case before promising retention. |
| Slot accepted after same-size model replacement | Identity uses structural/file metadata, not a full weight digest. | Verify exact bytes against a trusted manifest; obtain permission for fresh-state cleanup while stopped. Do not use slot compatibility as model-integrity proof. |

## Minimal evidence to retain

Record source/engine version, model family, actual `READY` parallel capacity,
synthetic input shape, configured state plane, terminal HTTP/SSE error/status,
cursor bounds, sanitized native completion/drain messages, and whether an
authorized restart occurred. Distinguish source expectation, Python/mock
observation and actual backend observation. Never publish credentials, raw private
history, slot bytes or host-specific paths. Missing required backend evidence
remains `BLOCKED_REQUIRED_BACKEND`; no source or helper check changes that.
