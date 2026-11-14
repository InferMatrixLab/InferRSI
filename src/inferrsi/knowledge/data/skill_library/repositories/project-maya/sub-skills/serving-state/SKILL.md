---
name: serving-state
description: "Audits Project Maya API history, background cancellation and replay, native conversation reuse, image identity, and parallel request state without confusing persistence with isolation."
disable-model-invocation: true
license: NO_LICENSE
metadata:
  disco-role: operating
---

# Serving state and recovery

Use this route for `previous_response_id`, `store`, background jobs, expired event
cursors, cancellation, cache hints, edited images, interleaved conversations, or
whether a restart can recover a conversation. This is source-grounded candidate
guidance, not a validated CUDA/HIP service or a security certification.
Native state coverage here is bounded to GLM, DS4 and MiniMax. Qwen native state
is unmined in this route; shared Python protocol inspection does not qualify
every model family. Use the root's model-runtime route for its bounded coverage.

## Read the relevant contract

- [API history and background lifecycle](references/api-and-history.md): request
  subset, owner scope, retention, continuation, replay, and structured output.
- [Native state and parallel ownership](references/native-state.md): GLM, DS4,
  and MiniMax differ; disk slots are not API history and parallel sequences are
  not credential partitions.
- [Troubleshooting](references/troubleshooting.md): smallest discriminating
  checks, recovery, and when to stop.

## Procedure

1. Identify the engine family/version, actual `READY` capacity, full rendered
   history, authentication configuration, and which state plane is missing.
   Collect sanitized status/error/cursor facts, not credentials or private prompts.
2. Separate Responses JSON snapshots, background records/events/readers, native
   resident sequences/checkpoints, and parked native slots. Ask which one is
   expected to survive; do not infer one plane's retention from another.
3. Resolve API history under the same authenticated credential. Without configured
   authentication every caller has owner `public`. A `prompt_cache_key` is only a
   hint and is not a native-cache partition, identity proof, or confidentiality
   control. CORS is not authentication.
4. For continuation, preserve complete input/output/tool-call relationships and
   explicitly resupply tools, instructions and settings as needed. On an expired,
   foreign-owner or post-restart ID, recover from client-held full history instead
   of silently omitting it. Do not replay a side-effecting tool automatically.
5. For native reuse, compare exact token prefixes and effective image identity,
   not visible text alone. Apply the family-specific lifetime and compatibility
   checks in [native state](references/native-state.md); do not patch slot headers
   or force an incompatible restore.
6. For cancellation/reconnection, distinguish the cancellation request, Python
   terminal state, event-reader release and actual native completion. A timed-out
   STOP drain does not prove GPU cleanup. Stop new dependent work and escalate
   uncertain backend ownership rather than claiming it is freed.
7. Report observations separately from expectations. Python/mock checks can test
   protocol guidance; GPU execution, multi-sequence correctness, disk restore and
   cancellation cleanup remain backend-unverified until actually exercised.

## Offline request construction

Run or read the bundled [Responses request template](scripts/request_template.py)
to construct a deliberately small text-only request without sending it:

```bash
python scripts/request_template.py --input "Remember the synthetic value 73" --store
python scripts/request_template.py --input "Summarize the synthetic note" --store --background --stream
```

The helper accepts only its documented subset. It does not authenticate, resolve
history IDs, validate model capacity, start Maya, or verify native-cache behavior.
Its `--previous-response-id` is useful only for an actually retained same-owner
response; `--prompt-cache-key` does not isolate a tenant.
