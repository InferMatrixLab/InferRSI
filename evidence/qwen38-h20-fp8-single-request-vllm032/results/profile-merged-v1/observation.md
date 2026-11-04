# Merged FP8 graph decode: profiler observation

Parent-reviewed diagnostic under InferRSI Issue #67. **INCONCLUSIVE** for service performance and full model quality. This single instrumented profile has no matched baseline profile. It supports candidate selection only; it does not establish an HTTP gain, formal regression cause, TPOT, or quality acceptance.

Job 2169 completed with scheduler exit `0:0` in 91 seconds using one GPU and eight CPUs: **91 allocated GPU-seconds**. Completion records `complete=true` and `state_released=true`. All four postflight statuses are zero. Before/after model-runtime and overlay JSON are identical; all 21 component and 59 source checks are successful and agree with locally verified manifests. Private originals remain outside the knowledge record; `receipt-review.json` contains sanitized hashes and counts.

The observation covers one 8192-token prefill and eight pooled CUDA Graph decode steps after one prefill and two decode warmups, with graph capacity 10240. The backend uses merged native FP8 projections, FlashInfer small-M decode GEMMs, DeepGEMM prefill, FlashInfer GDN, and native full attention. GPU kernels are attributed inside synchronized profiler intervals. Source-region attribution is inferred from repeated graph-node ordering, not module NVTX annotations.

| Instrumented phase | Host interval | GPU kernel sum | Kernel count |
| --- | ---: | ---: | ---: |
| Prefill | 2918.167 ms | 2861.021 ms | 3470 |
| Eight decode steps | 103.192 ms | 97.940 ms | 17328 |

Decode averages 12.243 ms of summed device kernel duration per token. Each replay contains 2163 graph kernel nodes, averaging 12.232 ms; graph sums range from 12.223 to 12.240 ms. Twenty-four additional kernels cover sampling and input/position fills. Timestamp overlap gives a 97.775 ms interval union, slightly below the sum. These instrumented sums must not be compared directly with HTTP latency or interpreted as host launch counts.

FP8 projections consume 7.128 ms/token; their activation quantization adds 0.396 ms/token. Separate BF16 GDN b/a projections plus split-K reductions consume 0.598 ms/token (96 GEMMs and 96 reductions). The convolution-window/copy/convolution/SiLU region consumes 0.503 ms/token, while FlashInfer GDN recurrence itself consumes 0.238 ms/token. The `deep_gemm::fp8_gemm_kernel_swapAB` decode symbols originate from the intended FlashInfer small-M API; they do not demonstrate accidental large-M DeepGEMM dispatch. The 256 FP8 module and activation-quantization counts agree.

The next bounded model hypothesis is to merge each GDN layer's two BF16 `[48,5120]` b/a projections into one `[96,5120]` projection ordered `[b(48), a(48)]`. The pinned vLLM source already uses this structure. Preserve BF16 exclusions, original checkpoint mappings, 256 FP8 modules, scales, and immutable model bytes. Keep the decode bridge's contiguous conversions until its stride contract is verified. A new GEMM shape may change reductions and BF16 results; reduced kernel count or time remains a hypothesis. Required checks include loader structure, actual-weight operator comparison, fixed-history eager/graph continuation, reset/reuse, and the existing frozen quality protocol before a separately budgeted matched service comparison.

Defer causal-convolution update fusion to a separate step. Its state mutation and rounding risks exceed b/a projection fusion: preserve the request-owned window, chronological update, and current BF16 convolution-output round-trip before SiLU. The pinned vLLM implementation applies SiLU to an FP32 accumulator and is not a drop-in arithmetic equivalent. Combining these changes would obscure attribution.

Public source provenance is preserved in `source-provenance.json`, including immutable URLs and byte hashes. The primary references are vLLM's `qwen_gdn_linear_attn.py` (`create_ba_proj`, `split_ba`, and decode flow), `flashinfer.py` (small-M dispatch), and `causal_conv1d.py` (deferred update semantics). The diagnostic changes no engine or validator. Its findings and limitations are recorded as a store-owned candidate; this is not a promoted library entry.
