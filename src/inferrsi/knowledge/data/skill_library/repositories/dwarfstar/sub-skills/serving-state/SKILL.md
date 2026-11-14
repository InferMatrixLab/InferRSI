---
name: serving-state
description: "Diagnose DwarfStar HTTP serving, session-slot reuse, image identity, disk KV compatibility and exact tool replay without confusing a visible transcript with a valid model checkpoint."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# DwarfStar serving and state

Use for a stale answer, an unexpected full prefill, a tool-result continuation,
an image-history change, a server restart or a concurrency change. This is
source-derived candidate guidance, not native accelerator or service validation.
Read [state contracts](references/state-contracts.md) for API examples, reuse
predicates and the evidence readset; use [troubleshooting](references/troubleshooting.md)
when an observed symptom violates an expected boundary.

For offline request construction, use the bundled
[request template](../../scripts/request_template.py); it prints JSON only and
does not contact the server. Its `--model` value is an API alias, not a file
selector.

## Establish the request identity

Record the engine revision and build backend, actual GGUF/checkpoint and optional
vision encoder, context, slot count, prefill chunk, sampling/thinking settings,
API, complete message history, ordered images and tool-call IDs. Record the
cache policy and whether this is a warm live slot or a disk restore after a
restart. Redact the content before sharing traces; retain the diagnostic
relationship between requests.

An API model alias is not a checkpoint selector. A rendered string is not an
exact token history. An image marker is not the image fingerprint. A tool-call
ID is not a durable remote conversation. Keep all four identities separate.

## Route and inspect

1. **Start local, not public.** An already-authorized, installed server may be
   configured with `-m <MODEL_PATH> --ctx <CONTEXT>` and bound to loopback. The
   default API address is `http://127.0.0.1:8000`. Do not broaden the bind,
   install software, download weights or launch inference merely because this
   procedure is being read. CORS is not authentication; a remote deployment
   needs a separately authorized access-control/TLS design.
2. **Identify the reuse layer.** Distinguish a live slot's valid backend
   checkpoint, the disk entry's rendered-byte-prefix lookup and the exact
   tokens/model state inside its payload. Apply the compatibility and suffix
   construction rules in the reference before calling a miss a regression.
3. **Check images before text shortcuts.** The routing probe requires a valid
   historical fingerprint/row-count prefix. Materialization must also preserve
   the token prefix and valid image positions. Changed pixels, reordered or
   removed historical images, or different embedding row counts are not safe
   extensions even when visible text is unchanged.
4. **Check tool replay before canonicalization.** Known call IDs can recover
   the sampled DSML spelling; all calls in a message must resolve to one
   retained block. Missing/mixed mappings use canonical rendering instead.
   Replacing previously sampled tokens requires a real backend-frontier
   restore or rebuild, not an edit to the token vector alone.
5. **Reconcile scheduling and ownership.** Each slot retains its own KV,
   recurrent state and history. A supported model may share prefill workspace;
   it does not share request identity. `--batched-session <SLOTS>` preallocates
   states, and full occupancy queues requests. Ordered fallback is concurrency
   and fairness, not proof of native grouped decode or throughput gain.
6. **Choose the smallest discriminating check.** Compare the same request with
   a known live prefix, after a controlled fresh session, and after an
   authorized restart with compatible disk cache. Change only one of text,
   image identity, tool IDs or cache policy at a time. Inspect the chosen reuse
   route and effective prompt; compare next-token/logit or model output only
   when the required backend and model are available.
7. **Recover without manufacturing validity.** On an incompatible payload,
   invalid checkpoint or unsupported rewrite, retain the error and rebuild
   from a verified older prefix or the full request. On interruption, distinguish
   completed synchronized chunks from an incomplete forward. Never set a
   validity flag merely because a token count looks plausible.

## Output and stopping condition

Return a short ledger with `request identity`, `slot/backend validity`,
`reuse layer`, `matched prefix`, `image/tool gate`, `suffix or rebuild`,
`observed result` and `remaining check`. State the counterexample that would
falsify the diagnosis. Stop before an unavailable accelerator/model, unsafe
cache deletion, private trace publication or unapproved service exposure.

CPU bookkeeping tests and source inspection can check guidance and state
predicates. They cannot establish Metal/CUDA/ROCm rollback, physical TP restore,
model quality, HTTP load/SLOs or performance. Those remain
`BLOCKED_REQUIRED_BACKEND` when required resources are absent; do not upgrade
them to a pass through synthetic assertions or green packaging CI.
