# Hy4-Flash-FP8 serial decode on four L20X GPUs

**PASS on the independent L4 replay.** At 130,048 input tokens and 1,024 generated tokens per request, the median TPOT fell from **5.779997 to 3.763408 ms/token**, a **34.89% reduction**. Serial AIME2026 was **29/30** against a **29/30** baseline. The allocation exposed four NVIDIA L20X devices. The operator confirmed this allocation after hardware preflight. [Acceptance and execution record](https://github.com/InferMatrixLab/InferRSI/issues/687)

| Service | P50 TPOT (ms/token) | AIME2026 correct |
| --- | ---: | ---: |
| Reference | 5.779997 | 29/30 |
| Selected candidate | 3.762996 | 29/30 |
| Fresh final | 3.763408 | 29/30 |

## Measurements and decisions

| Round | Change relative to its experimental parent | P50 TPOT (ms/token) | Reduction from reference |
| ---: | --- | ---: | ---: |
| 1 | DFly 15 | 5.733445 | 0.81% |
| 2 | Instrumented DFly 5 control | 6.643502 | -14.94% |
| 3 | Eager CUDA providers with decode graphs | 5.203872 | 9.97% |
| 4 | Instrumented eager-provider control | 5.228817 | 9.54% |
| 5 | Fused IndexPool rotation, Hadamard transform and FP8 conversion | 4.631993 | 19.86% |
| 6 | Fused sliding-window index generation | 4.287506 | 25.82% |
| 7 | Fused FP32 projections and gated pooling for small groups | 3.762996 | 34.90% |

The installed DeepInfer verification-budget record motivated measuring accepted positions alongside step cost. A wider DFly block increased delivered tokens per event and verification time together. The launch interval and the accepted-position distribution explained its small net gain. Warmup traces at DFly 5 showed thousands of small native PyTorch operations per step. The model did not opt into Inductor compilation, although compilation-aware defaults selected native operator implementations. Switching to eager CUDA providers while retaining full decode graphs reduced device kernels from 10,569 to 7,132 per step. The trace covered three iterations on each rank and finished before formal performance sampling. [Trace and component measurements](results/diagnosis.json) · [DeepInfer verification budget source](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L118-L219)

The remaining changes fused the sparse index feature transform, wrote packed causal window indices directly, and reduced the cost of the two FP32 projections used by small pooling groups. The feature and window tests compare the resulting bytes and indices exactly. The small-pool implementation retains FP32 arithmetic with a different reduction order. Some BF16 control values and full generated sequences changed. The two complete AIME passes on the selected revision establish the measured quality result. Each timing row represents a separate service launch. The evaluator skipped AIME on intermediate trials below the performance gate. [All attempts](results/trials.jsonl)

An earlier same-revision observation returned 6.617167 ms/token and 29/30, followed by a delayed process-group teardown. Its verdict remains INCONCLUSIVE. The accepted reference reproduced all twenty greedy output streams with a faster event cadence. The threshold uses the faster accepted reference. The independent final started a separate service with the same selected source and execution adapter. [Run identities and unrounded metrics](results/summary.json)

The evaluated workload is twenty serial LongBench v2 text completions and thirty serial AIME2026 problems on the local allocation. Retained public rows allow recomputation of the medians and correct counts. Private raw records contain the token events, generated responses, traces and lifecycle receipts. [Request boundaries](results/requests.jsonl) · [AIME judgments](results/aime.jsonl) · [Validator and input reconstruction](validator/README.md) · [Deployment and source](patch/README.md)
