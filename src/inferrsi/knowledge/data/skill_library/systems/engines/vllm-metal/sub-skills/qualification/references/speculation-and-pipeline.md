# Speculative verification and pending-token ownership

## Pairing and scheduling

Source methods include Gemma4 MTP with a matching assistant, separate draft
models for non-hybrid paged targets, and token-history n-gram drafting. DFlash
and DSpark have their own experimental target/draft checkpoint and scheduler
contracts; their detailed qualification is not derived here. Method presence
is not universal model support.

Only plain greedy requests without penalties, token constraints or sample
logprobs are drafted. Others may run target-only rather than doing the requested
speculative work. Scheduling is synchronous; the platform disables async when
speculation is configured. PP is unsupported with speculation, heterogeneous
draft vocabularies are rejected, and a nonzero long-prefill threshold must be
at least `1+num_speculative_tokens`. Multimodal paged batches cannot perform
multi-token verification, including text decode sharing multimodal prefill.

The ordinary draft must use full attention and the target vocabulary. Its
committed KV plus lookahead shares the target's scheduler-managed budget,
not a separate scratch allowance. The effective context is the smaller target/
draft limit. If no positive configured draft width fits, target-only fallback
is expected. The worker's context-limit fallback counter counts request
lifetimes once, survives preemption/completion and resets on drafter recreation;
reading it does not reset it. K=0 or temporary-width skips are not that event.

## Hybrid GDN is a state contract, not just more attention rows

Hybrid speculation is restricted to n-gram plus GDN, text-only, lazy GDN
kernels and FP32 recurrent state. Other hybrid state families (Mamba2, KDA,
shortconv) and non-ngram methods are rejected, not silently treated as safe.
Weights and convolution state need not all be FP32. Low-precision recurrent
state rounds differently between span verification and repeated decode; the
source records an exact-greedy-parity failure, not a theoretical equivalence.

A verify span stages its final recurrent state. Partial acceptance re-scans
the accepted prefix from untouched pre-span state; full acceptance across the
batch avoids that recovery. A partial acceptance currently re-scans all
requests in the batch, including prefill spans. One window segment per request,
head size≤256 and align-mode prefix state-block draft caps preserve the
supported checkpoint contract. The regular optional verification-window flag
does not make unsupported layouts safe.

## One-step-ahead decode pipeline

Pipelining overlaps graph construction/submit with the prior GPU step, deferring
the sampling sync. Its serve-level gate requires async scheduling, initialized
paged runtime, no pooling/PP/speculation, a suitable hybrid lazy-GDN path and
the in-process `uni` executor. Per-step gates exclude new/prefill/resumed/
preempted/encoder/spec/structured-output/multimodal work. Sampling must be
native greedy or eligible native random. A re-entering cached request without
a pending row forces synchronous handling; membership cannot grow unnoticed.

The runner appends a −1 placeholder and advances value-independent bookkeeping
before submission. Pending entries retain direct request-state references.
Resolution fills values through those references, not runner maps, so it does
not reinsert an evicted request. `begin_step` barriers pending work before any
ineligible-step mutation. Single pending and resolved-output slots enforce
serial output consumption. A leaked placeholder, unconsumed output or missing
pending row is a correctness failure, not an opportunity to skip synchronization.

Native random sampling supports the source's temperature/top-k/top-p/min-p
path, but seeds, penalties, logprobs and constraints can send the whole batch
through torch sampling. MLX RNG and torch RNG outputs may differ; matching seed
integers alone do not prove identical sampled generations.

## Immutable evidence

[Speculation guide](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/speculative_decoding.md),
[config pairing guards](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/platform.py#L690-L800),
[GDN load-time state guard](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/model_lifecycle.py),
and [pipeline gates/ownership](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/decode_pipeline.py#L1-L300).
Detailed kernel/parity bodies and live execution remain outside this source-only
qualification; exact resource hashes identify the inspected snapshot separately.
