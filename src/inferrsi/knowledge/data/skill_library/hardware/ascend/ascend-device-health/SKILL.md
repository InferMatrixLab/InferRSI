---
name: ascend-device-health
description: 'Pre-run health checks and recovery procedures for Ascend NPU devices on shared machines: card-group topology validation, Health status checks, SIGKILL residual-state detection, 4-step smoke verification, process occupancy check, and DVFS warmup discipline. Use before any experiment that requires a trusted performance baseline.

  '
---

# Ascend Device Health and Pre-Run Verification

Status: candidate. Source-grounded from MindIE-SD `dit-parallel-opt` skill
and `perf-gate` skill @ 8481d39b. Unverified locally (no NPU). The empirical
thresholds (SIGKILL detection criteria, drift magnitude) are from a single
environment — re-test on each hardware/software combination.

## SearchSpace mapping

This skill addresses the **OS / System** resource row:
- Diagnose: SIGKILL residual state, shared-machine contamination
- Configure: card-group selection, env variable setup
- Verify: card-health sequence before experiments

## When to use this skill

Before any of the following:
- A performance measurement that will be compared to a historical baseline
- Any multi-card distributed run
- Any graph-mode capture run (slow startup; must not be confused with stuck state)
- After a previous run was killed (SIGKILL, OOM, or timeout) on the same card group

## Step 1: Card topology check

**Command:**
```bash
npu-smi info -t topo
```

Read the output and identify which cards share UB/HCCS interconnect (same island/domain) vs which are connected only via SYS/PCIe (cross-domain).

**Legal card groups:**
- 2 cards: one pair of same-domain adjacent cards (UB/HCCS)
- 4 cards: one complete same-domain group
- 8 cards: all cards

Cross-domain groupings (mixing UB and PCIe cards) are not legal for performance experiments. If forced by occupancy constraints, label the result explicitly as "non-intra-domain" and note that bandwidth is sub-optimal.

**Do not hardcode card numbers.** Card identity can change after driver restart or hardware replacement. Always read the topology from `npu-smi info -t topo` at the start of each session.

Source: MindIE-SD `dit-parallel-opt` @ 8481d39b, §卡组拓扑规则.

## Step 2: Card health check

**Command:**
```bash
npu-smi info
```

For each card in your intended group:
- `Health = OK`: proceed to step 3.
- `Health = Alarm`: discard this card; choose an alternative group.
- `Health = Warning`: run a probe (see step 3) to confirm the card is usable before including it.

**Important: `Health = OK` is necessary but not sufficient.** It does not detect SIGKILL residual state (see step 3). A card reporting OK may still produce anomalous per-step timing.

## Step 3: Process occupancy check

```bash
npu-smi info  # look for proc-mem column
```

Check whether any external process (another user's `rtp_llm`, `vllm`, or other framework) is consuming memory on your intended cards. A card occupied by another tenant may produce unexpected slowdowns or card errors.

If a card shows memory usage from a foreign process, either request the card be freed or select a different group.

## Step 4: 4-step smoke verification (detect SIGKILL residual state)

After selecting a card group that passes steps 1–3, run a minimal 4-step warmup and check per-step timing:

```bash
# Run your model/workload for 4 steps only; record per-step elapsed time
```

**What to look for:**
- If per-step timing is uniform and within expected range: card group is clean.
- If per-step timing is uniformly elevated by approximately one order of magnitude compared to normal: this is the SIGKILL residual state pattern. The driver is in a degraded state from a previous killed job.

**Recovery from SIGKILL residual state:**
1. Try a full driver reset or restart the NPU service.
2. If that is not available: switch to a different card group and repeat the smoke test.
3. Record the event: which cards, which time, what the timing looked like.

`npu-smi Health=OK` does **not** detect this state. The smoke test is the only reliable check.

Source: MindIE-SD `dit-parallel-opt` @ 8481d39b, §执行要点 point 3.

## Step 5: DVFS warmup for operator benchmarks

For any operator-level benchmark (not serving throughput — see `ascend-operator-profiling`), run warmup iterations before collecting measurements.

```bash
msprof op --warm-up=10 --output=./msprof_output ./demo
```

DVFS (Dynamic Voltage and Frequency Scaling) causes the first few runs to operate at a lower clock frequency. Without warmup, the first run is slower than steady-state, contaminating the benchmark. `--warm-up=10` is a conservative default; reduce if the operator is expensive and startup cost matters.

Source: `ascend-operator-profiling` @ 75ec89ce.

## Card-group change discipline

Changing the card group is a contract change. It invalidates any previous baseline measurement taken on a different group. After a card-group change:
- Re-measure the baseline on the new group in the same session window.
- Do not compare new-group results to old-group baselines (cross-group absolute values are not comparable, for the same reason cross-window measurements are not comparable on a shared machine).

Source: MindIE-SD `dit-parallel-opt` @ 8481d39b, §执行要点 point 4.

## Environment variables checklist

Before a multi-card run, verify:

| Variable | Value | Purpose |
|----------|-------|---------|
| `HCCL_OP_EXPANSION_MODE` | `AIV` | Recommended with graph-mode capture; stabilizes collective communication dispatch |
| `HTTP_PROXY` / `HTTPS_PROXY` | your proxy | Required if the serving framework makes outbound requests |

Set only what you need. Do not set environment variables "just in case" — unintended variables can alter benchmark behavior.

## What this skill does NOT cover

- GPU (CUDA/NVIDIA) health checks: use `nvidia-smi` and the TRT-LLM `exec-env-check` pattern.
- Host-side CPU health: that is the RAM/Host row.
- CANN version compatibility: check against your model's requirements separately.
