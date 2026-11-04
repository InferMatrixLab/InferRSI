# Merged FP8 plus FlashAttention: actual engineering result

Under InferRSI Issue #67, job 2175 completed with scheduler exit `0:0` in 278 seconds on one H20. This is **INCONCLUSIVE** for quality and parity acceptance. It is a single original 8K input / 2048-output comparison, ineligible for the formal 10-input × 3-pair reducer.

| HTTP measurement | Native prefill | SDPA Flash prefill |
| --- | ---: | ---: |
| TTFT | 2.864008470 s | 2.321464958 s |
| TPOT | 12.212332628 ms | 12.188997569 ms |
| Request latency | 27.862653359 s | 27.272342981 s |

Observed TTFT is 18.943502% lower in this one comparison. Each arm had a discarded 2048-token warmup and one measured request; all four original raw SSE responses pass the unchanged official-client accounting audit. The measured output token sequences **differ**, first at zero-based output position 5. Therefore no quality-preserving gain is established. Quality screening remains required before promotion; attention arithmetic differs despite unchanged weights and valid same-candidate Graph behavior.

Synthetic tests used production 24Q/4KV heads, dimension 256, and merged-V token stride 14336 at lengths 129 and 8192. Six changed-input eager/Graph replays were exact, causal prefixes were preserved, and two prefill-to-decode outputs plus full cache updates were exact. The short native-rounding observation was max_abs 0.015625, NRMSE 0.002592582 with no acceptance tolerance assigned. This synthetic probe used injected projections and is not checkpoint FP8 evidence. The separate actual-checkpoint probe passed all 16 same-candidate eager/Graph predictions, 15 replays and final live state at capacity 10240.

All 16 component and 60 source hashes, complete before/after model/runtime and overlay checks, postflight statuses and external terminal evidence were verified. Replayed audit exactly matches the original. Both owned service processes exited 0 without forced termination or remaining groups. No warning/error/traceback marker was found in archived run logs. Attention selection is evidenced by launch configuration plus frozen constructor source; no independent call counter was added, and no equivalence to vLLM FA3 is claimed.

Preparation negatives remain: initial operator import-order lint failure, three collector/auditor line-length findings, one retained control-script line-length finding, and unsupported initial wrapper CLI flags, all fixed before submission. A premature remote hash check ran before asynchronous source transfer completed and failed with a missing manifest; it submitted no job. After transfer completion all 16 hashes passed and the sole GPU job was submitted. The earlier unrelated job 2113 startup timeout remains retained in its original case. Nineteen persistent CPU controls distinguish 14 raw/synthetic-health audits and 5 actual-main mocks; none substitute for GPU validation.

Raw archive SHA256 `a64663a8b0867d41150dd53dcb34fa5f303c02bd0791aa2074d4866c1f274f4e`; raw-audit SHA256 `c672817356064e27f95b513b7e991572f7b407da1eae42d0c7d8880fc6107184`. Component freeze `e3795574ca2e44725af4440f3b30dbf4c32012146a24cac572ef2a14b2705721` was published prospectively in Issue #67. Source identity and previous preparation are retained. Search allocation spent through this run is 2613 / 28800 GPU-seconds; other phase caps are unchanged. No full quality, retrieval, formal parity, or merge readiness is asserted.
