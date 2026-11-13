---
name: sglang-runtime-memory
description: "Trace SGLang request and scheduler flow; reason about Radix/HiCache ownership, KV pressure, chunked prefill, and speculative decoding."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Runtime and memory

Read [architecture and memory](../../references/architecture-and-memory.md) for source locations, invariants, and discriminating observations. Return to the [root](../../SKILL.md) for topology or experiment routing.

1. Pin the workload: prompt/output lengths, shared-prefix distribution, streaming, sampling, concurrent arrivals, model state type, and cache cold/warm state. Identify whether latency is queueing, prefill, decode, or host/storage transfer.
2. Trace one request through tokenization, admission, forward, and finish/abort. Keep logical request state, physical KV slots, prefix-cache nodes, and pending transfer state separate.
3. Locate the actual cache selected for this model. Plain RadixCache and UnifiedRadixCache have different component contracts. Do not transplant a full-attention assumption into SWA or Mamba state.
4. For a knob change, inspect declaration plus resolution/compatibility hooks and capture effective settings. For a code change, identify every allocator/refcount/finish path affected before editing.
5. Check miss/hit equivalence, partial-prefix boundaries, eviction under pressure, finish/abort cleanup, and chunk boundaries. For speculation, additionally check draft/target compatibility, accepted tokens, rejected-token state cleanup, and verification-path correctness.

Expected result: a traced ownership boundary, a small proposed change, and a correctness/performance observation that can disprove the hypothesis. Fewer OOMs alone do not prove that request state is correct or throughput improved.

If locks or pool counters diverge, stop performance work and minimize the failing lifecycle. If a startup hook rejects the configuration, retain its message and choose a supported baseline; do not bypass the validator. Use [validation gates](../../references/tuning-and-validation.md) to distinguish local static checks from required GPU tests.
