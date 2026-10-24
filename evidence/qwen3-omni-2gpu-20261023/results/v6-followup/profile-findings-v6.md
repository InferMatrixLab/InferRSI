# C1/C64 full-pipeline profile findings (diagnostic only)

Status: INCONCLUSIVE for service performance. The fixed MRv2+adapter source and two-GPU placement completed 8 C1 and 128 C64 profiled requests. Actual peak concurrency was 1/64; source, resource ownership, cleanup and all 18 retained artifact hashes passed their checks. Profiler overhead prevents acceptance use. C1 had zero reported inference JIT events; C64 had four, so C64 is not a zero-JIT steady-state sample.

| Concurrency | Stage | Kernel duration sum (s) | Per-stage kernel interval union (s) | Own kernel envelope (s) |
|---|---|---:|---:|---:|
| 1 | Thinker | 0.6160 | 0.6109 | 3.0472 |
| 1 | Talker/Predictor | 2.2320 | 2.0796 | 3.1424 |
| 1 | Code2Wav | 0.2217 | 0.2216 | 3.1058 |
| 64 | Thinker | 1.5646 | 1.5593 | 5.0128 |
| 64 | Talker/Predictor | 2.9752 | 2.8265 | 6.9379 |
| 64 | Code2Wav | 2.2808 | 2.2802 | 6.9205 |

These are trace intervals, not service latency or hardware-utilization measurements. Stage1 and stage2 share one physical GPU according to the pinned placement and startup mapping; their intervals overlap substantially. With each trace's baseTimeNanoseconds applied, their joint kernel unions are 2.157590/3.359664 seconds inside common envelopes of 3.142439/6.947352 seconds. No independent cross-process clock calibration or exact request perf_counter-to-wall bridge was captured. Kernel intervals can include scheduling effects. Uncovered intervals are not a quantified removable bottleneck.

Native stop_profile stops stages sequentially. Earlier trace export delays later stages' stop. Kernel envelopes avoid pure trailing empty capture time but cannot by themselves exclude background activity.

The C1 Talker trace contains 636721 kernel events and 25200 predictor flash-attention calls. This supports investigating operation granularity and sequential predictor depth; it does not prove launch overhead is the exclusive bottleneck. The real-weight uncompiled component test already showed that eliminating FLOPs does not produce proportional latency reduction.

At C64, Code2Wav's implicit_convolve_sgemm kernel accounts for 0.724101 seconds of duration sum and nchwToNhwcKernel 0.171412 seconds. The analyzer's original name heuristic labels the former GEMM; interpret the full name as a convolution implementation. Many nvjet kernels remain unknown rather than being assigned to an operator without correlation. CUDA graph kernel events lack tensor shapes, so no specific Conv layer is attributed to this cost.

Next bounded candidates: isolated V1 predictor KV quality comparison (running separately); fresh-process codec cuDNN algorithm-selection comparison; placement-only comparison with equal Thinker memory budgets; speculative-depth design only after sampler semantics are validated. None is promoted by these traces. Prior full-CUDA codec-placement trials changed additional knobs and are not isolated placement evidence.

Sources: pinned engine 4645c450ba4ed036433a30dfcb9782f22b0c3bfd; native profiler/orchestrator and benchmark sources; profile-v6-summary.json; profile-cross-stage-union-v6.json; profile-window-source-audit-v6.md; codec-c64-hotspot-audit-v6-private.json. Raw traces stay private with retained hashes.
