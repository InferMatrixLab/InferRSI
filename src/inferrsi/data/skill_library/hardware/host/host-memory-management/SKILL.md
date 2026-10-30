---
name: host-memory-management
description: 'Audit pinned host buffers and asynchronous CUDA transfers: distinguish copy ordering, host mutation/reuse and device allocator lifetime; use bounded PyTorch source evidence, a reusable staging-slot example and a hardware validation recipe. Also route Ascend native descriptor retention, Python preprocessing and NUMA placement to their scoped sources.'
---

# Host Memory Management

Use this candidate when profiling implicates CPU preparation, host memory pressure
or transfers between host and accelerator. These procedures propose checks; they
do not establish a throughput gain or safe memory percentage.

The [source case](references/pytorch-host-copy.md) and
[readset](references/pytorch-host-copy-readset.json) inspect selected PyTorch
v2.8.0 implementation and official documentation directly. The separate
[CPython document readset](references/cpython-free-threading-readset.json) only
corrects build/runtime GIL detection and compatibility guidance. Neither is a
device test. Status remains **candidate**, empirical validation **not_run**.
Historical links that were not revalidated are retained as
[lineage](references/legacy-source-notes.md), not evidence for new claims.

For root-cause profiling use `host-overhead-profiling`; for Python hotspots use
`host-overhead-optimization`. Separate host payload, transfer dependency and
storage ownership before selecting an optimization.

## Versioned Ascend native descriptor-pool case

Use the [native single-tier source case](references/vllm-ascend-native-offload.md) when a vLLM-Ascend worker retains CPU pointer/size arrays after submission or a tracked-job wait. At the pinned implementation, normal pool reuse follows a successful queue-head end-event query; submission, event recording and wait do not perform that reclamation. The reference separates descriptor ownership from CPU KV payload mirrors, allocator caches and physical RAM release, and reports shutdown ordering without a stronger lifetime claim.

This case is a source-derived candidate, with native validation not_run. The
CUDA allocation and stream APIs below do not qualify Ascend APIs,
synchronization recipes or performance.

## 1. Pinned host memory: ownership before capacity

**Observed source:** PyTorch's CUDA host allocator obtains page-locked host
storage through `cudaHostAlloc`, or through allocation/page mapping followed by
`cudaHostRegister` when configured. These are host allocations, not device HBM.
The [allocator/copy case](references/pytorch-host-copy.md#mechanism-and-boundary)
traces their release, cache and event handling.

`cpu_tensor.pin_memory()` returns the tensor when already pinned; otherwise
the inspected implementation allocates pinned storage and copies the CPU data.
Pinning on every request therefore adds work. Compare pageable input, per-request
pinning, a bounded reusable slot, and DataLoader `pin_memory=True` only when
DataLoader fits the workload. The latter is documented behavior here; the
DataLoader worker/pinning implementation was not inspected.

No tensor-size threshold, bandwidth multiplier or fraction of system RAM is
universal. Budget all live slots, in-flight transfers, allocator cache,
preprocessing buffers and other processes; measure host memory and allocation
costs under the actual container/OS limits. A PyTorch host allocation leaving
Python scope can enter an event queue or cache instead of immediately returning
physical memory to the OS. GPU `empty_cache()` is not a general host-pool flush
or a substitute for releasing live storage.

## 2. Asynchronous transfer: three independent obligations

`non_blocking=True` asks PyTorch to attempt a host-asynchronous conversion; it
does not promise an immediate return, compute overlap, or correct use on a
different stream. The inspected direct CPU/CUDA path enqueues a copy on the
current CUDA stream and records the host allocation's use. Dtype/layout changes
can take a temporary/conversion path. See
[dispatch and lifetime evidence](references/pytorch-host-copy.md#mechanism-and-boundary).

| Obligation | Required action | What it does not do |
| --- | --- | --- |
| Copy before a device consumer | Keep copy and consumer on the same stream, or enqueue `consumer.wait_event(copy_done)` / `consumer.wait_stream(copy_stream)` after the copy was submitted | A wait issued after the consumer cannot repair an earlier read |
| Host payload lifetime and mutation | Keep the source owner valid and do not refill, resize or mutate it until its H2D completion event finishes | A GPU stream wait does not block a CPU writer; allocator tracking does not stop writes through a live alias |
| Device storage lifetime on another stream | Use `device_tensor.record_stream(consumer)`, or explicitly order all side-stream uses back to the allocation stream before release | `record_stream` does not create a copy-to-compute data dependency |

**Same-stream consumers do not need a device-wide barrier just because H2D is
asynchronous.** A later kernel in that stream is ordered after the copy. For an
asynchronous D2H destination, the CPU must wait for the copy's completion before
reading it. For CPU reuse of an H2D source, an event wait on the CPU is similarly
different from a GPU stream wait.

### Example: one reusable host slot, current-stream consumer

This is an original eager CUDA example derived from the source contracts, not a
tested serving implementation. Preconditions: one calling CPU thread, one
explicit CUDA device, fixed dense contiguous CPU input shape/dtype, no concurrent
writers or external aliases to the staging slot, and a model already prepared
on the caller's current stream. Call the model on that same stream after
`enqueue`; a later stream handoff needs its own ordering and lifetime handling.
The example covers normal successful calls with a tensor-valued model result;
concurrency, cancellation and error recovery need a separate retirement design.

```python
import torch


class PinnedTransferSlot:
    def __init__(self, shape, dtype, device):
        self.device = torch.device(device)
        self.host = torch.empty(shape, dtype=dtype, pin_memory=True)
        self.copy_stream = torch.cuda.Stream(device=self.device)
        self.copy_done = None

    def enqueue(self, cpu_batch):
        if (
            cpu_batch.device.type != "cpu"
            or cpu_batch.shape != self.host.shape
            or cpu_batch.dtype != self.host.dtype
            or not cpu_batch.is_contiguous()
        ):
            raise ValueError("Expected a contiguous CPU batch matching the slot")
        # CPU wait: previous DMA must finish before this host slot is refilled.
        if self.copy_done is not None:
            self.copy_done.synchronize()
        self.host.copy_(cpu_batch)
        with torch.cuda.stream(self.copy_stream):
            device_batch = self.host.to(self.device, non_blocking=True)
            copied = torch.cuda.Event()
            copied.record(self.copy_stream)
        self.copy_done = copied
        consumer = torch.cuda.current_stream(self.device)
        consumer.wait_event(copied)  # GPU ordering, without a CPU wait.
        device_batch.record_stream(consumer)  # Device allocator lifetime.
        return device_batch

    def close(self):
        if self.copy_done is not None:
            self.copy_done.synchronize()  # Retire outstanding host use.
```

A call site keeps model work on the selected device's current stream:

```python
# model and cpu_batch are prepared by the application before this example.
device = torch.device("cuda:0")  # Select the application device explicitly.
with torch.cuda.device(device):
    slot = PinnedTransferSlot(cpu_batch.shape, cpu_batch.dtype, device)
    try:
        with torch.no_grad():
            output = model(slot.enqueue(cpu_batch))
        # Additional batches may reuse slot only through enqueue().
        # Blocking D2H on this consumer stream supplies a CPU-readable result.
        output_cpu = output.cpu()
    finally:
        slot.close()
```

The slot's host wait covers the previous H2D, not the whole compute stream.
Separately allocated device batches permit previous compute and a later copy to
overlap if scheduling/hardware allow it; this is not a claim that they do.
A ring of slots requires per-slot ownership and completion accounting. Its
capacity and memory cost must be measured, not selected from a universal rule.

### CUDA graph boundary

A same-stream copy followed by compute is not inherently unordered during graph
capture. The inspected graph documentation instead requires graph-safe work,
stable captured addresses and long-lived input/output tensors, and prohibits
CPU/GPU synchronization operations during capture. The eager slot above
allocates per-call device tensors and may synchronize the CPU; it is **not a
capture recipe**. New input writes must be ordered before replay, and reuse
must respect replay completion. Capture/replay implementations and multi-stream
capture restrictions were not qualified by this readset.

## 3. Python preprocessing: check the actual interpreter

Treat GIL-bound Python execution, native work that releases the GIL, I/O and IPC
as separate measurements. More worker processes or threads need a correctness,
serialization and resource-cost comparison; no fixed task duration or startup
time determines the winner.

The [CPython v3.13.0 document slice](references/cpython-free-threading-readset.json)
describes an optional experimental free-threaded build. Build capability and the
running process's GIL state are different. Inspect them after importing the
application's actual dependencies:

```python
import sys
import sysconfig

free_threaded_build = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
gil_enabled = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else None
print({"free_threaded_build": free_threaded_build, "gil_enabled": gil_enabled})
```

At that pin an incompatible C extension can re-enable the GIL. A Python version
number alone proves neither disabled GIL nor PyTorch/extension compatibility.
Explicit locks are still needed for shared mutable state. This document does not
qualify later Python releases or a free-threaded inference stack.

## 4. NUMA placement: inspect the target

The pinned CUDA host-allocator source warns about allocation and use across
NUMA nodes. That comment establishes a concern, not a measured penalty or a
promise that choosing a CUDA device controls CPU affinity and host page
placement. Do not infer a server's socket or GPU topology from its model name.

Use the existing `os-process-placement` owner to inspect topology and choose
CPU/memory policy before allocation. Verify actual placement, first-touch
behavior and per-process memory on the target; hold policy constant in a
comparison. Host registration mode, multiple workers, containers and available
local memory can change the result. This readset did not inspect OS/driver NUMA
implementation or execute placement commands.

## Counterexamples and validation

Before applying a transfer optimization, work through the
[concrete failure cases and hardware recipe](references/pytorch-host-copy.md#counterexamples-and-discriminating-checks).
Validate data ordering and lifetime under stress first, then measure CPU enqueue,
pinning, transfer, model and end-to-end time separately. Retain counterexamples
that did not reproduce; a passing small sample cannot prove an unsafe pattern
safe. Required CUDA/model/quality/memory/service validation is **not_run**.
