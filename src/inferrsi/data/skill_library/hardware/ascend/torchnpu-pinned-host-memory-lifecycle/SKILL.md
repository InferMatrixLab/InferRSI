---
name: torchnpu-pinned-host-memory-lifecycle
description: Diagnose TorchNPU pinned-host RAM allocation, asynchronous-copy lifetime, reuse and cache controls, then propose version-gated host-allocator changes. Use for pin_memory pressure or host allocation stalls, not device HBM or network transport.
---

# TorchNPU pinned-host memory lifecycle

## Scope and evidence contract

This candidate distills `Ascend/pytorch` at `67511c53cd4c88014f6123de7097677e60e85faa`, principally `torch_npu/csrc/core/npu/CachingHostAllocator.cpp`. Read [source-notes](references/source-notes.md) for exact source links, feature gates and unresolved boundaries. **F** means pinned-source facts; **P** means proposed decisions or verification. This is a **RAM/Host** capability: the returned allocation is CPU memory and expandable physical pages use host location, even though one enum contains `HBM`. H2D/D2H, registration and IPC are not Network evidence. No performance or installed-stack compatibility is established.

Status: candidate; empirical validation: **not_run**.

## Related capabilities

[host-memory-management](../../host/host-memory-management/SKILL.md) is general CUDA-oriented guidance; its examples, thresholds and synchronization advice do not establish TorchNPU behavior. Use this pinned ledger for TorchNPU ownership, readiness and reuse. [torchnpu-device-memory-lifecycle](../torchnpu-device-memory-lifecycle/SKILL.md) is the separate device-HBM domain, with different counters and controls.

## Required evidence

P: Obtain TorchNPU/PyTorch/CANN/HDK versions, hardware, effective allocator settings, host RAM pressure, allocation-size/reuse distribution and producer/consumer stream timeline. Identify allocator-owned pinned tensors versus externally registered pointers or ordinary pageable memory. Gather existing `host_memory_stats()` active/allocated bytes and host allocation/free timings, together with application references and concurrent data-loader/prefetch behavior. Identify the selected default or expandable host path before interpreting counters.

## Decision procedure and available actions

1. **Separate ownership, readiness and lifetime.** F1: nonblocking-copy handling records events for TorchNPU-owned host storage; unregistered paths synchronize the stream. Merely requesting `non_blocking=True` does not prove overlap. F2: event hooks and the expandable allocator defer reuse until pending uses complete in the normal path. P: retain correct host ownership and stream dependencies; do not mutate an H2D source or read a D2H destination before completion. For external registration, trace the owner's lifetime contract rather than assuming TorchNPU tracks it.

2. **Explain RAM retention using host semantics.** F3: host `allocated_bytes` means allocator-owned active plus cached bytes, unlike device allocated-byte accounting. Active bytes can include pending stream use. Expandable mode does not maintain all block-count metrics, and power-of-two assumptions do not apply uniformly. P: classify live/pending buffers versus reusable cached storage; inspect bytes and effective mode before calling zero counts or retained RAM a leak. Reuse is expected, as the focused tests show by assertions only, not execution here.

3. **Choose a path-specific proposal.** F4: the host allocator is selected once. Default-path round/cache thresholds are explicitly inert with `pin_memory_expandable_segments=True`. P: in fresh-process trials only, consider `pinned_max_round_threshold_mb` for large rounding waste, or `pinned_max_cached_size_mb` for infrequently reused large buffers. Potential benefit is lower retained RAM; costs are less reuse and more allocation/free work. Require the pinned docs' TorchNPU 26.2.0/PyTorch 2.13.0 gate and verify the actual stack. Do not present the latter as a total-cache cap or permission to free in-flight buffers.

4. **Match event-processing and expandable options to symptoms.** P: consider `pinned_use_background_threads` only when foreground event processing is material and its supported default-path implementation is verified; costs include CPU/thread activity. Consider host expandable segments for variable-size pressure only after its separate gates pass; the source uses 20 MiB physical segments, adding granularity/mapping costs. Do not transplant device `expandable_segments`, device split limits or 1 GiB page logic into host settings.

5. **Check registration and release carefully.** F5: registration can fall back, is disabled with host expandable segments, and has inconsistent HDK warning language. P: require the stricter documented CANN 8.5.0/HDK 26.0.RC1/TorchNPU 26.0.0 gates plus runtime feature evidence; otherwise leave registration unchanged. F6: `host_empty_cache` targets host cache, but the expandable release comment requires prior device synchronization while its public binding does not insert it. P: use an explicit quiescent boundary for any authorized release; never assume host cache clearing is a completion barrier. Budget for stalls and repinning on later use.

## Countersignals, verification and escalation

P: Keep the baseline for live-buffer growth, pageable-memory copies, stable frequent reuse, unverified versions, or an unsupported allocator path. If event query/runtime errors appear, stop tuning: the source's exception handling can drain events and is not evidence of successful copy completion.

P: Propose a small later fresh-process comparison with identical sizes, copy direction and stream order. Check output equality, completion before host reuse, and host active/allocated bytes before/after release; compare allocation/free timings and process RAM separately. The cited reuse/statistics tests were inspected, **not run**; no hardware test is authorized by this candidate alone.

P: Return ownership classification, F evidence IDs, one eligible action, benefit/resource cost and rollback criteria. Escalate external buffers, capture integration, base-PyTorch behavior or gate conflicts before changes. Loading this skill does not authorize installation, configuration changes, benchmarks or promotion. Do not claim Network/SSD coverage.
