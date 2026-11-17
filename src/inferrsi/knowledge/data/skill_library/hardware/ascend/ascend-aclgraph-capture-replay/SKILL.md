---
name: ascend-aclgraph-capture-replay
description: Diagnose vLLM-Ascend ACLGraph capture/replay eligibility, stable-input and ordering contracts, and capture-resource failures at a pinned implementation. Use for evidence-gated graph-mode proposals, not allocator, compiler-fusion, or network tuning.
---

# Diagnose Ascend ACLGraph Capture/Replay

## Trigger and boundary

Use when a vLLM-Ascend workload unexpectedly captures, bypasses, or fails to replay graphs; reports capture-resource errors; or has evidence suggesting repeated host launch overhead could be amortized. Produce a bounded diagnosis and proposed change with a correctness/resource verification plan.

This candidate derives from `vllm-project/vllm-ascend@8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf`. Read [source-notes](references/source-notes.md) for immutable paths, symbols, and evidence IDs. `F` denotes observed source facts; `P` denotes the proposed operational procedure. Runtime benefit is unvalidated. Other vLLM, TorchNPU, and TorchAir pins are independent, not a tested compatibility set.

Status: candidate; empirical validation: **not_run**.

## Related capabilities & responsibility routing

For checkpoint onboarding, FP8 loading, KV-head replication and multimodal validation order, use [ascend-model-adaptation](../ascend-model-adaptation/SKILL.md). Its startup guidance is adjacent to this wrapper contract, not evidence that the two source revisions form a validated stack. See the [version and responsibility table](../../../README.md#vllm-ascend-version-and-responsibility-routing) for their separate evidence and date boundaries.

- **Runtime Wrapper (`ascend-aclgraph-capture-replay`)**: Handles graph pool capture, batch descriptor matching, input pointer assertions, and replay dispatch.
- **Compiler Passes (`ascend-graph-mode`)**: Covers TorchAir configuration guidance; this skill adds the independently pinned vLLM-Ascend runtime wrapper.
- **Attribution Discipline (`cann-attribution-overlap`)**: Supplies attribution methodology, not evidence that this wrapper improved performance.
- **Device Allocator (`torchnpu-device-memory-lifecycle`)**: Addresses allocator ownership at another pin, not graph-pool caller correctness or stream lifetimes.

## Required evidence (P)

Collect the installed Ascend/vLLM/Torch/TorchNPU/CANN/HDK versions and device; requested and effective graph mode; Model Runner version; attention backend; context-parallel, EAGLE/draft and ENPU settings; capture sizes; representative batch descriptors and prefill/decode mix. Obtain the full error and phase, graph/replay observations, available HBM/stream-resource evidence, and an existing eager correctness baseline. For performance claims, require host/device timing rather than a launch-overhead guess.

If evidence is unavailable, identify the missing item and give a conditional proposal. Do not invent the installed stack or initiate a run to fill the gap without authorization.

## Decision procedure and available actions (P)

1. **Confirm the execution path.** Compare the installed implementation with the pin. Separate compile-time Npugraph_ex optimization from runtime ACLGraph. The guide supports V1/V2, but warns that context-parallel `FULL` is insufficiently supported. Backend compatibility may narrow the requested mode. Diagnose the effective mode; do not force a requested mode through compatibility checks. [F1]
2. **Classify dispatch before tuning.** Read the forward context's runtime mode and batch descriptor. `NONE` or a wrapper-mode mismatch calls the runnable directly. A matching mode captures an uncaptured entry and replays a captured entry. Treat intended warmup/profile bypass as expected; investigate changing descriptors or failed captures before calling repeated work a cache defect. [F2]
3. **Classify batch descriptor matching and capture sizing.** The wrapper indexes captured graphs by `BatchDescriptor`. A matching runtime mode with a missing entry triggers initial capture (after `validate_cudagraph_capturing_enabled()`), while `NONE` or a mode mismatch bypasses capture/replay and calls the runnable directly [F2]. Capture sets are bounded by `cudagraph_capture_sizes` and `max_cudagraph_capture_size` to prevent stream-resource exhaustion; the guide notes larger capture sets increase resource pressure [F6]. Any request bucketing or padding to stabilize batch descriptors operates upstream in the caller/runner, not inside this wrapper.
4. **Check replay correctness first.** Require caller-managed stable replay buffers. The wrapper neither owns persistent input buffers nor copies new inputs into them. Propose `VLLM_LOGGING_LEVEL=DEBUG` before wrapper creation for a diagnostic reproduction: its address assertion covers only top-level positional tensor arguments (`args`), not keyword arguments (`kwargs`), nested tensor containers, or semantic correctness [F3]. Equal addresses alone establish neither updated contents nor semantic validity. Escalate an address mismatch to the buffer-owning caller; never suppress it to obtain a timing.
5. **Preserve multi-stream synchronization and ordering.** Note that the relative ordering of parameter updates and replay does not apply unconditionally across all dispatch paths; it is specific to the `FULL` graph mode on update-aware paths where `use_updatable_graph(attn_backend)` holds [F5]:
   - On this update-aware `FULL` path when ENPU is enabled: parameter update runs before graph replay (`update` then `replay`). The pinned source notes this ENPU ordering is assigned to the model runner caller, which was not inspected.
   - On this update-aware `FULL` path when ENPU is disabled: graph replay executes first, followed by parameter update (`replay` then `update`).
   - `FULL` synchronizes the current stream when ENPU is disabled, except in the draft-model-plus-EAGLE case.
   - For piecewise or non-updatable graph paths, verify stream ownership and event dependencies directly against `vllm_ascend/compilation/acl_graph.py` before inferring synchronization order.
   - `weak_ref_output` is safe only for the last piecewise graph whose output is not consumed downstream. Capture returns local `output`, whereas replay returns `entry.output`. Follow the branch-specific invariants in source-notes. [F4–F5]
6. **Choose one evidence-matched proposal.** 
   - For confirmed stream-resource capture failures (`_is_stream_resource_capture_error`: `insufficient_stream_resources`, `stream resources are insufficient`, or code `207008` paired with `stream resource`), propose fewer capture sizes or a smaller maximum (`max_cudagraph_capture_size`). Consider `FULL`/`FULL_DECODE_ONLY` for mostly uniform decode with verified backend support.
   - For old HDK failures (`_is_old_hdk_capture_error`: `alloc sq cq fail`), report the source's HDK 25.5.1+ and matching-CANN guidance as signature-specific, not a universal minimum.
   - Use temporary eager execution (`--enforce-eager`) as a diagnostic control. Preserve unrelated exceptions for diagnosis. [F1, F6]

## Benefit, cost, and counter-signals (P)

Hypothesis: repeated compatible batches can reuse captured work and reduce repeated host dispatch overhead. Costs include capture/startup work, graph-pool/workspace HBM occupancy, stream resources, and branch-dependent synchronization. Weak references do not establish a measured HBM saving. Smaller capture sets can reduce workload coverage; full-mode switches can confound capture effects with FX optimization.

Prefer investigation or an eager control when shapes rarely repeat, replay addresses are unstable, capture cannot amortize, memory/stream pressure dominates, the backend narrows the mode, context parallelism conflicts with FULL, or timing shows device work rather than host dispatch dominates.

## Verification and failure handling (P)

Propose a small authorized correctness-first comparison: same model, inputs, stack, workload and compilation settings where possible; observe initial capture and repeated replay for the same descriptor, expected bypasses, output agreement, capture count, warmup/startup time, steady-state latency, and HBM/resource pressure. Separate mode/compiler changes in the interpretation. The once-only replay log proves a replay path ran, not coverage or speedup. Pinned mocked tests offer contract checks, not hardware validation. [F7]

Stop on mismatched outputs, unstable addresses, capture exhaustion, unknown ordering, or version drift. Return the evidence, smallest reversible proposal, expected tradeoff, and remaining authorization/compatibility question. Loading this skill does not authorize installation, repository or configuration changes, hardware runs, benchmarks, or promotion.
