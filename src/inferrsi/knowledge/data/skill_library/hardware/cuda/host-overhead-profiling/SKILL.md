---
name: host-overhead-profiling
description: 'Detect and diagnose CPU/host overhead in inference serving from nsys traces. Answers: is host overhead the bottleneck? What specific work is causing it? Covers GPU idle ratio, host-prep exposed ratio, NVTX breakdown, inter-kernel gap analysis, and multi-rank straggler detection.

  '
---

# Host Overhead Profiling

Analyze host/CPU overhead in inference serving from nsys timeline data. This skill answers two questions:

| Phase | Question | Input | Output |
|-------|----------|-------|--------|
| **Detection** | Is host overhead the bottleneck? | Single nsys trace | YES/NO verdict with metric evidence |
| **Root Cause** | What specifically regressed? | One or two nsys traces | NVTX per-step breakdown, regression sources |

## When to Use

- Confirming the bottleneck is real before optimizing (Detection)
- GPU utilization is suspiciously low and you need to know why (Detection)
- Throughput regressed but GPU kernel execution times are unchanged (Root Cause)
- The gap between forward step iterations has increased (Root Cause)
- To compare inter-iteration overhead between two versions (Root Cause)

Do NOT use when:
- The regression is in individual kernel performance (use kernel-level profiling instead)
- You need to profile a workload from scratch (capture traces first with nsys)
- The issue is NCCL communication (use distributed analysis)

## Prerequisites

- An nsys trace file (`.sqlite` or `.nsys-rep`) from a serving benchmark run
- For Root Cause comparison: two traces (baseline and target)
- Python 3 with sqlite3 support

---

## Key Concepts

### Host Overhead in Inference

In each forward iteration:
```
[inter-step gap] -> [_forward_step] -> [inter-step gap] -> [_forward_step] -> ...
```

The **forward step** includes GPU kernel execution plus host-side preparation. The **inter-step gap** includes host-side work between steps (scheduling, request fetching, sampling, response handling).

Host overhead only hurts performance when it is **exposed** — the GPU is idle waiting for work. When host prep overlaps with GPU execution, it is **hidden** and free.

### Forward Step Isolation

In tensor-parallel configurations, forward steps are isolated via allreduce kernel grouping (deterministic count per transformer layer). For TP=1, NVTX `_forward_step` ranges are used directly. See references/iteration-isolation-techniques.md for the full algorithm.

---

## Detection Phase (YES/NO Verdict)

Determine whether host overhead is the primary bottleneck.

### Detection Metrics

Six metrics in four categories:

| # | Metric | Threshold | What it answers |
|---|--------|-----------|-----------------|
| M1 | GPU idle ratio | > 0.30 | Is the GPU starved for work? |
| M2 | Launch overhead ratio | > 0.10 | Is kernel launch itself expensive? |
| M3a | Host prep exposed ratio | > 0.50 | How well is host prep pipelined? |
| M3b | Host prep perf impact | > 0.05 | How much throughput does exposed prep cost? |
| M3c | Host prep idle attribution | > 0.50 | Is host prep the main cause of GPU idle? |
| M4 | GPU utilization | < 0.60 | Is GPU utilization too low? |
| M5 | NCCL ratio (caveat) | > 0.20 | Is communication a confounding factor? |

**Host prep confirmation rule**: Host prep is a confirmed bottleneck only when **both** M3b AND M3c cross their thresholds.

Per-phase variants (tighter for generation due to CUDA graph replay):
- Generation GPU idle ratio threshold: 0.15
- Generation GPU utilization threshold: 0.80

### Detection Workflow

#### Step 1: Input Validation

```bash
# Accept .sqlite or .nsys-rep
ls -la <trace_file>

# If .nsys-rep, export to SQLite first
nsys export -t sqlite -o <output.sqlite> <input.nsys-rep>
```

#### Step 2: Run Detection Script

```bash
python scripts/detect_host_overhead.py \
  --trace /path/to/trace.sqlite \
  --output /path/to/verdict.json
```

The script computes M1, M2, M4, M5 from SQL queries against the nsys schema, optionally M3 via NVTX range intersection, applies the verdict logic, and outputs structured JSON.

#### Step 3: Interpret Verdict

**Overall Verdict:**
```
if aggregate_verdict == YES or context_verdict == YES or generation_verdict == YES:
    overall_verdict = YES
```

Per-phase analysis can **elevate** the verdict but never **demote** it.

**Next Steps:**
- **If YES** → Proceed to Root Cause phase below, then use `host-overhead-optimization` skill
- **If NO** → Use kernel-level profiling for SOL% analysis or full trace classification

---

## Root Cause Phase

Identify which specific host operations regressed and by how much. Works with a single trace (breakdown) or two traces (comparison).

### Principles

1. **Isolate forward steps, not the full trace.** Traces contain warmup, JIT, loading, teardown.
2. **Use structural kernel patterns for iteration detection.** Allreduce grouping is more robust than kernel density.
3. **Compare steady-state iterations.** Filter to identical workload (same batch size, same context/generation mix).
4. **Per-step metrics, not totals.** Always compare per-step averages.

### Root Cause Workflow

#### Step 1: Collect nsys Traces

Profile both versions (if comparing) with identical settings:

```bash
nsys profile -o /path/to/trace \
  -t cuda,nvtx,osrt \
  --force-overwrite=true \
  --cuda-memory-usage=true \
  -w true \
  <benchmark_command> --num_requests 500
```

#### Step 2: Export to SQLite

```bash
nsys export --type=sqlite --force-overwrite=true -o trace.sqlite trace.nsys-rep
```

#### Step 3: Run Root Cause Analysis

```bash
# Two-trace comparison
python scripts/analyze_host_overhead.py \
  --baseline /path/to/baseline/trace.sqlite \
  --target /path/to/target/trace.sqlite \
  --baseline-label "v1" \
  --target-label "v2" \
  --output /path/to/output/analysis.txt

# Single-trace breakdown
python scripts/analyze_host_overhead.py \
  --baseline /path/to/trace.sqlite \
  --baseline-label "current"
```

#### Step 4: Interpret Results

The script produces:
1. **Iteration detection** — confirms forward step boundaries
2. **Per-step wall time comparison** — quantifies the regression
3. **NVTX per-step breakdown** — identifies which host operations regressed
4. **GPU kernel comparison** — confirms GPU execution is unchanged
5. **CUDA API comparison** — detects kernel launch overhead changes

**Reading the Output:**

Per-step wall time:
```
Avg wall time per step: 3,317 us (baseline) vs 3,978 us (target)  +19.9%
```

NVTX breakdown (focus on large absolute deltas):
```
Operation           | baseline (us/step) | target (us/step) | Delta    | Status
_fetch_new_requests |               36   |             270  | +234     | REGRESSION
broadcast_requests  |                -   |             250  | +250     | NEW
_prepare_tp_inputs  |              650   |             950  | +300     | REGRESSION
```

GPU kernel comparison:
```
Kernels per step (launched): 6.2 (baseline) vs 21.9 (target)  +253%
```

More individual launches = more host-side launch overhead.

---

## Common Patterns and Root Causes

### Pattern 1: Fetch-and-Validate Refactor

**Symptom**: `_fetch_new_requests` regressed 5-10x, new `broadcast_requests` operation.

**Known facts** (observed in TensorRT-LLM v1.1 to main):
- v1.1: ~36 us per step
- Recent main: ~270 us per step (+643% regression)
- `broadcast_requests` new: ~250 us per step

**Cause**: Request fetching refactored for multi-rank broadcasting in TP.

**Next step**: Run `host-overhead-optimization` targeting `_fetch_new_requests` and `broadcast_requests`.

### Pattern 2: Increased Kernel Launch Count

**Symptom**: 3-5x more `cudaLaunchKernel` calls per step, similar GPU time.

**Cause**: Operations that were fused or graph-captured are now individual launches.

**Mitigation**: Re-fuse kernels; extend CUDA graph capture scope.

### Pattern 3: New Bookkeeping Operations

**Symptom**: New NVTX ranges like `_write_finish_reasons`, `_prepare_resources` overhead increase.

**Known facts** (TensorRT-LLM recent):
- `_write_finish_reasons`: 120-200 us (new)
- `prepare_resources`: v1.1 ~192 us, main ~349 us (+81%)

**Cause**: New features added without overhead budgeting.

**Mitigation**: Defer non-critical bookkeeping to async paths; batch updates.

### Pattern 4: Context-Only Bottleneck

**Symptom**: Aggregate metrics below threshold, but context iterations show 50% GPU idle.

**Cause**: Generation iterations dilute the context-phase bottleneck.

**Fix**: Per-phase analysis in Detection phase catches this.

---

## Reference Operations from TensorRT-LLM

The following NVTX ranges are documented in the inference loop (TensorRT-LLM PyTorch backend):

| Operation | Typical Duration | Notes |
|-----------|-----------------|-------|
| `_schedule` | 100-200 us | Stable across versions |
| `_fetch_new_requests` | 36 us (v1.1) / 270 us (main) | Known regression point |
| `broadcast_requests` | 250 us | New in recent versions, TP only |
| `_prepare_inputs` / `_prepare_tp_inputs` | 500-900 us | Primary target for optimization |
| `_sample_async` | 1,163 us (v1.1) / 720 us (main) | Improved in recent versions |
| `_process_requests` | 1,056 us (v1.1) / 390 us (main) | Improved in recent versions |
| `_update_requests` | 413 us (v1.1) / 723 us (main) | Known regression point |
| `_handle_responses` | 300-420 us | Moderate increase in recent versions |
| `_write_finish_reasons` | 120-200 us | New in recent versions |
| `prepare_resources` | 192 us (v1.1) / 349 us (main) | Known regression point |

Source: TensorRT-LLM NVTX reference (Feb 2025, Llama 3.2 1B, TP=2, H200).

Batch size scaling:
- 1-2 reqs: 500-600 us
- 50-100 reqs: 1,000-1,500 us
- 200-300 reqs: 8,000-12,000 us
- 400-500 reqs: 12,000-16,000 us

---

## Limitations

**CUDA-specific tooling**: nsys, NVTX ranges, CUDA API profiling are NVIDIA-specific. For NPU/Ascend environments, use equivalent profilers (torch_npu.profiler, msprof, HCCL analysis). Concepts (host prep exposed, inter-kernel gaps, iteration isolation) transfer; specific metrics and thresholds may differ.

**Trace capture overhead**: nsys tracing itself adds overhead. Disable non-essential collectors (e.g., memory tracking) if trace size becomes unwieldy.

---

## Pitfalls

1. **NVTX textId is an integer** — Always join with StringIds table; raw textId is useless.
2. **TP rank duplication** — Each rank reports NVTX ranges independently. De-duplicate by grouping entries within 100us.
3. **Negative inter-step gaps** — When ranks overlap, `gap = next_start - prev_end` can be negative. Use maximum end time.
4. **Benchmark window selection** — Allreduce-based window captures context+generation; steady-state NVTX filtering captures generation-only. Both are valid; use appropriate one for your goal.

---

## Handoff to Optimization

When analysis is complete and verdict is **YES**, hand off to `host-overhead-optimization` skill with:

1. **Detection verdict**: Which metrics crossed thresholds, whether host prep was confirmed.
2. **NVTX-based triage**: Top regressing operations by absolute delta (us/step) — these become profiling targets.
3. **Handoff data**: Structured output from detection script (thresholds, per-phase breakdown).
