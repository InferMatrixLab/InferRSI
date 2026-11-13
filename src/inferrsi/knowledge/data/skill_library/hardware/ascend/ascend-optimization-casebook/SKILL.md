---
name: ascend-optimization-casebook
description: 'Casebook of NPU optimization cases for Ascend inference systems: symptom → diagnosis → action → evidence records for memory-bound, compute-bound, communication-exposed, graph-compilation, and AI-CPU-fallback bottleneck classes. Use when a bottleneck has been classified and you need prior art for what to try next. Complement to inference-optimization-casebook (which covers the casebook *pattern*; this carries the actual NPU cases).

  '
---

# Ascend NPU Optimization Casebook

Status: candidate. Cases grounded in MindIE-SD @ 8481d39b and vllm-ascend
@ bc8115ed source evidence. All cases are source-grounded or inferred from
observed patterns; none have been independently re-run on a local NPU.
Mark each applied case as `locally_verified: false` until you run it.

## How to use this casebook

1. Classify the bottleneck first (see `ascend-performance-analysis` skill).
   Do not consult this casebook before you have a bottleneck class.
2. Find the matching section below by bottleneck class.
3. Read the case: understand the precondition and mechanism before applying.
4. Apply through the relevant skill or reference, then measure.
5. Record the result as a new case entry when you have a verified win or
   a clear failure with evidence.

The casebook does not run profiling or make decisions — it informs them.

---

## Bottleneck class: AI-CPU fallback

### Case: op falls back to AI_CPU core

**Symptom:** `kernel_details.csv` shows `Accelerator Core = AI_CPU` on a
hot-path operator. AI_CPU kernels are orders of magnitude slower than
AI_CORE or AI_VECTOR_CORE equivalents. This is almost always the highest-
priority fix when it appears.

**Diagnosis:** Sort `kernel_details.csv` by `Duration` descending. Any
`AI_CPU` row in the top-10 is a candidate. Cross-check `Accelerator Core ≡
Task Type` (they are the same field in different table layouts — verify
value-set equivalence before reporting).

**Common causes:**
- The PyTorch op has no `torch_npu` equivalent registered.
- The op is registered but the input dtype or shape is outside its
  supported range.
- A custom op was not compiled with the AscendC kernel.

**Action:**
1. Identify the op name from the `Type` (or `OP Type`) column.
2. Check `torch_npu.nn` or the CANN op catalog for a supported equivalent.
3. If an equivalent exists: swap the op; rerun profile; confirm `AI_CPU`
   rows disappear from the top-10.
4. If no equivalent: file a support issue or implement a custom AscendC
   operator. This is a larger task — see `ascend-operator-profiling` for
   the development loop.

**Evidence required for a PASS verdict:** before/after `kernel_details.csv`
showing the target op has moved from `AI_CPU` to `AI_CORE` or `AI_VECTOR_CORE`,
and a same-window A/B comparison showing E2E latency improvement.

**Source:** MindIE-SD `profiling-analyze` + `dit-perf-opt` @ 8481d39b.

---

## Bottleneck class: memory-bound

### Case: high mte2_ratio, low mac_ratio — DRAM bandwidth saturated

**Symptom:** `op_summary*.csv` shows `mte2_ratio / max(mac_ratio, vec_ratio)
> 1` (the derived `memory_bound` heuristic). The kernel is spending more time
moving data than computing.

**Diagnosis:** Confirm by cross-referencing `step_trace_time.csv` to ensure
`Computing` fraction is below expected. Then identify the memory-traffic
source: weight reads? activation reads? KV cache reads?

**Actions (in escalating cost order):**
1. **Kernel fusion:** if two adjacent ops both read the same activation tensor,
   fuse them so the tensor is read once. Look for elementwise + norm +
   activation chains. Check `fusion-scope-analyze` references for fusion
   boundary rules before attempting.
2. **Quantization:** reduce bytes-per-element (FP16 → INT8/FP8). For FP8 on
   Ascend: dequantize at loading time (see `ascend-model-adaptation` skill);
   verify AI Core utilization before and after — if mac_ratio does not improve,
   the gain is not materializing at the hardware level.
3. **Tiling / blocking:** increase data reuse by processing in blocks that fit
   in the AI Core local buffer (UB). This is an operator-level change requiring
   a custom kernel.

**Evidence required:** same-window A/B comparison of `mte2_ratio` and E2E
latency. A decrease in `mte2_ratio` without E2E improvement suggests the
memory-bound op was not on the critical path.

**Source:** MindIE-SD `profiling-analyze` @ 8481d39b; `dit-perf-opt` feature
interaction matrix.

---

## Bottleneck class: communication-exposed

### Case: AllReduce / AllGather blocking compute forward pass

**Symptom:** `step_trace_time.csv` shows `effective_comm = Communication -
Overlapped` is large relative to `Computing`. The communication is not being
masked by concurrent compute.

**Diagnosis:**
1. Confirm with `communication.json`: identify which collective dominates.
2. Check `Overlapped` fraction. If `Overlapped` is near 0, the collective
   is not pipelined with compute at all.
3. Verify the card group uses intra-domain topology (`npu-smi info -t topo`).
   Cross-domain collectives have inherently lower bandwidth ceiling.

**Actions:**
1. **Communication masking (comm-stream masking):** route the collective to a
   separate HCCL stream that runs concurrently with compute kernels. The upper
   bound of achievable masking is `1 - 1/n` (where n = TP/SP degree), but only
   when compute time ≥ communication time in the same step. If compute is
   shorter than communication, masking cannot fully hide the collective even
   in theory.
2. **Parallelism strategy change:** if AllReduce dominates, consider moving to
   Ulysses Sequence Parallelism (USP/AllToAll) which has lower collective size
   for sequence-parallel attention. See `ascend-distributed-parallel` skill.
3. **Topology-aware card selection:** confirm the card group is intra-domain
   (UB/HCCS). Switching to an intra-domain group can double effective bandwidth.

**Evidence required:** `step_trace_time.csv` four-tuple before and after, plus
E2E latency. Specifically: `effective_comm` should decrease; `Overlapped`
fraction should increase if masking was applied.

**Source:** MindIE-SD `profiling-analyze` Layer 4, `perf-gate`, and
`dit-parallel-opt` @ 8481d39b.

---

## Bottleneck class: graph compilation overhead

### Case: slow startup with npugraph_ex enabled

**Symptom:** inference startup takes many minutes with graph mode enabled.
Once serving begins, per-request latency is normal. This is expected behavior,
not a failure.

**Diagnosis:** startup cost = compile warmup + graph capture rounds +
multimodal encoder profiling. It scales with the number of graph shapes
captured. Excess recapture happens when the serving code presents variable
shapes to a graph configured for fixed shapes.

**Actions:**
1. Do not treat slow startup as failure unless hard errors appear in the log.
   Look for `Replaying aclgraph` — its presence confirms capture succeeded.
2. If startup time is unacceptable, reduce the number of distinct shapes by
   padding inputs to fixed sizes, or enable fewer graph features (e.g., disable
   static kernel compilation if it is not needed in this deployment).
3. Set `config.aclgraph_config.capture_limit` to bound recapture attempts.

**Evidence required:** startup timing before and after config change. Confirm
`Replaying aclgraph` still appears in the log after reducing capture scope.

**Source:** MindIE-SD `ascend-model-adaptation` references and awesome-ascend-
skills `ascend-graph-mode` @ 75ec89ce.

---

## Bottleneck class: scheduling / idle gaps

### Case: large `Free` fraction in step-trace

**Symptom:** `step_trace_time.csv` shows `Free` is a significant fraction of
step time (e.g., > 15%). The NPU is idle between compute bursts.

**Diagnosis:** look at `trace_view.json` for the host-side activity during the
`Free` period. Common causes: Python GIL contention, request batching delay,
or synchronization points in the framework that block the next kernel launch.

**Action:** this is a host-overhead problem, not an NPU problem. See the
`host-overhead-profiling` and `host-overhead-optimization` skills (RAM/Host
row) for the diagnostic and fix workflow.

**Source:** MindIE-SD `profiling-analyze` @ 8481d39b; TRT-LLM `perf-host-
analysis` @ f33e0e5f.

---

## Adding a new case

When you find a verified NPU optimization win, record it here with:

```yaml
case_id: <slug>
bottleneck_class: [memory-bound | compute-bound | comm-exposed | graph-compile | scheduling | ai-cpu-fallback]
symptom: <what the profiler showed before the fix>
precondition: <model, hardware, CANN version, configuration>
action: <what was changed>
mechanism: <why it helps at the hardware level>
evidence:
  run_id: <evidence campaign ID>
  metric_before: <value + units>
  metric_after: <value + units>
  verdict: [PASS | FAIL | INCONCLUSIVE]
  locally_verified: false
generalizes_to: <other models or hardware where this is likely to apply>
does_not_apply_when: <known failure conditions>
```

Do not add a case for an INCONCLUSIVE result. Do not add a case without a
measured metric comparison. A direction ("it seemed faster") is not evidence.
