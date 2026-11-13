# Generation and DSpark state contracts

Use to construct a round-by-round ledger without needing the original checkout.
The implementation facts below are scoped to the pinned source; verification
steps are proposals, not bundled model evidence.

## Shared control ABI and storage

`StepStateLayout(t_max, gamma_max)` requires room for the anchor plus maximum
draft block. Fields are four-byte scalars/arrays, total storage is padded to
16 bytes, and order is a compiler/runtime ABI. Fields are appended rather than
reordered. `pack`/`unpack` are little-endian host representations; emitted MSL
uses the same offsets. The root software helper checks a tiny roundtrip and
invalid-bound rejection; it never exercises GPU rollback.

| State | Meaning/owner |
| --- | --- |
| `position`, active rows and `pending_tokens` | First row position and inputs of current replay; intermediate prompt chunks are host-fed |
| `anchor`, `gamma`, proposal/confidence arrays, `verify_len` | Draft/selection state; target verification consumes anchor plus selected proposals |
| `accepted`, `checkpoint_index`, `n_inject` | Accepted prefix and recurrent commit slot/rows; committed target features for next draft pass |
| `drafter_ctx_len`, draft K/V | Injected committed context, distinct from proposals being verified |
| `rng_lo/hi` | Sampling reproducibility; seed alone is insufficient if policy/round order differs |
| `ring_head/tail`, `stop_at`, `done`, `error` | GPU publication, host consumption, request stop and bounded failure |

Weights are immutable packed mappings. Persistent target K/V, convolution/GDN
slots, draft context and control survive replays; acceptance logs and ring have
their own lifetimes. Temporary activations/partials may be reused only after
their last consumer. Program parameter records belong to a particular program.

## Speculative graph and commit

The compiler's `lower_round` appends acceptance to the target graph, then every
operation's declared `commit_kind`, then target feature taps → drafter block →
verify selection. The DSpark model injects committed features in its next draft
pass; its `lower_context_update` is deliberately a no-op, not missing work.

1. Intermediate prefill has `prefill_left > 0`; acceptance advances by prompt
   rows, selects the matching recurrent checkpoint, sets injection rows and
   emits no output. The final prompt pass samples the first token.
2. `verify_select` advances injected-context bookkeeping, bounds selected `L`
   by block, layout and remaining context, and writes pending anchor/proposals
   and `t_this_step = 1 + L` for the next target replay.
3. `accept_scan` finds the matching proposal prefix, obtains a target correction
   or bonus, checks ring space, publishes sequence-tagged tokens through the
   first EOS, and updates position/anchor/commit bookkeeping. For a first pass
   with prompt rows, `base = t_this_step - 1 - verify_len` accounts for rows
   preceding the anchor. Do not derive committed state from `accepted` alone.
4. Convolution/recurrent commit paths retain/recompute the state matching those
   committed rows. Attention validity follows logical positions; overwritten
   rejected rows cannot be included by later length bookkeeping.
5. The request's output cap can stop after a complete verified round. The host
   truncates returned/callback tokens to the requested output limit; queued
   dispatches after `done` return without productive work. Use acceptance logs
   for productive speculative round counts rather than all submitted steps.

## Sampling and verification policies

Greedy acceptance compares target argmax with proposals. For nonzero temperature,
the serving default still uses argmax draft proposals: accept when they equal
the target sample. Sampled proposals use draft distribution `q`, acceptance
`min(1, p/q)` and positive-part `p-q` replacement at rejection. Target top-k
renormalization precedes top-p on that path. The sampled path requires proposal
logits/statistics; those per-round values are excluded from persistent prefix
snapshots. Changing draft precision can change proposals and acceptance.

Lower-level selection supports `fixed`, `threshold` and `cost`. Fixed length
must be within the drafter block. Cost uses a backend cost table for the relevant
pack format; absence falls back to threshold, not extrapolated cost. Serving
selects fixed verification up to the supported block, normally seven proposals
plus anchor. A confidence head does not prove confidence scheduling is active.

DSpark's block transformer uses target feature K/V and bidirectional block
attention; sequential Markov corrections restore predecessor dependence and a
confidence head supplies policy estimates. Check checkpoint-owned embedding/head
versus supported target sharing. `--draft-quantization none` preserves supplied
precision; it cannot recreate BF16 from an already quantized source.

## Stop, failure and host ownership

The ring holds aligned eight-byte `(sequence << 32) | token` slots, so wrapped
slots can be distinguished. Ring capacity bounds publication and host draining.
State error 1 is ring overflow, 2 context capacity and 3 bounded mixer barrier
timeout; `Engine.run` explicitly raises for error 3. `Session.generate` raises
other stopped-short failures and rejects over-capacity requests before work.
An error reached only by queued work after a fully served request must be
interpreted with actual committed output, not the raw flag alone.

`Engine.run` waits for its queued work to finish. Streaming pumps are bounded;
cancel predicates stop subsequent work after the active pump. The interface
does not promise preemption of an active kernel. Preserve lifetime through that
completion boundary before release/adoption or a new request reset.

## Proposed qualification

Start with binary-layout and mock generation tests; then exercise real synthetic
ICB/reencode, done, wrap and overflow. Full-model tests must compare deterministic
continuation, rejection boundary, recurrent slots and target/draft logical
lengths; stochastic tests need the configured distribution protocol. Include
prefill and cache-resume boundaries. A hidden tensor comparison, accepted-count
summary or target-only latency is insufficient by itself.
