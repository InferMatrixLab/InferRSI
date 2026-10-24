---
name: ascend-aclgraph-capture-replay
description: Diagnose vLLM-Ascend ACLGraph capture/replay eligibility, stable-input and ordering contracts, and capture-resource failures at a pinned implementation. Use for evidence-gated graph-mode proposals, not allocator, compiler-fusion, or network tuning.
---

# Diagnose Ascend ACLGraph Capture/Replay

## Trigger and boundary

Use when a vLLM-Ascend workload unexpectedly captures, bypasses, or fails to replay graphs; reports capture-resource errors; or has evidence suggesting repeated host launch overhead could be amortized. Produce a bounded diagnosis and proposed change with a correctness/resource verification plan.

This candidate derives from `vllm-project/vllm-ascend@8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf`. Read [source-notes](references/source-notes.md) for immutable paths, symbols, and evidence IDs. `F` denotes observed source facts; `P` denotes the proposed operational procedure. Runtime benefit is unvalidated. Other vLLM, TorchNPU, and TorchAir pins are independent, not a tested compatibility set.

Status: candidate; empirical validation: **not_run**.

## Related capabilities

For checkpoint onboarding, FP8 loading, KV-head replication and multimodal validation order, use the older documentation-based [ascend-model-adaptation](../ascend-model-adaptation/SKILL.md). Its startup guidance is adjacent to this wrapper contract, not evidence that the two source revisions form a validated stack. See the [version and responsibility table](../../../README.md#vllm-ascend-version-and-responsibility-routing) for their separate evidence and date boundaries.

[ascend-graph-mode](../ascend-graph-mode/SKILL.md) covers TorchAir configuration guidance; this skill adds the independently pinned vLLM-Ascend runtime wrapper. [cann-attribution-overlap](../cann-attribution-overlap/SKILL.md) supplies attribution methodology, not evidence that this wrapper improved performance. [torchnpu-device-memory-lifecycle](../torchnpu-device-memory-lifecycle/SKILL.md) addresses allocator ownership at another pin, not graph-pool caller correctness.

## Required evidence (P)

Collect the installed Ascend/vLLM/Torch/TorchNPU/CANN/HDK versions and device; requested and effective graph mode; Model Runner version; attention backend; context-parallel, EAGLE/draft and ENPU settings; capture sizes; representative batch descriptors and prefill/decode mix. Obtain the full error and phase, graph/replay observations, available HBM/stream-resource evidence, and an existing eager correctness baseline. For performance claims, require host/device timing rather than a launch-overhead guess.

If evidence is unavailable, identify the missing item and give a conditional proposal. Do not invent the installed stack or initiate a run to fill the gap without authorization.

## Decision procedure and available actions (P)

1. **Confirm the execution path.** Compare the installed implementation with the pin. Separate compile-time Npugraph_ex optimization from runtime ACLGraph. The guide supports V1/V2, but warns that context-parallel `FULL` is insufficiently supported. Backend compatibility may narrow the requested mode. Diagnose the effective mode; do not force a requested mode through compatibility checks. [F1]
2. **Classify dispatch before tuning.** Read the forward context's runtime mode and batch descriptor. `NONE` or a wrapper-mode mismatch calls the runnable directly. A matching mode captures an uncaptured entry and replays a captured entry. Treat intended warmup/profile bypass as expected; investigate changing descriptors or failed captures before calling repeated work a cache defect. [F2]
3. **Check replay correctness first.** Require caller-managed stable replay buffers. The wrapper neither owns persistent input buffers nor copies new inputs into them. Propose `VLLM_LOGGING_LEVEL=DEBUG` before wrapper creation for a diagnostic reproduction: its address assertion covers only top-level positional tensor arguments, not keyword/nested inputs or semantic correctness. Escalate an address mismatch to the buffer-owning caller; never suppress it to obtain a timing. [F3]
4. **Preserve lifetime and ordering.** Review offloader synchronization/join, graph-pool ownership, output/workspace weak references, and the FULL replay/update branch before proposing code changes. Do not remove synchronization, reorder update/replay, or generalize weak-output handling as a performance shortcut. Follow the branch-specific invariants in source-notes. [F4–F5]
5. **Choose one evidence-matched proposal.** For confirmed stream-resource capture failures, propose fewer capture sizes or a smaller maximum. Consider `FULL`/`FULL_DECODE_ONLY` only for mostly uniform decode with verified backend/platform support; this can also change compilation behavior. Use temporary eager execution as a diagnostic control. For the specific old-HDK signature, report the source's HDK 25.5.1+ and matching-CANN guidance as signature-specific, not a universal minimum. Preserve unrelated exceptions for diagnosis. [F1, F6]

## Benefit, cost, and counter-signals (P)

Hypothesis: repeated compatible batches can reuse captured work and reduce repeated host dispatch overhead. Costs include capture/startup work, graph-pool/workspace HBM occupancy, stream resources, and branch-dependent synchronization. Weak references do not establish a measured HBM saving. Smaller capture sets can reduce workload coverage; full-mode switches can confound capture effects with FX optimization.

Prefer investigation or an eager control when shapes rarely repeat, replay addresses are unstable, capture cannot amortize, memory/stream pressure dominates, the backend narrows the mode, context parallelism conflicts with FULL, or timing shows device work rather than host dispatch dominates.

## Verification and failure handling (P)

Propose a small authorized correctness-first comparison: same model, inputs, stack, workload and compilation settings where possible; observe initial capture and repeated replay for the same descriptor, expected bypasses, output agreement, capture count, warmup/startup time, steady-state latency, and HBM/resource pressure. Separate mode/compiler changes in the interpretation. The once-only replay log proves a replay path ran, not coverage or speedup. Pinned mocked tests offer contract checks, not hardware validation. [F7]

Stop on mismatched outputs, unstable addresses, capture exhaustion, unknown ordering, or version drift. Return the evidence, smallest reversible proposal, expected tradeoff, and remaining authorization/compatibility question. Loading this skill does not authorize installation, repository or configuration changes, hardware runs, benchmarks, or promotion.
