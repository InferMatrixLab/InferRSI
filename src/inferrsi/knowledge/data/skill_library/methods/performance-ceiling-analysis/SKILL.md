---
name: performance-ceiling-analysis
description: 'Estimate optimization headroom before modifying an inference system. Produces a three-level ceiling model (analytical, empirical component, end-to-end) and a prioritized measurement plan. Use when asked whether a target speedup is worth pursuing, or to identify the binding bottleneck.

  '
---

# Performance Ceiling Analysis

Status: candidate. Procedures have not been evaluated against a real campaign.

## When to use this skill

Use this skill before modifying an inference serving system when you need to
answer: *does meaningful headroom exist, where is it, and is a requested
speedup such as 2× plausible?*

Do not use it to benchmark or compare two already-built candidates — that is
the job of InferRSI's AB/BA harness and `rsi-evidence` skill.

## Evidence to inspect first

Before profiling, gather what you can analytically:

1. Model architecture config (layer counts, hidden dims, attention heads,
   batch sizes, sequence/frame lengths, codec/VAE structure).
2. Hardware specification: peak FP16/BF16/INT8 FLOP/s, peak memory bandwidth,
   L2 size. For NVIDIA B300: INSUFFICIENT_EVIDENCE (no local datasheet values;
   must be resolved via vendor documentation or an empirical measurement).
3. Existing benchmark numbers if available: throughput frames/s, TTFA p50/p95,
   RTF mean. Label their provenance (author-reported, local measurement, etc.).

## Three-level ceiling model

### L1 — Analytical ceiling

Requires only model config and a hardware table entry.

For supplied single-resource work/traffic counts, the bundled
[pure helper](scripts/roofline.py) implements the arithmetic under an explicit
[input/output contract and synthetic attachment example](references/roofline-contract.md).
It preserves sources and unknowns; it does not collect hardware facts, estimate
model work or establish attainable speedup, goal acceptance or E2E performance.

For a remotely reusable input prefix, the
[Mooncake source comparison](references/mooncake-prefix-reuse-feasibility.md)
relates KV loading time to saved prefill work. Its paper-specific inequality
screens a candidate; current cache validity, effective rates, exposed costs and
service outcomes still require evidence.

For throughput-oriented offline inference with CPU/disk offload, use the
[FlexGen feasibility comparison](references/flexgen-offload-feasibility.md) to
check joint weights/KV/activation placement, resident plus working-memory peaks,
and exposed transfer/CPU costs against the latency objective. Its fitted,
overlap-dependent prediction is separate from the L1 helper and requires
current resource and execution evidence before a throughput recommendation.

**FLOPs per forward pass:**

For a linear projection of shape (batch × seq, in_channels, out_channels):
```
FLOPs = 2 × batch × seq × in_channels × out_channels
```
For multi-head attention QK projection + softmax + SV projection:
```
FLOPs_QK = 2 × batch × heads × seq² × head_dim
FLOPs_SV = 2 × batch × heads × seq² × head_dim
FLOPs_attn ≈ 4 × batch × heads × seq² × head_dim
```
For a DiT model, the dominant stages are the attention and MLP blocks inside
each transformer layer, plus the VAE encoder/decoder. LLM-Viewer's
`model_analyzer.py` (function `analyze_model`) walks each layer type and sums
FLOPs using these formulas.
Source: `hahnyuan/LLM-Viewer` @ 1893e4b5, `model_analyzer.py`.

**Memory traffic per forward pass:**

Traffic = bytes read (weights + KV) + bytes written (activations). For
inference with a frozen model, weight traffic dominates; KV cache traffic
dominates in decode-heavy workloads. Use bytes_per_element = 2 for FP16/BF16,
1 for INT8/FP8.

**Arithmetic intensity (AI):**
```
AI = FLOPs / bytes_transferred
```

**Roofline bound:**
```
perf_roof = min(peak_FLOP_s, AI × peak_bandwidth)
ridge_point = peak_FLOP_s / peak_bandwidth   # FLOP/byte
```
If `AI < ridge_point` → memory-bound; if `AI > ridge_point` → compute-bound.

**Adding a new hardware entry (NPU or B300):**
LLM-Viewer's `hardware_params.py` uses a flat dict keyed by device name. Each
entry requires:
```python
{
    "name": str,                # display name
    "peak_flops": float,        # theoretical peak FLOP/s (FP16 or target dtype)
    "memory_bandwidth": float,  # peak DRAM bandwidth (bytes/s)
    "memory_capacity": float,   # total DRAM (bytes); optional
}
```
All values must be FP16 (or the dtype you measure at). Use vendor datasheet
peaks. For empirically-measured roofs, see L2 below.
Source: `hahnyuan/LLM-Viewer` @ 1893e4b5, `hardwares/hardware_params.py`.

**DiT vs decoder LLM differences:**
- DiT models process full-frame tokens in every denoising step, not a growing
  KV cache. Sequence length is fixed (number of spatial tokens per frame).
- Each denoising step is a full forward pass; the performance measure is
  steps/second × frames/step, or directly frames/second.
- The VAE decoder adds a significant one-time cost per output; it must be
  included in the E2E breakdown (see L3).
- For an audio model such as fishaudio/drama-3, add vocoder/codec decode cost.
Source: `hahnyuan/LLM-Viewer` @ 1893e4b5, `configs/DiT.py`, `model_params/DiT.py`.

**Known L1 limitations:**
- L1 uses vendor datasheet peaks as conditional bounds for a stated algorithm,
  dtype, memory hierarchy and work/traffic count. No universal achievable
  percentage follows; calibrate a workload-specific attainable envelope in L2.
- L1 treats the full model as one roof; it cannot distinguish kernel-level
  variation, mixed operation-class throughput or scheduling overhead. Changing
  the algorithm can change both work and traffic, so proximity to the old roof
  does not rule out improvement.

### L2 — Empirical component ceiling

Requires hardware access. All values in this section are REMOTE MEASUREMENTS
to be taken; none can be filled in on a machine with no accelerator.

**What to measure:**

| Metric | Method | Required |
|--------|--------|---------|
| Empirical peak FLOP/s | ERT-style kernel sweep (see below) | REMOTE |
| Empirical peak memory bandwidth | ERT-style bandwidth kernel sweep | REMOTE |
| Kernel SOL% (Speed of Light) | nsys + ncu (CUDA) or vendor profiler (NPU) | REMOTE |
| SM/CU occupancy | ncu `sm__warps_active` or vendor equivalent | REMOTE |
| L1/L2/DRAM bandwidth per kernel | ncu hierarchical roofline section | REMOTE |
| Host-GPU/CPU-NPU transfer time | profiler timeline | REMOTE |

**Empirical peak measurement procedure (ERT method):**
The Empirical Roofline Toolkit (ERT) measures peak FLOP/s by running a FMA
loop kernel with variable trial counts; the alpha-update `alpha *= (1 - 1e-8)`
prevents compiler elimination. Peak is the maximum observed across a sweep of
working-set sizes and GFlops configurations. The config file (`Config/`) must
supply: compiler, GPU/NPU API, working set range, number of ERT trials, output
directory. For NPU, the `driver1.c` CUDA kernel must be ported to the vendor
compute API (CANN, Triton-Ascend, etc.); this is an open design decision.
Source: `ebugger/Empirical-Roofline-Toolkit` @ 0771fa9621d0,
`Empirical_Roofline_Tool-1.1.0/Drivers/driver1.c`,
`Empirical_Roofline_Tool-1.1.0/Scripts/roofline.py`.

**Bottleneck classification from profiler counters (CUDA / Nsight Compute):**

| Counter / metric | Bottleneck |
|-----------------|-----------|
| Memory SOL% high, Compute SOL% low | memory-bound |
| Compute SOL% high, Memory SOL% low | compute-bound |
| Both SOL% low, many small kernels, high CPU time | launch-overhead |
| Both SOL% low, significant collective operation time | communication-bound |
| Both SOL% low, excessive CPU-GPU sync events | sync-bound |

SOL% (Speed of Light %) = actual throughput / hardware peak throughput × 100.
Source: `NVIDIA/TensorRT-LLM` @ f33e0e5f,
`.claude/skills/perf-analysis/SKILL.md`,
`.claude/skills/perf-nsight-compute-analysis/references/roofline-analysis.md`.

### L3 — End-to-end ceiling

Requires at minimum wall-clock tracing of each stage.

**Stage breakdown for a diffusion serving system:**

| Stage | What to measure | Can be estimated? |
|-------|----------------|-------------------|
| Request scheduling | Time from request arrival to first GPU submission | CPU timer |
| Prefill (prompt encode) | Conditional encode time | profiler |
| Denoising steps | Per-step time × num_steps | profiler |
| Attention per step | QKV projection + attention kernel time | profiler |
| MLP per step | Linear projection time | profiler |
| AdaLN/conditioning | Conditioning injection time | profiler |
| VAE decode | VAE decoder latency | profiler |
| Audio/vocoder | Vocoder/codec decode time | profiler |
| Communication (multi-device) | NCCL/HCCL allreduce time | profiler |
| Serialization/transfer | Token/frame encode, network send time | profiler |
| Idle gaps | GPU idle between requests | profiler |

**Amdahl-style speedup formula:**

Given per-stage fractions of total time f_i (Σ f_i = 1), and a speedup s_i
achievable on each stage:
```
S_total = 1 / Σ_i (f_i / s_i)
```

Headroom attributed to stage i:
```
H_i = f_i × (1 - 1/s_i)   # fraction of total time recovered if s_i is achieved
```

Example (INSUFFICIENT_EVIDENCE — all values are placeholders):
If denoising steps = 70% of time with achievable speedup 1.4×, VAE = 15% with
1.2×, scheduling = 10% at 1.0×, other = 5% at 1.0×:
```
S = 1 / (0.70/1.4 + 0.15/1.2 + 0.10/1.0 + 0.05/1.0) = 1.26×
```
Without real profiling, this formula cannot produce a trustworthy number.

## Escalation rule: L1 → L2 → L3

Escalate from L1 to L2 when:
- The L1 roof predicts headroom but you cannot determine whether the system is
  memory-bound or compute-bound analytically (AI is near the ridge point).
- You need to confirm that a specific kernel is the bottleneck before
  committing to an optimization.

Escalate from L2 to L3 when:
- Kernel-level L2 measurements show individual kernels near their ceilings
  but E2E throughput is still lower than expected (scheduler, communication,
  or serialization losses).
- A single stage (e.g. VAE decode) dominates the Amdahl estimate and you need
  its real fraction.

Do not escalate unless the question requires it. L1 alone is often enough to
decide whether a 2× claim is plausible.

## How to express uncertainty

Never report a single speedup number without stating:
- Which ceiling level the estimate comes from (L1/L2/L3).
- The evidence basis: source-grounded analysis, author-reported, CPU test,
  device measurement, or end-to-end measurement.
- The assumptions (hardware peaks, stage fractions, whether profiler numbers
  came from the actual deployment configuration).
- A range: if stage fractions are ±20%, compute the best-case and worst-case
  Amdahl speedup explicitly.

Mark any empirical field as `INSUFFICIENT_EVIDENCE` when no accelerator
measurement exists. Do not interpolate from a different hardware SKU.

## Measurement plan: drama-3 / B300 case

This is a plan only. No empirical values exist on the local machine.
All "REMOTE" fields require execution on the target B300 system.

```yaml
baseline:
  model: fishaudio/drama-3  # diffusion audio/speech model
  engines:
    - vLLM-Omni (revision: TBD, freeze before measurement)
    - SGLang-Omni (revision: TBD, freeze before measurement)
  hardware: single NVIDIA B300
  concurrency_levels: [1, 2, 4, 8, 16]  # to be determined from capacity

workload:
  metrics:
    - throughput_frames_per_s
    - ttfa_p50_ms
    - ttfa_p95_ms
    - rtf_mean
  repetitions: ≥3 per concurrency level
  warmup: required; exclude from statistics

analytical_roof:
  status: INSUFFICIENT_EVIDENCE
  blocker: B300 peak FP16 FLOP/s and memory bandwidth not on this machine
  action: resolve from NVIDIA B300 datasheet or measure empirically via ERT

empirical_roof:
  status: INSUFFICIENT_EVIDENCE
  action: >
    REMOTE: run ERT-style FMA kernel sweep on B300; record empirical peak
    FLOP/s and peak memory bandwidth; compare to datasheet; record achievable
    fraction for this workload, without assuming a universal percentage.

stage_breakdown:
  status: INSUFFICIENT_EVIDENCE
  action: >
    REMOTE: run nsys to capture full timeline; extract per-stage wall-clock
    fractions for denoising, VAE, conditioning, communication, scheduling,
    idle. Report as f_i values for Amdahl formula.

bottlenecks:
  status: INSUFFICIENT_EVIDENCE
  action: >
    REMOTE: run ncu on the denoising kernel and VAE kernel; record SOL%,
    arithmetic intensity, bottleneck classification, occupancy.

headroom:
  speedup_range: INSUFFICIENT_EVIDENCE
  action: compute Amdahl S_total from measured f_i and achievable s_i

target_feasibility:
  verdict: INSUFFICIENT_EVIDENCE
  note: >
    A 2× E2E speedup requires either the dominant stage (likely denoising)
    to achieve >2× improvement (which implies near-doubling compute or
    memory efficiency), or several stages together to contribute. This is
    analytically possible but cannot be confirmed without stage fractions.

recommended_experiments:
  - hypothesis: Denoising step is memory-bound; fusing AdaLN conditioning
      reduces memory traffic.
    evidence: INSUFFICIENT_EVIDENCE (measure AI and SOL% first)
    expected_gain: unknown
    measurement: REMOTE — ncu AI vs ridge point on denoising kernel
    priority: 1

  - hypothesis: VAE decode fraction is significant; offloading or tiling
      reduces peak latency.
    evidence: INSUFFICIENT_EVIDENCE (measure VAE fraction of E2E first)
    expected_gain: unknown
    measurement: REMOTE — nsys stage fraction for VAE decode
    priority: 2

  - hypothesis: Multi-engine scheduling introduces idle gaps at concurrency>1.
    evidence: INSUFFICIENT_EVIDENCE
    measurement: REMOTE — nsys idle gap analysis at concurrency 4 and 8
    priority: 3
```

## How to decide whether further optimization is worthwhile

1. Compare the conditional Amdahl headroom with the actual target and measured
   uncertainty. Use nonoverlapping exposed-time fractions; a sum of overlapping
   kernel durations is not an end-to-end decomposition.
2. Check the dominant stage against operation-specific attainable envelopes.
   High utilization can constrain local tuning of the current algorithm while
   fusion, materialization removal, work ownership or a different algorithm
   changes its work and traffic. No universal SOL% cutoff establishes saturation.
3. Treat low utilization as a question: distinguish work supply, scalar versus
   matrix work, dependency stalls, launch overhead and memory movement before
   selecting a change. Occupancy, throughput and utilization are different metrics.
4. Keep four evidence types separate: physical/conditional bound, observed
   attainable envelope, empirical simulator prediction, and measured application
   outcome. A predictor needs a matching calibration domain and held-out load
   coverage, especially near capacity; prediction error does not establish a bound.
5. Redirect when the expected removable time cannot exceed locally measured
   noise, or when a change exposes a new owner. Preserve a valid incumbent and
   verify the final artifact under the application objective and all SLOs.

### Reviewed paper resources

The [modeling comparison](references/papers-20261015/MECHANISMS.md),
[exact readset](references/papers-20261015/READSET.md),
[bounds and predictions](references/papers-20261015/knowledge/bounds-predictions-and-decisions.md),
[cross-layer procedure](references/papers-20261015/redirect-cross-layer-optimization/procedure.md)
and [decision cases](references/papers-20261015/cases/decision-cases.md) retain
paper-specific costs, counter-signals and unresolved metric discrepancies.
Use [simulator calibration](../calibrate-serving-simulation/SKILL.md) for a
prediction-based shortlist and [attention diagnosis](../../hardware/cuda/diagnose-attention-bottlenecks/SKILL.md)
for algorithm/operation-class changes. These remain candidate guidance, not local
performance measurements. The bundled helper only computes explicitly supplied
L1 inputs under the contract above.
