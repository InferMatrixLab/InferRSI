---
name: torchnpu-device-memory-lifecycle
description: Diagnose TorchNPU device-HBM reuse, cross-stream lifetimes, cache retention and fragmentation, then propose version-gated allocator changes. Use for NPU allocator OOM or reuse investigations, not pinned-host RAM or network transport.
---

# TorchNPU device-memory lifecycle

## Scope and evidence contract

This candidate distills `Ascend/pytorch` at `67511c53cd4c88014f6123de7097677e60e85faa`, principally `torch_npu/csrc/core/npu/NPUCachingAllocator.cpp`. Read [source-notes](references/source-notes.md) for exact symbols, line links, gates and contradictions before using a specific lever. **F** denotes pinned-source facts; **P** denotes proposed decisions or verification. This is source-derived intelligence, not a measured optimization or an installed-stack compatibility claim. Device HBM belongs to **Accelerator**, not RAM/Host. IPC and H2D do not establish Network coverage.

Status: candidate; empirical validation: **not_run**.

## Related capabilities

[torchnpu-pinned-host-memory-lifecycle](../torchnpu-pinned-host-memory-lifecycle/SKILL.md) covers a separate RAM domain at the same upstream pin; do not share its counter semantics or controls with device HBM. [ascend-aclgraph-capture-replay](../ascend-aclgraph-capture-replay/SKILL.md) covers the graph wrapper at an independent pin, not this allocator's private-pool destruction rules.

## Required evidence

P: Obtain the failing allocation size, device and allocator backend; TorchNPU/PyTorch/CANN/HDK versions and hardware model; effective allocator settings; stream creation/use/free timeline; graph capture/private-pool state; and a bounded allocation-size sequence. Request existing `memory_stats()` or snapshot evidence for allocated, active, reserved and inactive-split bytes, retry/OOM counters, plus application references still retaining tensors. Separate evidence collected before and after synchronization. Missing evidence means a conditional proposal, never a diagnosed leak.

## Decision procedure and available actions

1. **Resolve lifetime before tuning.** F1: free requests reduce allocated bytes before all stream events necessarily complete. `recordStream` records usage; event completion controls cache reuse. The native `record_stream` caller rejects external streams; the allocator skips foreign-deleter pointers. F2: tests distinguish lifetime protection from producer/consumer ordering. P: trace every side-stream use and recommend the missing lifetime record and appropriate stream dependency independently. Do not remove records or substitute internal `eraseStream` to reduce retention. Stop for external/custom/shared allocation ownership that has not been traced.

2. **Classify retained HBM.** F3: reuse is stream-associated best-fit; splitting depends on effective configuration. Inactive-split statistics exclude expandable segments. P: distinguish live tensor growth, event-pending blocks, inactive splits and graph/private-pool retention. A reserved-minus-allocated gap alone cannot distinguish these. If live allocations dominate, address application ownership or workload capacity before allocator knobs.

3. **Select one eligible lever.** P: for non-expandable fragmentation with many inactive splits, propose `max_split_size_mb`; benefit is potentially less splitting, cost is reduced reuse or more allocation. For varying sizes, consider `expandable_segments`; benefit is potentially less stranded capacity, costs include mapping/granularity overhead and changed statistics. F4: nondefault split limits or garbage-collection thresholds cannot coexist with device expandable segments. Check the feature gates in the reference; never reuse the introductory comment's fixed 200 MB threshold as a default.

4. **Treat reclaim as work.** F5: `emptyCache` synchronizes and releases eligible cached storage; it cannot free live tensors. Garbage collection requires an active memory-fraction limit and a positive threshold, and its implementation also calls device synchronization despite a contrary comment. P: propose cache release only at an appropriate quiescent boundary; account for stalls and subsequent allocation churn. Reject per-iteration flushing as an unsupported general recommendation.

5. **Use specialized options only on matching evidence.** F6: `multi_stream_lazy_reclaim` reduces event-query frequency, reaping before block selection when backlog exceeds 512 or on a cache miss outside capture. P: consider it only for demonstrated multi-stream host query overhead; measure retained HBM and latency rather than promising unchanged peaks. F7: `page_size:1g` is large-pool-only with CANN/HDK/hardware gates. P: reject it for small allocations or limited HBM headroom; its coarse allocation can consume more memory. Treat it as a separately justified proposal, not a baseline preset.

## Countersignals, verification and escalation

P: Keep the baseline when traces show stable reuse, compute-bound execution, one-stream operation, capacity dominated by live tensors, or unsupported versions. Before any authorized change, save the exact configuration and define rollback for wrong results, new runtime errors, worse OOM/retry counts or unacceptable latency/HBM regression.

P: A later bounded verification should compare the same allocation sizes and stream ordering in fresh processes, check output equality and no premature reuse, then compare allocator statistics and latency at identical synchronization boundaries. Start from the cited focused tests; they were inspected, **not run**. A passing correctness check would not prove a performance gain.

P: Return the suspected state transition, F evidence IDs, one proposed action, expected benefit/resource cost, countersignals and a verification plan. Escalate capture/private-pool, IPC/custom-allocator or runtime-error cases to the owning subsystem. Loading this skill does not authorize installation, benchmarks, promotion or changes to a live deployment.
