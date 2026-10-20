---
name: host-overhead-optimization
description: 'Profile and reduce CPU/host overhead in inference serving using line_profiler. Iterative profile-analyze-optimize-validate loop targeting Python execution in request preparation, scheduling, and model execution coordination.

  '
---

# Host Overhead Optimization

Automates detection and optimization of host-side (CPU) overhead in serving workloads.

## When to Use

- GPU utilization is low during inference (CPU bottleneck suspected)
- Host overhead has been confirmed as the bottleneck by `host-overhead-profiling`
- Optimizing request throughput (requests/sec)
- Need line-by-line profiling of specific Python functions

### Confirming the Bottleneck

line_profiler measures *where* CPU time is spent but not *whether* CPU is the bottleneck.

If you need to confirm CPU is the limiting factor, run the `host-overhead-profiling` skill first — it provides a YES/NO verdict with metric evidence.

**Rough heuristic without profiling data**: If doubling the batch size does not proportionally increase GPU utilization or throughput, CPU overhead is likely the bottleneck.

### Using Analysis Results

If `host-overhead-profiling` has already been run, use its output to prioritize targets:

1. **Detection verdict**: If YES with host_prep_confirmed, start with `_prepare_tp_inputs`.
2. **NVTX triage**: The top regressing operations (by absolute us/step delta) become profiling targets. Map NVTX range names to source functions using the reference below.
3. **Cross-function triage**: When the top regression is NOT `_prepare_tp_inputs` (e.g., `_fetch_new_requests`, `broadcast_requests`, `_update_requests`), profile that function's source directly instead of defaulting to `_prepare_tp_inputs`.

---

## Cross-layer redirection

When a kernel change exposes serialization, feature materialization or assembly,
reassign the bottleneck to the actual owner. Compare removable exposed time with
locally measured uncertainty; the paper's noise percentage is not a universal
law. Invariant reuse, views/shared buffers and preallocation require explicit
immutability, lifetime and ordering guarantees. They are not automatically safe.

The [cross-layer procedure](../../../methods/performance-ceiling-analysis/references/papers-20261015/redirect-cross-layer-optimization/procedure.md)
and [FlashVector audit](../../../methods/performance-ceiling-analysis/references/papers-20261015/references/flashvector.md)
retain the resource trade-offs and SLO counterexample. A component-level gain
needs matched full-stack measurement before a service claim. Re-profile and
reconsider batching/instance configuration after a change, under the same budget
and all SLOs. Reading this skill starts no autonomous loop or deployment.

## Profiling Setup

### line_profiler (Primary Method)

**Environment Variables:**
```bash
TLLM_LINE_PROFILER_ENABLED=True
TLLM_LINE_PROFILER_PATH=/path/to/output.prof
TLLM_LINE_PROFILER_FUNCTIONS="module.Class.method1,module.Class.method2"
```

**Function specification format:**

Class methods (module path, class name, method name):
```bash
tensorrt_llm._torch.pyexecutor.model_engine.PyTorchModelEngine._prepare_tp_inputs
```

Standalone functions (use `::` separator):
```bash
tensorrt_llm._torch.pyexecutor.sampler::_group_requests_by_strategy_key
```

Multiple functions (comma-separated):
```bash
TLLM_LINE_PROFILER_FUNCTIONS="tensorrt_llm._torch.pyexecutor.model_engine.PyTorchModelEngine._prepare_tp_inputs,tensorrt_llm._torch.pyexecutor.executor.PyExecutor._schedule"
```

### CPU Affinity (Environment Factor)

CPU core affinity significantly affects host overhead on multi-socket systems (e.g., B300). Pinning processes to cores near the GPU's NUMA node reduces cross-socket memory access latency.

- Check affinity: `taskset -p <pid>` or `numactl --show`
- Pin to local NUMA node: `numactl --cpunodebind=<node> --membind=<node>`
- **Impact**: Up to 2x difference in host overhead on NUMA systems

When comparing profiling results, ensure CPU affinity is consistent across runs. Document the affinity setting in each round's report if it varies.

### Workspace & Suffix Management

Each profiling run needs a unique suffix to track progress:
```bash
EXTRA_SUFFIX=round0_baseline bash profile.sh
EXTRA_SUFFIX=round1_eliminate_redundant_iter bash profile.sh
```

---

## Autonomous Optimization Loop

Before starting, understand the key insight: **Optimizations are NOT independent.** Fixing a 50ms bottleneck may reveal a 30ms bottleneck that was previously hidden. Always re-profile after each significant change — the bottleneck landscape shifts.

**Ordering principle**: Prefer the smallest evidence-supported change. Caching, preallocation and hoisting still require lifetime, invalidation, ownership and correctness checks; expected savings must come from the current workload.

Run up to N rounds (default 3) of this cycle:

```
FOR round = 1 to MAX_ROUNDS:
  1. PROFILE (with Drill-Down if needed)
  2. ANALYZE (Multi-Option)
  3. OPTIMIZE (Apply Change — prefer evidence-supported first)
  4. TEST (Unit Test Validation)
  5. VALIDATE (Re-Profile — expect bottleneck landscape to shift)
  6. REPORT

END FOR → FINAL SUMMARY
```

### Phase 1: PROFILE (with Drill-Down)

- Run workload with profiler enabled
- Parse output: identify functions with highest Total time and lines with highest % Time
- **Critical: Drill down into sub-functions that are not yet profiled**

#### Drill-Down Profiling

When a profiled function shows most time in a single sub-call (>80%), you must drill down:

```
Line #      Hits         Time    Per Hit   % Time  Line Contents
==============================================================
  2848      4100  59200000000.0  14439024.4   98.7      output = self.model_engine.forward(...)
```

1. Identify the sub-function's full qualified path
2. Add it to `TLLM_LINE_PROFILER_FUNCTIONS`
3. Re-profile to get line-level data inside it
4. Analyze the **inner** hotspots

Common drill-down targets from TensorRT-LLM:
- `PyTorchModelEngine.forward` → `PyTorchModelEngine._prepare_tp_inputs`
- `PyExecutor._forward_step` → `PyTorchModelEngine.forward` or `TorchSampler.sample_async`
- `TorchSampler.sample_async` → individual sampling kernels

### Phase 2: ANALYZE (Multi-Option)

For the chosen hotspot:

1. **Identify** the top hotspots by **absolute time** (not just %) within the target function
2. **Classify** each hotspot by type:

| Type | Indicators | Severity |
|------|------------|----------|
| **HOST_SYNC** | `.item()`, `.cpu()` in per-layer forward path | Critical |
| **SYNC** | `.item()`, `.cpu()`, `synchronize()` in step-level code | Critical |
| **CUSTOM_OP** | Chain of Python tensor ops (view/slice/cast) before kernel launch | Critical |
| **GRAPH_BREAK** | Op that prevents CUDA graph capture (fix via GRAPH_EXPAND / GRAPH_SPLIT) | High |
| **ALLOC** | `torch.zeros/empty/tensor()` in loops, `.clone()` | High |
| **HOIST** | Per-layer recomputation of step-invariant values | High |
| **PYLOOP** | `for x in collection:` with many iterations | High |
| **REDUNDANT_ITER** | Multiple passes over the same collection | High |
| **DEAD_WORK** | Object construction whose results are always discarded | High |
| **CONTAINER** | Dict/set lookups in hot loops | Medium |
| **FUNCALL** | Repeated method/property calls | Medium |
| **COMM** | `dist.all_reduce`, `dist.barrier` in TP/PP paths | Medium |
| **GIL** | Lock/queue contention | Medium |
| **SERIALIZE** | `pickle.dumps/loads`, `json.dumps/loads` in request processing | Medium |
| **GC** | Periodic latency spikes, non-deterministic pauses | Low |
| **COMPUTE** | Actual computation (may not be optimizable) | Low |

3. **Propose 2-4 optimization options** in a table:

| Option | Description | Estimated Savings | Risk | Complexity |
|--------|-------------|-------------------|------|------------|
| A | Pre-allocate buffers at init | 20-30% | Low | Low |
| B | Hoist loop-invariant computation | 10-15% | Low | Medium |
| C | Fuse separate tensor ops | 15-25% | High | High |

4. **Select the best option** (prefer high-savings + low-risk; follow evidence-supported-first ordering)

### Phase 3: OPTIMIZE (Apply Change)

- Apply the selected code change with Edit tool
- **One optimization per round** — keep changes minimal and targeted
- Record the exact change (file, line range, before/after) for potential rollback

### Phase 4: TEST (Unit Test Validation)

**Mandatory** after each optimization. Find and run related tests.

**Finding related tests:**
```bash
# Search by modified file name
grep -rl "model_engine\|PyTorchModelEngine" tests/

# Search by modified function name
grep -rl "_prepare_tp_inputs\|prepare_inputs" tests/
```

**Running tests:**
```bash
pytest tests/unittest/_torch/executor/test_pytorch_model_engine.py -v -x --timeout=120
pytest tests/unittest/_torch/executor/test_pytorch_model_engine.py::TestClass::test_method -v
```

**If tests fail:**
1. Read the failure message
2. Rollback immediately (`git checkout -- <file>`)
3. Analyze why the optimization broke correctness
4. Try the next-best option from Phase 2

### Phase 5: VALIDATE (Re-Profile)

- Re-run profiler with identical workload, using suffix `round<N>_<description>`
- Compare three things:
  1. Did the **target hotspot** time decrease?
  2. Did the **overall function** Total time decrease?
  3. Did **benchmark metrics** (throughput, TPOT) improve?

**If regression detected** (function time increased or metrics worsened):
- The optimization may have triggered a CPython pitfall
- Rollback and try the next-best option from Phase 2

### Phase 6: REPORT

Log for this round:
- Round number, date, profiler settings (CPU affinity, batch size, model)
- Hotspot location (file:line) and classification
- Optimization applied (with before/after code summary)
- Time delta: function Total time before → after (absolute and %)
- Benchmark delta: throughput before → after

---

## Reading Profile Output

```
Timer unit: 1e-06 s
Total time: 1.234 s
File: /path/to/file.py
Function: my_function at line 100

Line #      Hits         Time  Per Hit   % Time  Line Contents
==============================================================
   100                                           def my_function(self):
   101       500    890000.0   1780.0     72.1       result = tensor.item()
   102       500    234567.0    469.1     19.0       return result
```

**How to read effectively:**
1. Start with **Total time** for each function — this is the overall budget
2. Sort lines by **absolute Time**, not just % Time (3% of a 60s function = 1.8s)
3. Check **Hits count** — high hits relative to expected iteration count indicates nested loops or repeated calls
4. Look for **repeated patterns** — if 10 lines each take 3%, the loop costs 30% total

---

## Stopping Criteria

Stop the optimization loop when:
1. **Iteration limit reached**: Completed N rounds (default 3)
2. **No actionable hotspots**: Top hotspots are pure GPU compute (COMPUTE type)
3. **Diminishing returns**: < 5% improvement in last 2 rounds
4. **Risk threshold**: Further optimizations require architectural changes (Cython, struct-of-arrays)
5. **Test failures**: Cannot find an optimization that passes tests

**Primary success metric**: Benchmark throughput (requests/sec) is ground truth. A function-level speedup that doesn't improve throughput is not a real win.

---

## Primary Target Function: `_prepare_tp_inputs`

The `_prepare_tp_inputs` method in `PyTorchModelEngine` is the primary target when host_prep is confirmed in `host-overhead-profiling`.

**Location**: `tensorrt_llm._torch.pyexecutor.model_engine.PyTorchModelEngine._prepare_tp_inputs`

**Common hotspot types** within this function:
- **PYLOOP** over requests constructing input tensors
- **REDUNDANT_ITER** — same collection iterated multiple times
- **DEAD_WORK** — tensor constructions whose results are discarded
- **CUSTOM_OP** — chains of Python tensor ops (view/slice/reshape) before model launch

**Optimization patterns** for `_prepare_tp_inputs`:
- Pre-allocate input buffers at initialization instead of per-step
- Hoist request-to-position mapping outside the loop
- Batch tensor operations instead of per-request concatenation
- Reduce tensor copies via in-place operations where safe

---

## Alternative Target Functions by NVTX Regression

If the top regression from `host-overhead-profiling` NVTX triage is NOT `_prepare_tp_inputs`, profile these instead:

| NVTX Operation | Source Function | Typical Hotspot |
|---|---|---|
| `_fetch_new_requests` | `ExecutorRequestQueue.fetch_new_requests` | Queue polling, request validation |
| `broadcast_requests` | `PyExecutor._broadcast_requests` | TP collective communication prep |
| `_update_requests` | `PyExecutor._update_requests` | State synchronization, token tracking |
| `_schedule` | `RequestScheduler.schedule_request` | Scheduling policy evaluation |
| `_sample_async` | `TorchSampler.sample_async` | Logits extraction, sampling kernel dispatch |

---

## Hotspot Classification and Patterns

Each hotspot type has standard optimization patterns:

### SYNC / HOST_SYNC (Critical)

**Pattern**: `.item()`, `.cpu()`, `synchronize()` in the hot path.

**Optimization**:
- Move sync operations outside the loop to step level
- Pre-compute boolean conditions on CPU before the step
- Use deferred host reads (collect results async, read later)

### ALLOC (High)

**Pattern**: `torch.zeros()`, `torch.empty()`, `.clone()` per-request or per-step.

**Optimization**:
- Pre-allocate buffers at initialization with maximum batch size
- Reuse buffers across steps (clear/reset instead of reallocate)
- Use in-place ops (`.fill_()`, `.copy_()`) instead of creating new tensors

### REDUNDANT_ITER (High)

**Pattern**: Same collection iterated multiple times in the function.

**Optimization**:
- Merge loops into a single pass
- Build intermediate structures in first pass, reuse in subsequent passes

### PYLOOP (High)

**Pattern**: `for x in collection:` with many iterations (100s of requests).

**Optimization**:
- Vectorize with PyTorch ops instead of Python loops
- Use batch operations (e.g., `torch.arange` + indexing instead of per-request math)

### CUSTOM_OP (Critical)

**Pattern**: Chain of Python tensor ops (view/slice/cast) that could be a single kernel.

**Optimization**:
- Replace with a custom C++/CUDA kernel (if large savings)
- Or defer to step level and batch across requests

---

## Final Summary Output

The final report should include:
- **Rounds executed**: Number of profile-optimize cycles completed
- **Cumulative improvement**: Total host time reduction (% and absolute)
- **Benchmark metrics**: Before/after comparison (throughput, latency, TPOT)
- **Optimizations applied**: List of changes with file:line and classification
- **Failed attempts**: Any optimizations tried and reverted (with reason)
- **Remaining hotspots**: Top bottlenecks that couldn't be optimized (with classification)
- **Recommendations**: Suggested follow-up for architectural changes if needed

---

## Limitations

**CUDA-specific tooling**: line_profiler and PyTorch timing are designed for NVIDIA GPUs. For NPU/Ascend environments, use equivalent profilers (torch_npu.profiler). Optimization patterns (hoisting, batching, sync avoidance) generally transfer; specific metrics may differ.

**Iteration count sensitivity**: Profile results depend heavily on batch size, model size, and workload mix. Always profile at representative operating point (steady-state batch sizes, typical request mix).

