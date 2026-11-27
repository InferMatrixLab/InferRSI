# PyTorch pinned host buffers and CUDA copy ownership

Status: **candidate**; empirical validation: **not_run**. The
[nine-file readset](pytorch-host-copy-readset.json) pins the official PyTorch
v2.8.0 repository, exact inspected line ranges, Git blobs and raw-byte SHA-256
digests. Complete file hashing is identity verification, not whole-file or
whole-repository inspection. PyTorch's [license notice](pytorch-LICENSE.md) is
retained; this case is original analysis and examples, not vendored runtime code.

`CODE` below is observed implementation; `DOC` is an official contract or
source comment; `INFERENCE` and `PROPOSED` are explicitly separate. Scope is
ordinary eager CPU/CUDA transfers with the pinned PyTorch allocator. Driver
internals, custom/external allocators, ROCm/XPU/NPU behavior, graph implementations
and actual overlap are not qualified.

## Mechanism and boundary

| Stage | Evidence at the source pin | Consequence and limit |
| --- | --- | --- |
| Pinning | **CODE:** [Memory.cpp:44-72](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/native/Memory.cpp#L44-L72) returns already-pinned input or allocates pinned storage and copies CPU data. [CUDA backend:77-132](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/cuda/CachingHostAllocator.cpp#L77-L132) selects host allocation/registration and the matching release. | Pinning need not be free or zero-copy. Registered host RAM and GPU HBM remain different resources. |
| Copy dispatch | **CODE:** [Copy.cu:297-375](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/native/cuda/Copy.cu#L297-L375) separates contiguous, same-dtype direct copies from temporary/conversion paths. [384-423](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/native/cuda/Copy.cu#L384-L423) obtains the current stream, enqueues `cudaMemcpyAsync` when nonblocking and records host use; the blocking path calls `memcpy_and_sync`. | **CODE:** the CUDA branch of [CUDAFunctions.h:77-99](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/c10/cuda/CUDAFunctions.h#L77-L99) enqueues then synchronizes the stream. The original description that a blocking copy waits only until command issue was incorrect. |
| Host use registration | **CODE:** [Copy.cu:404-421](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/native/cuda/Copy.cu#L404-L421) supplies the host storage context and data pointer. [record_event:285-314](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/core/CachingHostAllocator.h#L285-L314) recognizes owned blocks and stores their streams, or returns false. | This is allocation tracking, not a fence that stops the caller writing a live tensor. Arbitrary external host buffers are not guaranteed to be recognized; the copy path does not check that return value. |
| Host release and reuse | **CODE:** [free:244-283](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/core/CachingHostAllocator.h#L244-L283) records events for tracked streams on release. The [CUDA specialization:145-161](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/cuda/CachingHostAllocator.cpp#L145-L161) records/queries CUDA events. [Event processing:542-581](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/core/CachingHostAllocator.h#L542-L581) makes a block reusable only after its pending events are processed. | A recognized allocation can outlive the Python tensor through allocator bookkeeping. A still-live reusable slot is different: the application must wait before mutating its payload. |
| Cache versus physical release | **CODE:** [allocate:189-241](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/core/CachingHostAllocator.h#L189-L241) rounds sizes and prefers cached blocks; [empty_cache:316-341](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/aten/src/ATen/core/CachingHostAllocator.h#L316-L341) processes events and frees available cached blocks. | Python reference release, transfer completion, availability for cache reuse and returning RAM are distinct transitions. No guarantee that all retained memory is a leak or that a user-facing GPU cache call releases this host pool. |
| Consumer order | **DOC:** [CUDA semantics:274-332](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/docs/source/notes/cuda.rst#L274-L332) orders work within a stream and requires coordination across streams. **CODE/DOC:** [wait APIs:42-71](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/torch/cuda/streams.py#L42-L71) affect future submissions and return without a CPU wait. | Record the dependency after submitting the producer and before enqueuing the consumer. A wait taken before the copy does not cover later copy submissions. |
| Device allocation lifetime | **DOC:** [record_stream:4040-4118](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/torch/_tensor_docs.py#L4040-L4118) describes tracking side-stream use or explicitly joining use back to the allocation stream before release. | This is separate from waiting for input data. Device allocator internals were not audited; this case relies on the documented API contract. |
| CPU visibility | **CODE/DOC:** [Event.query/synchronize:205-231](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/torch/cuda/streams.py#L205-L231) checks/waits for recorded work; synchronize blocks the CPU. | **INFERENCE:** a completed event after H2D permits source refill; one after D2H permits CPU destination reads. A GPU wait alone establishes neither CPU permission. |

**DOC:** the [Tensor.to contract:5228-5239](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/torch/_tensor_docs.py#L5228-L5239)
describes asynchronous conversion as an attempt for pinned and pageable memory.
[Pinning guidance:1049-1068](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/docs/source/notes/cuda.rst#L1049-L1068)
warns about cost and low-RAM pressure. Neither establishes a universal speedup,
minimum tensor size, pinning percentage or observed DMA/compute overlap.

**DOC:** [graph address lifetime:1157-1170](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/docs/source/notes/cuda.rst#L1157-L1170)
and [capture constraints:1214-1249](https://github.com/pytorch/pytorch/blob/ba56102387ef21a3b04b357e5b183d48f0afefc7/docs/source/notes/cuda.rst#L1214-L1249)
require separate analysis. A same-stream H2D is not itself evidence of a missing
barrier, and inserting a host synchronization inside capture is not a general
fix. Graph implementation and replay qualification remain excluded.

## Counterexamples and discriminating checks

These are **PROPOSED** adversarial cases, not observed failures or executed tests.

| Tempting inference | Concrete counterexample | Required discriminating check |
| --- | --- | --- |
| Synchronizing compute after the model repairs input ordering | The model on stream B reads a batch while stream A is still copying it; a later B wait only waits for already-issued incorrect computation | Insert A's completion event before B's model work; compare against a serialized reference with varied payloads and an independent transfer/compute trace |
| A pinned pool automatically protects in-place reuse | CPU `slot.copy_(next_batch)` changes the live host buffer while the prior H2D reads it | Retain each expected payload and wait for that slot's H2D event before refill; compare every batch, not just the last |
| A stream wait also protects device allocator reuse | A tensor allocated on A is consumed on B, then its last Python reference is dropped while B is still using it; A allocates another same-size tensor | Compare explicit `record_stream(B)` or a correct B-to-A join under allocator pressure; a copy wait alone is insufficient |
| Host-asynchronous D2H is CPU-readable on return | CPU reduction reads a pinned destination before its D2H event completes | Compare only after event completion against the serialized result; also verify any producing-device stream dependency |
| `non_blocking` guarantees a faster transfer | Per-request pinning or dtype/layout conversion costs more than the transfer savings, or the workload has no independent work to overlap | Separate pinning, enqueue, completed transfer and end-to-end timing; retain a no-benefit result |
| Finished transfers imply an immediate RSS drop | An inactive pinned block is cached for a later same-size request | Separate live ownership, pending events and cached allocation counters from OS memory measurements; do not diagnose a leak from RSS alone |

## Hardware validation recipe (not run)

1. Freeze the target tuple: PyTorch commit/build, CUDA runtime/driver, allocator
   configuration, device, OS/NUMA policy, model and input shape/dtype/layout.
   Pinning source identity is not proof the installed wheel has the same code.
   Define correctness gates and resource budgets in the campaign before tuning.
2. Build a deterministic serialized reference using distinct payloads per batch.
   Compare same-stream nonblocking copy, the owner procedure's side-stream slot,
   and explicitly event-ordered D2H. Cover repeated slot reuse, bursts, early
   tensor release after enqueue, zero/small/large chosen shapes and application
   dtype/layout variants. The direct-path example is not coverage of conversion
   or graph paths.
3. Exercise each counterexample in an isolated diagnostic workload, then its
   corrected counterpart. Store all outputs/mismatches and the exact ordering;
   some races will not reproduce. Do not use unsafe variants in serving and do
   not label non-reproduction a correctness proof.
4. Record CUDA events around completed transfer/compute stages and synchronize
   the terminal event before reading durations. Measure host preparation,
   pinning and enqueue time separately. Capture a timeline to establish actual
   overlap and dependency placement; enqueue latency is not transfer latency.
5. Compare steady state and burst/drain behavior with a bounded number of live
   slots. Record host memory/cached allocation observations available in that
   build, process/container limits, device allocation pressure and NUMA policy.
   Retain slow, memory-pressure and no-overlap outcomes.
6. Only after correctness, run the authorized model/quality and end-to-end
   workload with frozen controls. Report L0/L1/L2 separately from L3/L4; static
   source inspection and CPU package checks cannot establish service improvement.

No CUDA allocation, transfer, capture, model, NUMA change, memory-pressure trial
or service benchmark was executed for this knowledge update. Native validity,
fit, throughput and latency remain unverified.
