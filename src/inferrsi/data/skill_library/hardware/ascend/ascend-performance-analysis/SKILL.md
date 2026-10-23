---
name: ascend-performance-analysis
description: 'Diagnose performance bottlenecks on Ascend NPU systems using CANN profiling data. Maps GPU profiling concepts (nsys, ncu, SOL%, roofline) to their NPU equivalents (msprof, torch_npu.profiler, CSV/JSON outputs, AI Core utilization, HCCL communication analysis). Covers measurement discipline on shared NPU machines and evidence acceptance for automated NPU optimization stages. Use when profiling data is available or a stage report needs its execution and validation evidence checked.

  '
---

# Ascend NPU Performance Analysis

Status: candidate. Source-grounded from MindIE-SD @ 8481d39b. Device-specific
claims are unverified locally (no NPU on this machine). Verify against CANN docs
and actual profiler outputs before using.

## Accepting an automated optimization stage

For a CannBot fixed-stage model-inference report, first use the
[stage-evidence reference](references/cannbot-stage-evidence.md). Bind the model,
current stage and loaded candidate code to the baseline, actual quality-validator
output and comparable measurement artifacts before accepting a stage conclusion.
Progress-file markers and self-check keywords establish only the conditions
their callbacks inspect; they do not establish numerical accuracy or a speedup.
Missing execution or validator evidence leaves the conclusion `INCONCLUSIVE`;
an observed validator failure remains `FAIL` under the frozen campaign gate.

This source-derived candidate rule adds no device result or new numeric bar.
The existing five-layer analysis and shared-machine measurement procedure below
remain the path for interpreting valid profiling evidence.

## GPU→NPU concept mapping

| GPU concept | Ascend equivalent | Notes |
|------------|------------------|-------|
| nsys timeline | `trace_view.json` (Chrome Trace format) | Same JSON schema; host + device events |
| per-kernel stats | `kernel_details.csv` | Per-NPU-op rows; 48 columns |
| SM SOL% | `op_summary*.csv` `*_mac_ratio` / `*_vec_ratio` | AI Core utilization ratios |
| Memory bandwidth | `*_mte2_ratio` / `*_mte3_ratio` | MTE = Memory Transfer Engine |
| Step/iteration time | `step_trace_time.csv` | Computing / Communication / Overlapped / Free |
| NCCL | HCCL; `communication.json` | Per-collective timing |
| nvidia-smi | npu-smi | `npu-smi info`, `npu-smi info -t topo` |
| ncu kernel-level | CANN offline profiler (`msprof`) | Not a direct equivalent; different metric model |

Source: `MindIE-SD/.agents/skills/profiling-analyze/SKILL.md` @ 8481d39b.

## Five-layer analysis pipeline

Work through these layers in order. Stop when the bottleneck is located.

### Layer 1 — step-level breakdown

Read `step_trace_time.csv`. Each row is one step with four fields:
- `Computing`: time spent in pure AI Core execution
- `Communication`: HCCL collective operation time
- `Overlapped`: communication time that ran concurrently with compute
- `Free`: idle time

Derive:
```
effective_comm = Communication - Overlapped   # exposed communication cost
compute_utilization = Computing / (Computing + effective_comm + Free)
```

If `effective_comm` dominates → communication-exposed bottleneck (see dit-parallel-opt).
If `Free` is large → scheduling / pipeline bubble.
If `Computing` fraction is small → look deeper at AI Core utilization.

**Critical: do not sum `Duration` across concurrent communication streams.** The
sum double-counts overlap. Always use `step_trace_time.csv` four-tuple as the
ground truth for stage fractions.
Source: `profiling-analyze/SKILL.md` §reading-guidelines.

### Layer 2 — kernel distribution

Read `kernel_details.csv`. Sort by `Duration` descending. Identify:
- Top-5 kernels by cumulative time (these are the high-value targets).
- Kernel type distribution: `AI_CORE` (matrix), `AI_VECTOR_CORE` (elementwise),
  `AI_CPU` (fallback, usually slow), `COMMUNICATION` (HCCL).

`AI_CPU` kernels in a hot path almost always indicate an un-fused or unsupported
op falling back to CPU. This is a high-priority fix target.

**Column aliasing — must verify before using:**
Column names vary across CANN versions. The reliable approach is to read the
header, take the unique value set of each candidate column, and match against
known enum sets. Do not assume column position or copy column names from
secondary sources.

Verified equivalences (MindIE-SD empirical, one version, one environment —
re-verify on your version):

| Meaning | In `kernel_details` | In `op_summary` |
|---------|--------------------|-----------------| 
| Operator type | `Type` (60 values incl. `Slice`/`Cast`/`hcom_*`) | `OP Type` |
| Execution unit | `Accelerator Core` (6 values) | `Task Type` |
| Data type | `Input/Output Data Types` | — |

`Core Type` in `op_statistic` is NOT equivalent — it has 5 values and omits
`COMMUNICATION`, so communication ops are silently dropped.
Source: `profiling-analyze/SKILL.md` §column-semantics.

### Layer 3 — AI Core utilization

Read `op_summary*.csv`. The key ratios:
- `*_mac_ratio`: matrix/cube core utilization (GEMM-like ops)
- `*_vec_ratio`: vector core utilization (elementwise, norm, activation)
- `*_mte2_ratio`: memory read utilization
- `*_mte3_ratio`: memory write utilization

Derived `memory_bound` heuristic:
```
memory_bound = mte2_ratio / max(mac_ratio, vec_ratio)
```
Values > 1 suggest memory-bound; < 1 suggest compute-bound. This is a heuristic,
not a precise measurement — verify with trace-level evidence.

If `op_summary` columns are all `N/A` → capture was invalid. The profiler may
report "export succeeded" while no file exists, or silently omit utilization
columns. Check: (1) file actually exists at expected path; (2) utilization
columns are non-null; (3) `check_output.py` passes.
Source: `profiling-analyze/SKILL.md` §silent-failures.

### Layer 4 — communication analysis

Read `communication.json`. For each collective (AllReduce, AllGather, AllToAll):
- Duration vs compute duration for the same step → masking ratio.
- Actual masking ratio upper bound: `1 - 1/n` where n = number of parallel
  ranks, only when compute and communication pipelines truly overlap. In
  practice, masking may be much lower due to synchronization points or
  non-pipelined placement.

For HCCL topology: run `npu-smi info -t topo` to identify intra-domain (UB/HCCS)
vs inter-domain (PCIe/SYS) links. Cross-domain collectives have higher latency
and lower bandwidth — a configuration that works at 4 cards intra-domain may not
scale to 8 cards cross-domain.
Source: `dit-parallel-opt/SKILL.md` §topology-rules @ 8481d39b.

**Single-collective latency is not reproducible across devices.** Two devices
running the same configuration may produce collective latency that differs by up
to ~2×. Use call counts and aggregate ratios for cross-device comparison; never
cite single-kernel ms across devices.
Source: `profiling-analyze/SKILL.md` §reproducibility.

### Layer 5 — optimization direction

Match the bottleneck class to a direction:

| Bottleneck | Direction |
|-----------|----------|
| `AI_CPU` ops in hot path | Port to CANN custom op or use supported torch_npu equivalent |
| High `mte2_ratio`, low `mac_ratio` | Memory-bound: increase arithmetic intensity (fusion, tiling) |
| High `mac_ratio` approaching 1.0 | Compute-bound: check quantization opportunity or algorithmic change |
| Large `effective_comm` in step trace | Communication-exposed: increase overlap (comm-stream masking, pipelining) |
| Large `Free` | Scheduling bubble: check step batching, prefill/decode overlap |
| `AI_CPU` fallback on norm/activation | Op coverage gap: check CANN version, use torch_npu.nn equivalents |

## Measurement discipline on shared NPU machines

**Cross-window comparison is invalid.** On a shared machine, the same
configuration run in two different time windows can differ by an amount
comparable to real optimization gains due to temperature, neighbor load, and
driver state. Every valid A/B comparison must use a same-window protocol:
run base and candidate interleaved within the same wall-clock session.

**Call counts are reproducible; single-kernel ms is not.** Use call counts and
aggregate ratios as the primary evidence for optimization scope. Single-kernel
ms may vary ±10% across devices; collective latency may vary ~2×.
Source: `perf-gate/SKILL.md` @ 8481d39b.

**Exploration vs acceptance state:**
- Exploration state: single-run or single-step evidence, marked `[探索]`.
  Valid for direction-finding; not valid as a committed performance claim.
- Acceptance state: same-window ≥N repetitions with A/B/A drift correction,
  three-proof evidence (HTTP 200 + byte count + log line), md5 on outputs,
  and verification that the output is correct (md5 match ≠ correct output).
  Only acceptance-state results may be entered into a performance ledger.

## Profiling collection prerequisites

Before analyzing, verify collection quality:
1. Warmup steps excluded (msprof captures warm state only).
2. At least 3-5 representative steps captured.
3. `check_output.py` passes (presence of required files, non-null utilization columns).
4. Card health: `npu-smi info` shows Health=OK; no Alarm cards.
5. For multi-card runs: card group is topologically valid (intra-domain,
   all-healthy, consistent with prior measurements).

## Known limitations

- This skill is grounded in MindIE-SD's experience with MiniMax-H3 diffusion
  models on Ascend. Different models (LLMs, encoders) may have different
  dominant bottlenecks.
- CANN column names and file formats vary across versions. Always verify column
  semantics on your specific version before reporting.
- Empirical thresholds (±10% kernel drift, ~2× collective variance) are from a
  single two-device experiment. Re-test on each new hardware/software combination.
- No local NPU verification. All claims are source-grounded.
