# Allocation, asynchronous work and graph addresses

## Inputs and outputs

Inputs: target device, allocation sizes/lifetimes, active tensors/autograd state,
allocator backend/configuration, stream dependency graph and capture/replay
schedule. Output: a memory and dependency ledger, first lifetime violation or
bounded OOM hypothesis, with a correct eager control before timing.

## Diagnose memory growth

1. Record actual device memory plus `memory_allocated`, `memory_reserved`, peak
   statistics, workload shape sequence and when each measurement synchronizes.
   Live tensor bytes, cached reservation and all device-process memory differ.
2. Inspect retained tensors, saved autograd graphs, output caches, optimizer
   states and asynchronous work before changing allocator knobs. Appending
   loss tensors can retain history; keep detached summaries when only metrics
   are needed. `retain_graph=True` changes lifetime rather than fixing leakage.
3. Compare a fixed-shape repeated step with the changing-shape workload. Capture
   allocator stats/summary at consistent points. A large reserved-minus-allocated
   gap alone does not prove fragmentation; external library/device allocation
   can be invisible to torch's allocator statistics.
4. `empty_cache()` releases unused cached memory, not live tensors. It cannot
   free saved activations or fix invalid cross-stream dependencies. Repeated
   cache clearing can introduce allocation/synchronization overhead.
5. Identify the allocator backend before tuning. Native allocator split/cache
   controls may not apply to cudaMallocAsync. Record the exact allocator config
   and runtime support. Treat expandable segments or split thresholds as
   hypothesis-specific controls, not universal OOM remedies.
6. Reduce live residency first where justified: microbatch/accumulation,
   activation recomputation, precision, sharding or bounded output retention.
   Verify numerical/gradient equivalence and full-step resource effects.

## Native caching allocator mechanism

The native allocator associates blocks with streams, finds suitable cached
blocks, may split them and allocates from CUDA when no block fits. Large and
small pools and oversize handling reduce allocation overhead/fragmentation.
On allocation failure it can release suitable cached blocks and retry.
These are implementation policies at the pinned revision, not portable memory
threshold recommendations.

Use on an additional stream must be tracked until that stream finishes.
`record_stream` records allocator lifetime usage; it does not order producers
and consumers. The allocator processes completion events before reusing
cross-stream blocks. Capture defers/restricts event-based reclamation because
some event queries are illegal while capturing.

## Correct stream handoff

1. Identify the producer stream, consumer stream and each tensor's last use.
   CUDA work on the same stream is ordered; different streams need explicit
   dependencies. Host launch completion is not device completion.
2. Before the consumer reads/writes a produced allocation, insert
   `consumer.wait_stream(producer)` or the corresponding event wait. Even an
   empty allocation can reuse storage still associated with old work, so
   allocation-time ordering can matter despite no data read.
3. While using a tensor on a different stream, call `tensor.record_stream`
   for that stream or use a proven manual lifetime strategy that prevents
   reuse until its work finishes. A reference kept only until host enqueue
   is not sufficient if the allocator can recycle its storage too early.
4. Before the original stream consumes the result, wait for the worker stream.
   Before host access or timing, synchronize the relevant device/events.
5. Backward CUDA ops use their corresponding forward streams; autograd's
   internal dependencies do not automatically order later use of grads on
   an unrelated stream. Wait before consuming those gradients.
6. For nonblocking H2D copies, keep pinned source buffers alive and unmodified
   until the transfer completes. Avoid returning device tensors from loader
   workers. Use the host-memory owner for residency/NUMA pressure decisions.

The bundled [CUDA lifetime diagnostic](../scripts/cuda_lifetimes.py) has
`--mode streams` and `--mode graph`. It exits with a backend-block status when
CUDA is absent; it never silently changes to CPU. Execute only in a selected
CUDA environment. It allocates tiny tensors, not a model or benchmark dataset.

## CUDA graph workflow

1. First make eager code correct and warmed on a side stream. Fix shapes,
   dtype/layout, grad mode and control flow; avoid capture-unsupported host
   synchronization, data-dependent Python and operations using external state.
2. Hold long-lived static input/output tensors and a CUDAGraph object. Capture
   the operation using those buffers. Replay uses captured device addresses;
   rebinding a Python input name does not update captured storage.
3. Copy new data into the same input buffers before replay, in the correct
   stream order; consume output only after replay completion/order is ensured.
   Validate several changed inputs against eager outputs.
4. Native graph-private pools keep baked addresses reserved while graph/pool
   ownership survives. Include that retained high-water residency in memory
   accounting. Destroying a Python variable is not necessarily releasing every
   reference to the graph or captured allocation.
5. Sharing pools across graphs requires a compatible, proven replay order and
   lifetime schedule. Avoid concurrent/overlapping reuse unless its documented
   contract has been qualified. A smaller memory reading cannot prove safety.
6. Graph capture for training requires stable gradients/optimizer storage and
   supported optimizer behavior; start from an eager training control and
   qualify all state updates. Compiler-managed CUDA Graph Trees are a separate
   lifecycle owner; diagnose via compiler logs and retained output boundaries.

ROCm can expose torch.cuda-compatible APIs but requires actual HIP/runtime
qualification. MPS, XPU, MTIA and external backends have their own allocator,
stream and graph contracts; do not transplant CUDA-specific lifetime code by
renaming the device. Their source inventory is breadth, not native verification.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`docs/source/notes/cuda.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/cuda.md)
- [`c10/cuda/CUDACachingAllocator.cpp`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/c10/cuda/CUDACachingAllocator.cpp)
- [`test/test_cuda.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/test/test_cuda.py)
