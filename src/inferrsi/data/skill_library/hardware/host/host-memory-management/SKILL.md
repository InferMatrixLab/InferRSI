---
name: host-memory-management
description: 'Configure host memory for inference serving: pinned memory for fast H2D transfers, async transfer streams, Python GIL avoidance patterns, and NUMA-aware allocation. Also route versioned Ascend native offload descriptor retention to its source case. Complements host-overhead-profiling (detect the bottleneck) and host-overhead-optimization (optimize Python execution).

  '
---

# Host Memory Management

Configure host-side memory for inference serving to reduce latency and increase throughput. This skill covers four independent mechanisms:

1. **Pinned memory** — allocate host memory that the GPU can access directly for fast H2D/D2H transfers
2. **Asynchronous H2D transfers** — overlap CPU-side preparation with GPU compute via separate CUDA streams
3. **Python GIL avoidance** — use multiprocessing or free-threaded Python to avoid single-threaded bottlenecks in request preprocessing
4. **NUMA-aware allocation** — bind processes and tensors to the same NUMA node as the GPU to avoid cross-socket latency

When to use this skill:

- Host-to-device transfer is a measured bottleneck (confirmed by nsys or manual timing)
- Requests are being fetched/processed on the CPU while GPU is idle
- Running on multi-socket systems (e.g., two CPU sockets, one GPU per socket)
- Python multiprocessing overhead is high due to GIL contention in request handling

**Do not use this skill for:**
- Profiling or root-cause analysis (use `host-overhead-profiling` instead)
- Line-by-line optimization of Python hotspots (use `host-overhead-optimization` instead)

---

## Versioned Ascend native descriptor-pool case

Use the [native single-tier source case](references/vllm-ascend-native-offload.md) when a vLLM-Ascend worker retains CPU pointer/size arrays after submission or a tracked-job wait. At the pinned implementation, normal pool reuse follows a successful queue-head end-event query; submission, event recording and wait do not perform that reclamation. The reference separates descriptor ownership from CPU KV payload mirrors, allocator caches and physical RAM release, and reports shutdown ordering without a stronger lifetime claim.

This case is a source-derived candidate, with native validation not_run. The four historical mechanisms and CUDA examples below do not qualify Ascend APIs, thresholds, synchronization recipes or performance.

---

## 1. Pinned (Page-Locked) Memory

### What It Is

Pinned memory is host RAM that the GPU can access directly via DMA, bypassing CPU page translation. Transfer speed improves from ~3–5 GB/s (pageable) to 6–12 GB/s or higher (pinned), depending on hardware.

**Source (observed)**: PyTorch documentation on [CUDA semantics](https://pytorch.org/docs/1.2.0/notes/cuda.html) describes pinned memory for faster transfers. The [pinned memory allocator DevLog](https://docs.pytorch.org/devlogs/eager/2026-08-09-pinned-memory-allocator/) documents PyTorch's internal management of pinned buffers.

### When to Use

**One-sentence rule**: Use pinned memory when moving large tensors (> 1 MB) between host and GPU is a measured bottleneck, and you have spare RAM; avoid if pageable memory is the primary bottleneck or if pinning reduces available memory below 80% of workload demand.

**Specific scenarios:**
- Large batch preprocessing on CPU → GPU (e.g., 256 MB batch transferred per step)
- Repeated transfers of the same tensor across steps (e.g., query cache, prompt embeddings)
- Multi-rank inference with significant input gathering work

**Typical speedup:** 2–3x for 100 MB+ transfers; diminishing returns for small tensors (< 10 MB).

### How to Allocate

#### Method 1: Pin After Creation (Explicit)

```python
# Create tensor on CPU
tensor = torch.randn(batch_size, seq_len, hidden_dim, dtype=torch.float32)

# Pin it
pinned_tensor = tensor.pin_memory()

# Transfer asynchronously (see Section 2)
device_tensor = pinned_tensor.to(device, non_blocking=True)
```

**Source (observed)**: PyTorch API — `Tensor.pin_memory()` returns a pinned copy of the tensor. Documented in [PyTorch nn API](https://pytorch.org/docs/main/torch_cuda_memory).

#### Method 2: Pre-Allocate at Initialization (Recommended for Serving)

```python
class InputCache:
    def __init__(self, max_batch_size, hidden_dim, device):
        # Pre-allocate pinned buffers at initialization
        self.input_buffer = torch.zeros(
            max_batch_size, hidden_dim, 
            dtype=torch.float32,
            pin_memory=True
        )
        self.device = device
    
    def transfer_async(self, data, size):
        # Copy data into pinned buffer (CPU-side, synchronous)
        self.input_buffer[:size].copy_(data)
        
        # Transfer to GPU asynchronously
        return self.input_buffer[:size].to(
            self.device, non_blocking=True
        )
```

**Source (observed)**: PyTorch `torch.zeros(..., pin_memory=True)` parameter, documented in the [pinned memory Discourse thread](https://discuss.pytorch.org/t/when-to-set-pin-memory-to-true/19723/25).

#### Method 3: Automatic via DataLoader

```python
# For offline batch preprocessing
dataloader = DataLoader(
    dataset,
    batch_size=256,
    pin_memory=True  # Automatically pins batches
)
```

**Source (observed)**: PyTorch DataLoader `pin_memory` parameter. Implementation in [pytorch/torch/utils/data/_utils/pin_memory.py](https://github.com/pytorch/pytorch/blob/main/torch/utils/data/_utils/pin_memory.py).

### Cost and Limitations

**Memory overhead**: Pinning memory reserves it from the OS page pool. Over-pinning reduces available pageable memory and can slow down CPU operations (swapping increases).

**Guideline**: Pin no more than 30–50% of total system RAM on production systems; monitor page faults with `vmstat 1` (Linux) or Task Manager (Windows).

**Incorrect pattern — avoid**:
```python
# SLOW: pin after allocation from GPU memory
tensor = torch.randn(..., device='cuda')
pinned = tensor.cpu().pin_memory()  # Double copy: GPU → CPU (slow) → pinned
```

**Source (observed)**: PyTorch forum discussion on [pin_memory().cuda() being slow](https://discuss.pytorch.org/t/why-is-tensor-pin-memory-cuda-significantly-slower/216122).

---

## 2. Asynchronous Host-to-Device Transfers

### What It Is

By default, `.to(device)` transfers block the CPU thread until the GPU command is issued. Using `non_blocking=True` and custom streams decouples CPU and GPU timelines, allowing CPU preprocessing to continue while data moves in the background.

**Source (observed)**: PyTorch [CUDA semantics documentation](https://pytorch.org/docs/1.2.0/notes/cuda.html) describes stream-based async operations. NVIDIA's [sync-free CUDA graph best practice](https://docs.nvidia.com/dl-cuda-graph/latest/torch-cuda-graph/sync-free-code.html) covers stream synchronization patterns. PyTorch DevLog on [hidden H2D syncs](https://docs.pytorch.org/devlogs/eager/2026-08-11-hidden-h2d-sync/) documents synchronization hazards.

### Basic Pattern: Non-Blocking Transfer

```python
# Step 1: Fetch data on CPU (blocks only if GPU transfer is pending)
batch_data = fetch_batch()

# Step 2: Issue async transfer (returns immediately)
device_tensor = batch_data.pin_memory().to(device, non_blocking=True)

# Step 3: Continue CPU work (e.g., fetch next batch)
next_batch_data = fetch_batch()

# Step 4: Before using device_tensor in a kernel, synchronize
torch.cuda.synchronize()  # Wait for the transfer to complete
result = model(device_tensor)
```

**Key requirement**: Always call `torch.cuda.synchronize()` before using the transferred tensor in a kernel. Without it, the GPU kernel may execute before the transfer completes, causing incorrect results or silent memory corruption.

**Source (observed)**: [Stack Overflow question on non_blocking H2D synchronization](https://stackoverflow.com/questions/79751502/when-does-non-blocking-h2d-copy-from-pinned-memory-in-pytorch-require-synchronization) confirms the synchronization requirement.

### Advanced Pattern: Separate Stream for Transfer

For maximum CPU-GPU overlap, transfer on a side stream while the main stream executes compute:

```python
import torch

class AsyncTransferPipeline:
    def __init__(self, device):
        self.device = device
        self.transfer_stream = torch.cuda.Stream()
        self.compute_stream = torch.cuda.Stream()
    
    def forward(self, model, input_tensor):
        """
        Overlap transfer of next batch with compute on current batch.
        """
        # Step 1: Transfer on side stream (batched, asynchronous)
        with torch.cuda.stream(self.transfer_stream):
            device_input = input_tensor.pin_memory().to(
                self.device, non_blocking=True
            )
        
        # Step 2: Compute on main stream (can overlap with transfer)
        with torch.cuda.stream(self.compute_stream):
            # This kernel may start before transfer completes
            output = model(device_input)
            # But we must sync before reading output on CPU
            self.compute_stream.synchronize()
        
        return output
```

**Synchronization requirement**: When compute and transfer happen on different streams, insert `stream.synchronize()` or `torch.cuda.synchronize()` before accessing the result on either the CPU or another stream.

**Source (observed)**: PyTorch [CUDA Streams documentation](https://pytorch.org/docs/main/generated/torch.cuda.Stream.html) documents stream creation and synchronization. PyTorch forum on [async H2D on side stream](https://discuss.pytorch.org/t/is-it-possible-that-pytorch-can-make-async-host-to-device-transfer-execute-on-side-stream-while-the-transferred-data-on-the-main-stream/223702) confirms the pattern.

### Pitfall: CUDA Graph Synchronization

If using CUDA graphs (for low-latency inference):

```python
# WRONG: Graph capture includes async transfer but no explicit sync
graph = torch.cuda.CUDAGraph()
with torch.cuda.graph(graph):
    device_tensor = host_tensor.to(device, non_blocking=True)
    output = model(device_tensor)  # May execute before transfer completes
```

**Fix**: Ensure H2D transfer is complete before graph capture, or move the transfer outside the graph:

```python
# RIGHT: Transfer outside graph, sync before capture
device_tensor = host_tensor.pin_memory().to(device, non_blocking=True)
torch.cuda.synchronize()  # Explicit sync

graph = torch.cuda.CUDAGraph()
with torch.cuda.graph(graph):
    output = model(device_tensor)

graph.replay()
```

**Source (inferred)**: CUDA Graphs require deterministic execution order; async operations without explicit barriers violate that contract.

---

## 3. Python GIL Avoidance

### The Problem

The Global Interpreter Lock (GIL) serializes Python bytecode execution in a single process, even with multiple threads. In request-serving pipelines, this means preprocessing (tokenization, batching) on one thread blocks all others, reducing effective CPU parallelism to ~1 core regardless of machine size.

**Source (observed)**: [PEP 703 — Making the Global Interpreter Lock Optional in CPython](https://peps.python.org/pep-0703/) formally describes the GIL and its removal in Python 3.13+.

### Pattern 1: Multiprocessing for CPU-Heavy Preprocessing (All Python Versions)

Use separate **processes**, not threads, to avoid GIL contention. Each process has its own Python interpreter and GIL.

```python
from concurrent.futures import ProcessPoolExecutor
import torch

class RequestPreprocessor:
    def __init__(self, num_workers=4):
        # One process per worker; each has its own GIL
        self.executor = ProcessPoolExecutor(max_workers=num_workers)
    
    def preprocess_batch(self, raw_requests):
        """
        CPU-heavy tokenization and embedding lookup.
        Runs on separate process — no GIL contention.
        """
        futures = [
            self.executor.submit(self._tokenize_and_embed, req)
            for req in raw_requests
        ]
        return [f.result() for f in futures]
    
    @staticmethod
    def _tokenize_and_embed(request):
        # This runs on a separate process
        tokens = tokenize(request.text)  # CPU-heavy
        embeddings = embed_lookup(tokens)  # I/O or CPU
        return torch.tensor(embeddings)
```

**Source (observed)**: Python [concurrent.futures.ProcessPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html) documentation. The pool creates separate processes, each with its own GIL.

**Trade-off**: Multiprocessing has higher overhead (process startup ~10–100 ms, IPC serialization). Use it for long-running tasks (> 100 ms each); for short tasks, overhead dominates.

### Pattern 2: Free-Threaded Python 3.13+ (Experimental)

Python 3.13 introduces an experimental build with an optional GIL. When built with `--disable-gil`, multiple threads can execute Python code simultaneously without GIL contention.

```bash
# Build or download Python 3.13 free-threaded build
python3.13 --version

# Check if free-threading is available
python3.13 -c "import sys; print(sys.flags.nogil)"  # True if enabled
```

**Code compatibility**: No changes needed; existing `threading.Thread` code runs with true parallelism.

```python
import threading

class ThreadedPreprocessor:
    def __init__(self, num_threads=8):
        self.threads = []
        self.results = []
        self.lock = threading.Lock()
    
    def preprocess_batch(self, raw_requests):
        """
        With free-threaded Python 3.13+, these threads run in parallel.
        With standard Python, the GIL serializes them (use multiprocessing instead).
        """
        threads = [
            threading.Thread(target=self._worker, args=(req,))
            for req in raw_requests
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return self.results
    
    def _worker(self, request):
        result = self._tokenize_and_embed(request)
        with self.lock:
            self.results.append(result)
```

**When to use**: Python 3.13+ with free-threading enabled (or Python 3.14+ when it becomes standard). For production inference, free-threading eliminates the GIL-to-multiprocessing trade-off.

**Source (observed)**: [PEP 703](https://peps.python.org/pep-0703/) documents the experimental free-threaded build. [Python 3.13 release notes](https://dev.to/zackch/python-313-no-gil-what-you-need-to-know-352i) confirm availability. [Python 3.14 roadmap](https://dev.to/mechcloud_academy/unlocking-true-parallelism-a-developers-guide-to-free-threaded-python-3-14-175i) indicates official support in 3.14.

### Pattern 3: Avoid Threading for GIL-Heavy Work (All Versions)

**Anti-pattern** — do not use threading for CPU-intensive preprocessing on standard Python:

```python
# WRONG: Threads are serialized by GIL on standard Python
import threading

def preprocess_worker():
    tokens = tokenize(request.text)  # Blocks all other threads
    return tokens

threads = [
    threading.Thread(target=preprocess_worker)
    for _ in range(4)
]
for t in threads:
    t.start()
for t in threads:
    t.join()
# Total time ≈ sum of all task times (no parallelism)
```

---

## 4. NUMA-Aware Allocation

### What NUMA Is

NUMA (Non-Uniform Memory Access) is a multi-socket server architecture where each CPU socket has local RAM (low latency) and can access other sockets' RAM (high latency). A typical B300 server has two CPU sockets and one or two GPUs attached to specific sockets.

Allocating memory on the wrong socket causes cross-socket traffic, increasing latency by 2–3x. Similarly, pinning worker threads to CPU cores on the wrong socket increases latency.

**Source (observed)**: [NUMA, numactl, and taskset guide](https://tonyseah.medium.com/numa-numactl-and-taskset-a-practical-guide-for-ai-ml-engineers-0fbacb450f22) describes NUMA topology and affinity. [NVIDIA memory management on hardware-coherent platforms](https://developer.nvidia.com/blog/understanding-memory-management-on-hardware-coherent-platforms/) covers GPU NUMA considerations.

### Step 1: Check NUMA Topology

```bash
# List NUMA nodes and their CPUs
numactl --hardware

# Example output (2-socket system):
# available: 2 nodes (0-1)
# node 0 cpus: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
# node 0 size: 188000 MB
# node 1 cpus: 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
# node 1 size: 188000 MB

# Check which NUMA node a GPU is attached to
nvidia-smi -L  # Lists GPUs
lspci -vv | grep -A5 "NVIDIA\|AMD Radeon"  # Shows NUMA affinity
```

**Source (observed)**: `numactl` man page and NVIDIA tools documentation.

### Step 2: Bind Process to Local NUMA Node

```bash
# Bind the serving process to CPU cores on node 0 (local to GPU 0)
numactl --cpunodebind=0 --membind=0 \
  python serve.py --model <model_path>

# Check affinity of running process
taskset -p <pid>
numactl --show
```

**Source (observed)**: `numactl` and `taskset` man pages. [Production-grade NUMA pinning guide](https://ssadaniowski.substack.com/i/198715659/numa-pinning-and-gpu-affinity) demonstrates the practice.

### Step 3: Set PyTorch Device in Code

```python
import torch

class NUMAInference:
    def __init__(self, device_id=0, local_numa_node=0):
        # Set the GPU device BEFORE allocating tensors
        torch.cuda.set_device(device_id)
        
        # Allocate any host-side buffers on the local NUMA node
        # (The numactl binding from Step 2 handles this automatically)
        
        self.device = device_id
        self.model = load_model(device_id)
    
    def forward(self, input_tensor):
        # Ensure input is on the correct device
        # (pinned memory + non_blocking are independent)
        device_input = input_tensor.pin_memory().to(
            self.device, non_blocking=True
        )
        
        torch.cuda.synchronize()
        return self.model(device_input)
```

**Source (observed)**: PyTorch [CUDA semantics](https://pytorch.org/docs/master/notes/cuda.html) documents `torch.cuda.set_device()`. [Stack Overflow on CUDA device allocation](https://stackoverflow.com/questions/60593317/any-guarantees-that-torch-wont-mess-up-with-an-already-allocated-cuda-array) confirms the pattern.

### Verification

```bash
# Verify process is pinned correctly
numactl --show
# Example: cpubind: 0  membind: 0

# Monitor cross-socket memory traffic
# On Linux: numastat -p <pid>
# Example:
# Per-node process memory usage (in MB) for PID 12345 (my_serving_process):
#           Node 0 Node 1 Total
# my_serving_process 1500  50   1550
# (Most memory on node 0, minimal cross-socket)

# Check GPU affinity
nvidia-smi -q -d PCI | grep "Bus ID"
# Compare PCI slot to NUMA node location
```

### Impact and Trade-Offs

**Expected improvement**: 10–30% latency reduction on NUMA systems when properly tuned, compared to uncontrolled allocation.

**Trade-off**: Manual binding is system-specific and fragile. Portable code should remain flexible and document the assumption.

---

## Integration: Full Serving Example

```python
import torch
from concurrent.futures import ProcessPoolExecutor
import time

class OptimizedInferenceServer:
    def __init__(self, model_path, num_preprocess_workers=4):
        # NUMA: Process already pinned via numactl on startup
        torch.cuda.set_device(0)
        
        self.device = 0
        self.model = torch.jit.load(model_path).to(self.device)
        self.model.eval()
        
        # GIL: Use ProcessPoolExecutor for preprocessing
        self.preprocessor = ProcessPoolExecutor(
            max_workers=num_preprocess_workers
        )
        
        # Pinned Memory: Pre-allocate buffers
        self.max_batch_size = 256
        self.hidden_dim = 768
        self.input_buffer = torch.zeros(
            self.max_batch_size,
            self.hidden_dim,
            dtype=torch.float32,
            pin_memory=True  # Pinned for fast H2D
        )
        self.transfer_stream = torch.cuda.Stream()
    
    def preprocess_batch_parallel(self, requests):
        """
        Tokenize and embed in parallel (avoids GIL via ProcessPoolExecutor).
        """
        futures = [
            self.preprocessor.submit(self._tokenize, req)
            for req in requests
        ]
        embeddings = [f.result() for f in futures]
        return torch.stack(embeddings)
    
    @staticmethod
    def _tokenize(request):
        # CPU-bound work on separate process (no GIL contention)
        tokens = tokenize(request)
        return torch.tensor(tokens, dtype=torch.float32)
    
    def forward(self, requests):
        """
        Full pipeline: preprocess (parallel, GIL-free) → transfer (async, pinned)
        → compute (GPU) → return results.
        """
        # Step 1: Preprocess in parallel
        batch_embeddings = self.preprocess_batch_parallel(requests)
        batch_size = batch_embeddings.shape[0]
        
        # Step 2: Async transfer (pinned memory + non_blocking)
        with torch.cuda.stream(self.transfer_stream):
            self.input_buffer[:batch_size].copy_(batch_embeddings)
            device_input = self.input_buffer[:batch_size].to(
                self.device, non_blocking=True
            )
        
        # Step 3: Synchronize before compute
        torch.cuda.synchronize()
        
        # Step 4: Compute
        with torch.no_grad():
            output = self.model(device_input)
        
        return output

# Startup: Run with NUMA binding
# numactl --cpunodebind=0 --membind=0 python serving_script.py
```

---

## Limitations

**Historical CUDA examples**: The four mechanisms and serving example retain their CUDA/Python/NUMA scope. Their APIs, thresholds, synchronization advice and performance figures do not establish Ascend behavior. The [versioned native offload case](references/vllm-ascend-native-offload.md) covers a separate CPU descriptor-pool contract; it does not establish the historical `torch_npu.cuda_stream` spelling as a supported API or qualify a general NPU alternative.

**Python GIL**: Free-threaded Python 3.13+ is experimental; production readiness and third-party library compatibility vary. Multiprocessing remains stable but has higher overhead.

**NUMA complexity**: NUMA topology is system-specific and changes with hardware. Portable code should detect topology at runtime and adapt.

---

## References

- [PyTorch CUDA semantics](https://pytorch.org/docs/1.2.0/notes/cuda.html) — core async transfer and stream patterns
- [PyTorch pinned memory DevLog](https://docs.pytorch.org/devlogs/eager/2026-08-09-pinned-memory-allocator/) — internal allocator design
- [PyTorch DevLog on hidden H2D syncs](https://docs.pytorch.org/devlogs/eager/2026-08-11-hidden-h2d-sync/) — synchronization hazards
- [PEP 703](https://peps.python.org/pep-0703/) — Python GIL removal spec
- [NVIDIA hardware-coherent memory blog](https://developer.nvidia.com/blog/understanding-memory-management-on-hardware-coherent-platforms/) — NUMA and GPU memory interaction
- [NUMA affinity guide](https://tonyseah.medium.com/numa-numactl-and-taskset-a-practical-guide-for-ai-ml-engineers-0fbacb450f22) — practical system tuning
