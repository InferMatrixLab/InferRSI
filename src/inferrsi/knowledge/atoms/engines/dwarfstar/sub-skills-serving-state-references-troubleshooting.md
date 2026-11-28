# Serving-state troubleshooting

Use these as source-derived diagnostic hypotheses. A failed hypothesis is useful
evidence; do not change cache policy, erase files or expose a service merely to
obtain a cleaner trace. Record the effective request and build configuration.

| Symptom | Distinguish first | Smallest useful check | Recovery / stop condition |
| --- | --- | --- | --- |
| The requested API model name appears ignored | A compatibility alias versus the GGUF loaded at startup | Compare startup model identity and `/v1/models` with the configured `-m` | Select the intended compatible file in an authorized restart; a request alias does not hot-load it |
| A repeated chat re-prefills after restart | Live slot versus disk prefix/payload and cache policy | Check whether a matching disk entry exists, is model/context compatible, and actually loaded | Full-history replay is valid fallback; preserve the failed-load reason rather than calling a byte-key hit a restore |
| Equal visible text has different token counts | Sampled token spelling versus canonical BPE tokenization | Compare exact saved tokens and the suffix boundary, not only rendered text | Restore exact history plus suffix; replacing sampled tokens behind the live end needs full frontier restore/rebuild |
| Changed image appears to reuse stale KV | Fingerprint/row count and order versus a text-only prefix | Change one historical image while keeping visible text fixed; the old image-conditioned route must miss | Retain ordered image identity and rebuild; never force reuse from matching text or placeholder IDs |
| Appended images never reuse a live prefix | Fingerprint-only routing probe versus strict materialized spans | Verify historical fingerprints/row counts, the independent text/tool continuation, and the rebased/new-image positions | Diagnose the failed gate; do not skip token matching merely because images match |
| Image conversation disappears from disk cache | Deliberate vision save guard versus corrupt persistence | Check whether the slot contains or is syncing vision state | Text-keyed disk persistence is not a multimodal state contract; after restart re-send complete image history and accept prefill |
| Tool result causes a large rebuild | Missing/evicted IDs, mixed DSML blocks, or canonical token rewrite | Keep original IDs and complete history, inspect replay versus canonical route; compare a controlled diagnostic with exact replay disabled only if authorized | Rebuild a valid frontier, or resend reconstructible history; a tool ID is not durable remote state |
| Tool-result-only request fails after restart | In-memory live binding versus retained compatible disk/tool trailers | Identify whether any full replayable prefix still exists | Return a clear missing-context limitation; do not invent a stored conversation |
| `unsupported session payload version` or layout/capacity error | Wrong runtime/layout, saved context too large, incomplete file or incompatible model | Preserve the error; compare source/build/model/context identity and declared payload lengths | Rebuild from full history or a verified compatible older cache; never patch header/version fields to force a load |
| `prompt length ... exceeds context ...` | Prompt-only length versus required generation room | Count the materialized prompt, including template/images/tools | Reduce history/output plan or increase context only if supported and budgeted; sync requires at least one generation token of room |
| Interrupted request later returns stale logits | Token vector versus completed chunk's backend/logit checkpoint | Check actual interrupted status and last completed synchronized frontier | Re-sync a valid prefix; do not mark an incomplete forward valid based only on token count |
| More slots fit but do not improve throughput | Independent states and scheduling versus native grouped decode | Record the actual model/backend path and fallback messages with fixed workload | Ordered fallback is expected in supported cases; measure before claiming gain and stop at missing GPU evidence |
| Disk restore is unexpectedly slow on TP | Token replay across both ranks versus direct per-rank GPU restore | Compare both-rank sync activity with the retained token count | Expect prefill; physical transport and distributed correctness require an authorized real-peer check |

## Safe local interface preparation

Keep loopback binding unless remote access is explicitly requested. `--cors`
only changes browser cross-origin headers; it does not supply authentication,
change the bind address or make an Internet deployment safe. Keep cache and
trace paths private. Public examples should use `<MODEL_PATH>`, `<CACHE_DIR>`
and redacted request identities rather than private paths or conversation text.

Build a tiny deterministic JSON request offline first, then send it only to a
confirmed authorized local service. Do not add image URLs or server-side file
paths when the endpoint requires inline image content. Free-form traces may
contain prompts, tool arguments, IDs and generated text; review/redact before
publication, retaining enough structure to explain reuse or invalidation.

## Report the boundary

For each diagnosis provide: observed symptom, selected identity layer, source
invariant, alternate explanation, discriminating check, result and next safe
step. Source reads and CPU identity tests do not prove model output, native
rollback, device-memory safety, service SLOs or cross-rank restoration. Required
unavailable backend/model evidence remains `BLOCKED_REQUIRED_BACKEND`.
