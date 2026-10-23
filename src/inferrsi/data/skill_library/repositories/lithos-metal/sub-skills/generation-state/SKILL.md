---
name: generation-state
description: "Trace Lithos Metal GPU-resident generation and DSpark verification, commit/rollback, token-ring and cancellation state when continuation, acceptance or stop behavior is wrong."
disable-model-invocation: true
license: Apache-2.0
metadata:
  disco-role: operating
---

# Trace generation and speculative state

## Trigger and prerequisites

Use for continuation drift, wrong tokens after a rejected proposal, recurrent
state mismatch, context/ring errors, unexpected stop or cancellation latency.
Source-derived candidate; empirical validation **not_run**. Read the
[root](../../SKILL.md), [state mechanism](references/state-machine.md) and
[source readset](../../references/source-notes.md).

Record target/draft identities, tokenizer, model/DSpark configuration, taps,
formats/precision, context capacities, layout bounds, verification and sampling
policy, numerical options and selected backend/recipe. Dimensions alone do not
prove target/draft compatibility. Server DSpark uses fixed verification;
lower-level `Session` defaults to cost-aware selection with a fallback when
no matching cost table is available.

## Decision procedure

1. Identify whether the failing pass is intermediate prefill, final prefill,
   target verification, recurrent commit, draft context injection, proposal
   construction, verify-length selection or host token draining. Do not treat
   every replay as a productive decode round.
2. Reconstruct the committed-prefix ledger across the failing boundary. Include
   `position`, `t_this_step`, `pending_tokens`, `verify_len`, `accepted`,
   `checkpoint_index`, `n_inject`, `drafter_ctx_len`, recurrent slots,
   `ring_head/tail`, `stop_at`, `done` and `error`. Match the shared ABI rather
   than hardcoding offsets from another layout.
3. For `L` selected proposals, account for `1 + L` target rows including the
   anchor. Acceptance commits a prefix plus correction/bonus, bounded by EOS.
   Rejected positions must not survive as logical target or draft history.
   Inspect convolution and GDN commit passes as well as attention lengths;
   hidden-output agreement alone is insufficient.
4. Distinguish greedy/argmax-proposal and sampled-proposal semantics. The sampled
   path retains `q` logits/statistics through verification and uses rejection
   correction. Never apply its probability rule to the argmax proposal path or
   persist per-round proposal scratch as a prefix checkpoint.
5. Check compiled/active row and context bounds before varying proposal count.
   A changed block can select another recipe or exceed layout capacity. Preserve
   target/draft configuration and sampling semantics in any target-only control.
6. For streaming/cancellation, trace completed GPU work and committed ring tokens.
   Callbacks receive cumulative verified output. Cancellation is cooperative
   between bounded host pumps; an active Metal dispatch completes first.
   Never free buffers still owned by in-flight work.
7. Propose a bounded reproduction covering zero/full/interior rejection, EOS,
   token limit, context end and replay after done. Compare continuation tokens
   and target/draft persistent state with matched numerical mode. CPU mocks and
   synthetic ICB checks are useful contracts; actual DSpark/model numerics still
   require the selected checkpoint/backend.

## Counter-signals and report

Queued replays may return immediately after `done`; submitted steps can exceed
productive rounds. Full acceptance still needs correction/bonus accounting.
Allocated KV rows past the committed length need not be physically erased if
they are never read as valid history. An expected cache miss or conservative
row fallback is not evidence of corrupted state.

Return the first mismatched state obligation, its owner, the exact failing
round/prefix, control configuration and missing observations. Read
[troubleshooting](references/troubleshooting.md) for ABI, ring, capacity and
state-recovery failures. Do not publish complete-round or service rates from
target-only compute projections or acceptance assumptions.
