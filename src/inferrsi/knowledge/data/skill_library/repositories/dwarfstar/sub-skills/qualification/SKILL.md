---
name: qualification
description: "Qualify DwarfStar speculative decoding and distributed inference by separating sampling semantics, recurrent-state rollback, model-specific support and physical-backend evidence. Use for DSpark or MTP comparisons, exact sampling, TP failure recovery, correctness gates or performance claims."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Qualify speculation and distributed execution

Use this route before interpreting accepted-draft counts, local protocol tests
or a faster decode as a qualified engine result. This is source-derived
candidate guidance, not a backend certification or measured improvement.

Read the [verification contract](references/verification-contract.md) for the
model/mode matrix, proof ladder and experiment worksheet. Use
[troubleshooting](references/troubleshooting.md) when a continuation diverges,
a speculative block cannot be restored or peers fail to agree.

## Inputs and output

Record the engine revision/build flags, model family and exact weight hashes,
support-model identity, backend/device/topology, context and prefill sizes,
request concurrency, prompt/output limits, sampling parameters, seed policy,
cache/restore state and proposed change. A project name, bit width or filename
alone does not identify the computation.

Return one bounded conclusion with its invariant, actual check, evidence class,
counter-signal and remaining gap. Freeze numerical, distributional, quality,
latency and resource gates in the authorized experiment, not in this skill.

## Procedure

1. **Choose the semantic control first.** Ordinary target-only decode, greedy
   speculation, opportunistic nonzero-temperature speculation and exact sampled
   speculation are different modes. Do not call default opportunistic acceptance
   distribution-preserving. `--mtp-exact-sampling` selects the exact path where
   implemented; it does not promise equal seeded output or equal floating-point
   reductions. DeepSeek `--quality` or `--dspark-strict` can isolate a
   target-only control; keep their other numerical effects visible.
2. **Match the actual capability tuple.** Flash 0731, Flash Vision Experimental,
   V4.1 Flash, GLM and Qwen have different draft layouts and eligibility gates.
   A support file that loads or yields plausible acceptance is not proof that
   it matches the target. Check the bundled model/mode matrix; preserve its
   V4.1 network-DSpark documentation conflict rather than announcing support
   from a generic flag or one source branch.
3. **Verify state, not only returned tokens.** Accepted rows must commit the
   corresponding target KV/compressor/indexer/recurrent frontier. Rejected rows
   must not remain visible. Tool-mode boundaries, EOS, cancellation, partial
   acceptance, restore and stale rewind need separate cases. A truncated token
   vector is not proof that recurrent state was restored. Send session-prefix
   and image-identity work to [serving-state](../serving-state/SKILL.md).
4. **Keep the three distribution mechanisms separate.** In-process CUDA pairing
   shards work across selected local devices; network TP coordinates two ranks;
   pipeline mode assigns complete layer ranges. Their flags, capacity,
   communication and failure contracts are not interchangeable. A local
   socketpair test is useful protocol evidence, not physical TCP/RDMA or GPU
   inference evidence. Send placement/budget work to
   [runtime-memory](../runtime-memory/SKILL.md).
5. **Climb the proof ladder without upgrading its result.** Start with the
   selected model-free numerical/protocol checks, then actual backend kernels,
   matched-model continuation and state tests, and finally the authorized
   service workload. Missing required hardware, model or peer evidence remains
   `BLOCKED_REQUIRED_BACKEND` for AREX verification and unverified/INCONCLUSIVE
   for the affected campaign claim. A CPU check cannot clear it.
6. **Measure net work after correctness.** Separate preparation, prefill,
   drafter, verifier, accepted-prefix commit, replay/correction and transport
   time. Record proposed/accepted lengths, direct/partial commits, replay
   fallbacks, verifier errors, per-request latency and aggregate throughput.
   Acceptance alone omits draft and verification cost; aggregate throughput is
   not the speed of one request. Test both predictable and unpredictable inputs.

## Report and stop

Name the precise tested tuple and distinguish source inspection, a completed
CPU/native check, an upstream report and an unexecuted proposal. Retain failed
trials and invalidated sessions. A mismatched checkpoint, unsupported mode,
unavailable accelerator/peer, missing frozen validator or exhausted authorized
budget stops the affected qualification; it does not justify a silent fallback
or a performance PASS.

No reading of this route authorizes engine installation, model downloads,
network reconfiguration, process termination or a new experiment. Final admission
of a partially verified knowledge candidate is a separate informed decision.
