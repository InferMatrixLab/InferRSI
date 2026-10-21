---
name: sglang-parallel-extension
description: "Plan SGLang TP/replica-DP/attention-DP/EP and PD topology, or extend models, attention backends, and kernels with ownership and correctness checks."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Parallelism and extension

Read [parallelism and extension reference](../../references/parallelism-and-extension.md); use [native candidates](../../references/native-candidates.md) only for the component being changed. [Root routing](../../SKILL.md).

For topology, record ranks, group sizes, model dimensions, expert layout, accelerator memory, interconnect, and workload. Distinguish replica DP from attention DP. Confirm divisibility and model/backend gates in the pinned checkout. For PD, trace routing, bootstrap identity, destination allocation, transfer completion, and timeout/cancellation on both roles before adjusting capacity.

For implementation, choose the smallest responsible boundary:

- Model: config/architecture resolution, forward semantics, sharded weight loading, multimodal preprocessing if applicable, and logits/sampling integration.
- Attention backend: registered factory, supported forward modes and layouts, metadata planning, cache writes/reads, graph capture/replay.
- Kernel: operator contract, numerical reference, supported shapes/dtypes/strides/devices, lazy registration, and correct source/test placement.

Runtime configuration is published into namespace bags; the raw ServerArgs record is not the effective decision source. Inspect the current native runtime-context contract before modifying config reads, overrides, or per-runner state.

Expected result: topology/ownership diagram or precise patch boundary plus baseline comparisons. Validate one rank first when appropriate, then the intended groups and PD peers. Include idle ranks, uneven loads, cancellation, and error propagation in distributed checks.

A distributed hang requires rank-specific evidence and collective-order inspection. A numerically wrong kernel requires a reduced input and reference comparison. Revert the affected backend/feature to the baseline; do not infer correctness from a successful import, launch, or faster microbenchmark. Plan the [validation gates](../../references/tuning-and-validation.md) before accepting the extension.
