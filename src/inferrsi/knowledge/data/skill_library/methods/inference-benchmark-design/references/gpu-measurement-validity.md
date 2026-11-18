# GPU measurement validity and attribution of gains

Status: source-derived candidate; empirical validation not_run; efficacy
not_evaluated. Public source observations are cited below. The attribution and
adoption procedure is an author proposal derived from those sources, unverified
as a complete method. The final section contains task-supplied author reports
with unavailable evidence, not locally reproduced cases or efficacy evidence.
Source versions, inspected sections and available document hashes are retained
in the owning `metadata.json`; the unversioned SMI page is hash-pinned there.

## Freeze the measurement and environment

1. Bind workload, quality oracle, baseline execution mode, warmup, timed boundary,
   repetition/aggregation rule, cache policy, streams and graph policy before
   comparison. Retain paired baseline/candidate samples, including failures;
   service claims still need the campaign's E2E evidence. This is proposed
   measurement guidance, not a new numeric gate; see the owning skill's contract.
2. Record SM/memory clocks, temperature, power draw/limit and throttle reasons
   alongside timestamped samples; record co-tenancy and allocation changes.
   Boost state and thermal/power limits can move GPU region times without a
   code change; competing work can alter scheduling and memory traffic.
   They need not affect every region equally. E2E time alone cannot attribute
   a gain to the patch. Sources: [NCG] §§ Clock Control, Reproducibility;
   [SMI] §§ Performance State, Clocks Event Reasons. Recording is author advice.
3. Record profiler version, replay mode and actual control settings. Nsight
   Compute 2025.3 defaults to `--clock-control base` and `--cache-control all`:
   it attempts base clocks and flushes GPU caches before kernel replay passes.
   Thermal throttling can still override clock control; platform support varies.
   Sources: [NCC] § Profiling; [NCG] §§ Clock Control, Cache Control.
4. Ordinary execution and Nsight Systems tracing do not automatically apply
   those NCU replay controls. This is an inference from [NCS] § CLI Profile
   options versus [NCC], not a guarantee about an external launcher. Record
   external clock locks and explicit cache flushes. Use NCU for isolated kernel
   diagnosis; its kernel durations are not E2E evidence. Retain separate normal
   paired E2E measurements and assess profiler overhead. [NCG] §§ Replay,
   Overhead; [NCS] § CUDA Graph Trace warns of node-tracing overhead.

## Attribute changes within each paired run

Author-proposed diagnostic, derived from [CBP] §§ Application Profiling,
Amdahl's Law and [NCG] § Clock Control; its reliability is unverified here.

1. Instrument stable regions and retain their times and E2E time from the same
   run. Use region shares, not a kernel time divided by a different run's total.
   Keep baseline/candidate interleaved in one allocation. Select an untouched
   reference region `U` with identical work, placement and dependency behavior.
2. Compare `region_time / U_time` within each run. `U` acts as an internal clock
   only if it shares the relevant clock sensitivity and is unaffected by the
   patch. Verify its counts and environment; use multiple controls if possible.
   A CPU-bound or differently memory-bound region is not a universal GPU clock.
   Common movement is a confounding signal, not proof that normalization works.
3. Predict the E2E change from measured changed-region speedups and baseline
   shares using an Amdahl decomposition. For disjoint serial regions, with no
   drift and an unchanged residual, define `f_i = B_i / T_B` and `s_i = B_i/C_i`:

   ```text
   predicted candidate/baseline time = 1 - sum(f_i) + sum(f_i / s_i)
   observed candidate/baseline time  = T_C / T_B
   ```

   If explicitly assuming common multiplicative drift `d = U_C/U_B`, use
   `s_i = (B_i/U_B)/(C_i/U_C)` and compare the prediction to `(T_C/T_B)/d`.
   That correction assumes the residual shares the drift too; model unaffected
   host time separately. Retain raw and normalized ratios and their uncertainty.
4. Check prediction against the observed paired E2E ratio under the frozen
   campaign uncertainty rule. A mismatch leaves attribution unresolved: inspect
   noise, overlap/critical-path effects and side effects in other regions.
   Do not sum overlapping kernel durations as wall time. Use the dependency
   timeline for concurrent work; a faster off-path kernel need not shorten E2E.
   Sources for these limits: [CPG] §§ Concurrent Kernel Execution, CUDA Graphs;
   the mismatch interpretation is an author inference, not a causal proof.

## Retain work counts as well as time

For identical work and comparable collection conditions, these author-selected
counts are less directly sensitive to clocks/temperature than durations or rates.
They explain small changes; they do not independently establish a speedup.

| Work signature | Collection and interpretation |
| --- | --- |
| Kernel set and launch count | [NCS] CUDA GPU Kernel Summary / launch trace: retain kernel identity and instances per region, not just aggregate time. |
| DRAM read/write bytes | `dram__bytes_read.sum`, `dram__bytes_write.sum`; [NCM] § nvprof Metric Comparison names these counters. Retain both directions under the same cache/replay policy. |
| Executed instructions / FLOPs | `smsp__inst_executed.sum` counts warp instructions, not FLOPs ([NCM]). Derive FLOPs only with documented operation, datatype, active-thread and tensor-instruction semantics; count FMA as two operations ([CBP] § Instruction Throughput). |
| Host↔device copy bytes | [NCS] CUDA GPU MemOps Summary (by Size): separate HtoD/DtoH bytes, instances and transfer types. |
| Synchronization count | [NCS] CUDA API trace: count named host synchronization calls per region. API calls do not enumerate every device barrier or dependency. |
| CUDA graph node count | [CPG] § CUDA Graphs: retain graph topology/node types and replay count; [NCS] node tracing exposes activities. A graph launch count is not its node count. |

The metric names above have an official legacy mapping in the CUDA 10.2 NCU
archive [NCM], not a promise of availability on every current GPU. Query the
installed NCU/device with `--query-metrics`; resolve suffixes with
`--query-metrics-mode suffix --metrics <names>` ([NCC] § Metric Collection).
Retain supported names, units, collection passes and per-region sums; mark absent
counters unavailable. Do not replace a count with percent-of-peak or per-second.

Author caveats: these are conditional invariants, not constants. Cache residency,
co-tenancy and replay can change DRAM traffic; data-dependent branches, spin
loops and algorithms can change instructions. [NCG] §§ Range and Precision,
Cache Control describes asynchronous traffic and multi-pass variability.
For FLOPs, keep the derivation with the raw counters; instruction count alone
does not distinguish useful arithmetic, address work or redundant computation.

## Require an explanation before adoption

Author-proposed candidate guidance, motivated by [CBP]'s Assess / Optimize
cycle and [RB] § 3 and Appendix A; no efficacy claim or repository-wide gate.

Before measurement, state a mechanism and predicted signature: region, metric,
direction and rough size. For example, removing a materialized intermediate
predicts fewer DRAM bytes in the affected region; fusion predicts fewer launches
and perhaps less intermediate traffic. These are hypotheses to verify, not
automatic consequences or numeric thresholds. Retain counters, timelines,
paired E2E samples, quality results and the Amdahl check together. Adopt only
when retained data supports the explanation and frozen campaign gates hold.
Leave unexplained numeric gains unadopted / INCONCLUSIVE for attribution;
reject a contradicted mechanism/candidate rather than narrating it as a win.
Distinguish this adoption decision from the campaign's PASS/FAIL/INCONCLUSIVE.

## Audit common timing traps

- **L2 flushing:** Triton v3.2.0 `do_bench` writes a cache buffer with
  `cache.zero_()` before each measured start event ([TR]). Its preliminary
  runtime estimate includes the flush, whereas per-sample events surround `fn`.
  Record the method, buffer size, stream/order and cold-versus-warm intent.
  Author advice: compare flush methods as a separate control; an excluded flush
  may still change the next kernel's cache/memory state. Do not infer that a
  read-based flush is equivalent or superior without device-specific evidence.
- **Events versus host timers:** CUDA launches are asynchronous. Use synchronized
  host boundaries for completed wall time; CUDA events timestamp stream progress
  and require completion before reading elapsed time ([CBP] § Timing).
  Capture/instantiation, host submission, graph replay and kernel execution have
  different costs ([CPG] § CUDA Graphs). Author advice: expose fixed launch/replay
  costs with matched repetition counts; amortize only what deployment amortizes.
  Events are not pure instruction time when their interval contains GPU idle gaps.
- **Baseline identity:** state eager versus `torch.compile`, compiler settings,
  warmup and graph mode. Speedup is `baseline_time/candidate_time`; changing the
  denominator changes the claim (arithmetic / author advice). [RB] Appendix C.3
  explicitly distinguishes eager and compiled comparisons; neither is universal.
- **JIT extension identity:** give separately loaded variants distinct extension
  names and retain the actual module/function and built-library identity. This
  is author advice inferred from [PT] `load`: the build directory uses `name`,
  which must match the pybind11 module. The docs do not establish that every
  repeated name fails; do not assume two same-named loads are independent.
- **Benchmark exploits:** [RB] § 3 and Appendix A report inefficient baselines,
  low-variation outputs and input-specific shortcuts passing exposed checks.
  Author advice: inspect actual timed work and use independent varied-input
  quality tests. A correctness flag or extreme ratio alone cannot clear a gain.

## Author-reported observations: unverified

Task-supplied reports only; raw samples, configurations and profiler artifacts
were not supplied. The numbers below are not public-source findings, reproduced
results, reusable thresholds or evidence that this procedure is effective.

| Reported scope | Reported observation | Limit |
| --- | --- | --- |
| One H200 campaign | Write-based L2 flush inflated timings about 9% versus read-based flushing. | Cause and flush equivalence unverified. |
| Shared nodes | Same-run interleaved ratios were reported trustworthy while cross-run baselines drifted ±7–15%. | Reliability, uncertainty and common-drift assumptions unverified. |
| Same code, different weight placement | Timing differed about 4%. | Placement and causal mechanism unverified. |
| Same candidate, different baseline | 7.35x versus eager, 1.43x versus `torch.compile`. | Baseline configurations, quality and timings unverified. |

Original synthesis; no upstream code, figures or raw reports redistributed.
NVIDIA/PyTorch document rights remain with their owners; Triton is MIT-licensed;
Lange et al.'s [RB] is CC BY 4.0. Source review is not GPU execution, model quality,
L1–L4 qualification, independent review or proof of agent efficacy.

[NCG]: https://docs.nvidia.com/nsight-compute/2025.3/ProfilingGuide/index.html
[NCC]: https://docs.nvidia.com/nsight-compute/2025.3/NsightComputeCli/index.html
[NCS]: https://docs.nvidia.com/nsight-systems/2025.3/UserGuide/index.html
[SMI]: https://docs.nvidia.com/deploy/nvidia-smi/index.html
[CBP]: https://docs.nvidia.com/cuda/archive/12.9.1/cuda-c-best-practices-guide/index.html
[CPG]: https://docs.nvidia.com/cuda/archive/12.9.1/cuda-c-programming-guide/index.html
[NCM]: https://docs.nvidia.com/cuda/archive/10.2/nsight-compute/docs/NsightComputeCli/index.html
[TR]: https://github.com/triton-lang/triton/blob/9641643da6c52000c807b5eeed05edaec4402a67/python/triton/testing.py
[PT]: https://docs.pytorch.org/docs/2.7/cpp_extension.html
[RB]: https://arxiv.org/html/2509.14279v1
