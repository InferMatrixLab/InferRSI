# Optimization results

[Back to InferRSI](../README.md#selected-results) · [vLLM-Omni model optimization roadmap](https://github.com/InferMatrixLab/InferRSI/issues/416)

The README highlights measured improvements of at least 20%. This page keeps the
full curated record, including the campaigns below that bar. Hardware, workloads
and baseline revisions differ across comparisons. Quality and acceptance status
are reported for each result.

## Text serving

### DeepSeek V4.1 Flash W4A8 on Ascend A3

The project ran DeepSeek V4.1 Flash 1017 W4A8 on an Ascend A3 SuperPod with
disaggregated prefill and decode (1P1D, 8 physical cards per side). AISBench
generated load and InferRSI rechecked throughput at each scenario's latency
limit. [Project report, configuration and reproduction](https://github.com/jiaran-king/dsv4.1-optimize).

| Scenario | Per-card throughput metric | Latency limit | Baseline → optimized (tokens/s) | Measured change |
| --- | --- | --- | --- | --- |
| 19 · Prefill | Input throughput | Mean TTFT < 10 s | 68,239 → 105,397 | **+54.45%** |
| 21 · Decode, C1152 | Steady-state output | Mean TPOT < 50 ms | 1,711.98 → 2,330.28 | **+36.12%** |
| 23 · End-to-end, steady state | Decode output | Mean TPOT < 21 ms | 1,132.9 → 1,368.5 | **+20.80%** |

Cases 19 and 23 use medians from two runs. Case 21 uses one recheck of the
retained configuration, which includes a SiLU safeguard. TTFT is time to first
token. TPOT is time per output token.

### Historical DeepSeek V4.1 Flash W8A8 pilot

The A3 / 910C pilot used 16 dies, TP4 / DP4 / EP16, DSpark-5 and an
8K-input / 1K-output workload. The slide deck reported the following single-run
observations against the earlier control in [issue #329](https://github.com/InferMatrixLab/InferRSI/issues/329).

| Concurrency | Earlier control → reported pilot TPOT (ms/token) | Measured change |
| --- | --- | --- |
| 1 | 93.86 → 30.02 | **−68.0%** |
| 4 | 97.36 → 24.98 | **−74.3%** |
| 16 | 102.33 → 36.55 | **−64.3%** |

Only C4 reached 25 ms/token in the reported run. The follow-up benchmark uses
its own calibrated baseline. The campaign stopped with an **INCONCLUSIVE**
verdict. [Follow-up #353](https://github.com/InferMatrixLab/InferRSI/issues/353).

## Image, video and speech in vLLM-Omni

InferRSI campaigns and upstream experiments cover image, video and speech models.
Each result applies to its linked workload and measured revisions. Some results
are reported directly by upstream contributors, with validation scoped to their benchmarks.

| Model | Hardware | Optimization approach | Measured gains | Validation and limits | Evidence | vLLM-Omni PR |
| --- | --- | --- | --- | --- | --- | --- |
| **Qwen-Image-2.1-Turbo** | 4× B300 | <ul><li>Text-conditioning reuse</li><li>BF16 operator fusion</li><li>Symmetric-memory Ulysses with batched QKV exchange</li></ul> | **384.16 → 266.60 ms (−30.60%)**<br>Warm HTTP end-to-end latency, repeated prompts | Historical InferRSI campaign. Latencies are medians of five trial means from alternating AB/BA groups. All 44 RGBA images were pixel-identical. | [Campaign #3](https://github.com/InferMatrixLab/InferRSI/issues/3) · [Pinned results](qwen-image-2.1-turbo-b300.md) | [#8739](https://github.com/vllm-project/vllm-omni/pull/8739) (merged) |
| **Qwen-Image-2.1-Turbo** | 1× Ascend 910B1 | <ul><li>Conditioning cache for repeated prompts</li><li>Shared modulation once per denoising step</li><li>Native interleaved NPU RoPE with frequency-table reuse</li></ul> | **2,921.23 → 2,272.83 ms (−22.20%)** offline generation latency<br>Warm repeated prompts | Upstream parent-to-merge reference. InferRSI imported the techniques as knowledge. 18/18 RGBA images were pixel-identical. The 30% target was unmet. Both arms aborted during teardown, leaving lifecycle `INCONCLUSIVE`. | [Final-merge measurements](https://github.com/vllm-project/vllm-omni/pull/8729#:~:text=Final%2Dmerge%20performance%20and%20image%20comparison) · [Earlier Ascend cohorts](qwen-image-2.1-turbo-ascend.md) | [#8729](https://github.com/vllm-project/vllm-omni/pull/8729) (merged) |
| **MiniMax-H3 Ref2VA** | 8× Ascend 910B1 | <ul><li>Lossy Cache-DiT profile tuning</li></ul> | **407.27 → 108.12 s (−73.45%)**<br>5 s video, HTTP end-to-end vs. dense inference | All 14 frozen quality comparisons passed. | [Campaign #293](https://github.com/InferMatrixLab/InferRSI/issues/293) · [Pinned results](../evidence/h3-ref2va-ascend-293/results/final-5s/README.md) | [#9698](https://github.com/vllm-project/vllm-omni/pull/9698) (draft) |
| **MiniMax-H3 Ref2VA** | 4× Ascend 950PR (~86 GB per card) | <ul><li>USP4 + MXFP8</li><li>RainFusion + Cache-DiT</li></ul> | **701.95 → 166.17 s (−76.3%, 4.22×)**<br>5 s clip denoising time vs. the in-run dense control | Five retained historical A/B slots. Performance and quality qualification remained inconclusive. For quality, the recipe reports sharpness, flicker, and luma ratios of 0.924 / 0.950 / 0.984 against a dense USP4 + MXFP8 reference. | [Archive record #520](https://github.com/InferMatrixLab/InferRSI/issues/520) · [Measured repeats](https://github.com/vllm-project/vllm-omni/pull/9955#:~:text=in%2Drun%20dense%20median) | [#9955](https://github.com/vllm-project/vllm-omni/pull/9955) (merged recipe) |
| **MiniMax-H3-Image** | 4× Ascend 910B1 | <ul><li>Opt-in VAE tile graphs</li><li>Approximate encoder/decoder tile batching</li></ul> | **16.89 → 10.82 s (−35.9%)** · 4736×3552 generation<br>**4.18 → 2.67 s (−36.1%)** · 1024×1024 generation | Single-launch HTTP medians vs. the same-layout SP4 control. All 30 numerical image screens passed across generation and editing. Latency targets were unmet and final qualification remains `INCONCLUSIVE`. | [Campaign #390](https://github.com/InferMatrixLab/InferRSI/issues/390) · [Evidence PR #394](https://github.com/InferMatrixLab/InferRSI/pull/394) | [#10184](https://github.com/vllm-project/vllm-omni/pull/10184) (merged) |
| **MiniMax-H3-Image** | 2× RTX 3090 | <ul><li>Rank-local layerwise offload</li><li>Selected DiT weights kept resident</li><li>AdaLN caching</li><li>Request-local text refinement reuse</li></ul> | **36.62 → 14.59 s (−60.16%)**<br>Warm mean HTTP delivery latency | One upstream A/B of complete deployment profiles. All nine image pairs had identical decoded RGB pixels, including warmups. Repeated qualification remains incomplete. | [Paired deployment benchmark](https://github.com/vllm-project/vllm-omni/pull/10243#:~:text=One%20paired%20deployment%20comparison) | [#10243](https://github.com/vllm-project/vllm-omni/pull/10243) (open) |
| **MiniCPM-o 4.5** | 1× L20X | Seed-TTS runtime and deployment changes | **11.46 → 22.99 requests/s (+100.6%)** and **0.65548 → 0.32300 mean RTF (−50.72%)** at C32<br>**10.62 → 18.51 requests/s (+74.29%)** and **0.34287 → 0.19744 mean RTF (−42.42%)** at C16<br>**2.94 → 3.66 requests/s (+24.49%)** at C1 | Five retained fresh servers per arm, 12,800 successful requests. The independent-engine target was outside this comparison. Formal speech-quality non-inferiority remains unestablished. | [Campaign #431](https://github.com/InferMatrixLab/InferRSI/issues/431) | [#10331](https://github.com/vllm-project/vllm-omni/pull/10331) (merged) |
| **MiniCPM-o 4.5** | 1× L20X | <ul><li>Packed conditioning on a tuned configuration</li><li>TensorRT speaker extraction + CUDA MPS (separate comparison)</li></ul> | **−27.69%** median TTFA<br>Packed conditioning, C32, same 50-frame window<br>**+20.5%** at C16 · **+25.4%** at C32<br>TensorRT + MPS throughput | The packed-conditioning candidate missed the exploratory WER margin against the tuning reference at the 50-frame setting. The separate TensorRT + MPS comparison had speech-quality verdict `FAIL`. | [Campaign #49](https://github.com/InferMatrixLab/InferRSI/issues/49) | [#9218](https://github.com/vllm-project/vllm-omni/pull/9218), [#9188](https://github.com/vllm-project/vllm-omni/pull/9188) (both merged) |
| **LFM3-Omni-2B** | 1× Ascend 910B1 | <ul><li>Depth graphs</li><li>Grouped greedy sampling</li></ul> | **0.285 → 0.593 requests/s (+108.1%)**<br>Upstream offline Omni API A/B, C4, temperature 0 | Retained audio waveforms matched bit-for-bit within each tested temperature. | [Offline A/B benchmark](https://github.com/vllm-project/vllm-omni/pull/9827#:~:text=Performance%20results) | [#9827](https://github.com/vllm-project/vllm-omni/pull/9827) (merged) |
| **Drama 3** | 2× Ascend 910B1 | Full graph replay for steady-state decode | **17.31 → 22.40 / 22.91 frames/s (+31%)** and **1.237 → 0.962 / 0.947 mean RTF (−23%)** at C1 | Rounded changes use the mean of the two candidate runs. The real-time factor targets were unmet. | [Campaign #132](https://github.com/InferMatrixLab/InferRSI/issues/132) | [#9308](https://github.com/vllm-project/vllm-omni/pull/9308) (merged) |
| **Qwen3-TTS 1.7B** | 1× Ascend 910B1 | Codec and predictor optimizations | **1.869 → 4.822 audio s/s (+158%)** at C1<br>**16.463 → 38.755 (+135%)** at C16<br>**21.245 → 52.091 (+145%)** at C32 | Historical seven-path profile vs. fresh same-card no-PR control. Mandarin speaker similarity and some ASR results regressed. Upstream reference. | [vLLM-Omni roadmap #416](https://github.com/InferMatrixLab/InferRSI/issues/416) | [#9068](https://github.com/vllm-project/vllm-omni/pull/9068) (merged) |

**Earlier Qwen-Image-2.1-Turbo Ascend measurements.** On one Ascend 910B1 at
1280×704, BF16, eager, and eight native steps, the author reported a 3111.5 ms
baseline. Conditioning reuse with interleaved RoPE reached **2459.6 ms (−21.0%)**
with pixel-identical RGBA. Adding the opt-in VAE fastpath reached **2425.5 ms
(−22.0%)** and passed the reported quality gate with changed pixels. Each mean
covers three requests after two warmups. InferRSI verification covered the
import, so acceptance remains `INCONCLUSIVE`. The 30% target was unmet. The B300
campaign and this cohort used different hardware and measurement protocols.
[Earlier Ascend report](qwen-image-2.1-turbo-ascend.md)

### Historical campaigns below the 20% highlight bar

These campaigns stay on the record even though their measured gain is under the
bar the README highlights. Their upstream PR labels are kept as they were.

| Model | Hardware | Measured change | Validation and limits | Evidence | vLLM-Omni PR |
| --- | --- | --- | --- | --- | --- |
| **MiniMax-H3 Ref2VA** | 4 logical Ascend 910C devices | **291.25 → 286.67 s (−1.57%)**<br>5 s video, HTTP end-to-end | One lossless screening pair; strict quality checks passed for the screened candidate. Campaign `INCONCLUSIVE`. | [Campaign #297](https://github.com/InferMatrixLab/InferRSI/issues/297) · [Evidence PR #317](https://github.com/InferMatrixLab/InferRSI/pull/317) | [#9745](https://github.com/vllm-project/vllm-omni/pull/9745) (draft) |
| **Qwen3-Omni** | 2× L20X | **+7.79%** throughput · **−6.06%** mean RTF<br>One C64 pilot | Median time to first audio regressed 7.12%. Campaign `INCONCLUSIVE`. | [Campaign #112](https://github.com/InferMatrixLab/InferRSI/issues/112) · [Pinned pilot](https://github.com/InferMatrixLab/InferRSI/tree/e1ae256fc075ea9ab64aec68da749cf4a8c22ac7/evidence/qwen3-omni-2gpu-20261023/results/pr9283-cudnn-performance) | [#9283](https://github.com/vllm-project/vllm-omni/pull/9283) (draft) |
| **LingBot-World** | 4× Ascend 910C1 | **108.29 → 103.89 s (−4.06%)**<br>Full-request latency, upstream AB/BA | Pre-codec tensors and decoded RGB frames matched exactly. | [KV gather benchmark](https://github.com/vllm-project/vllm-omni/pull/8112#:~:text=Performance%3A%20whole%2Dblock%20index_select%20KV%20gather%20on%20NPU) | [#8112](https://github.com/vllm-project/vllm-omni/pull/8112) (merged) |

### Historical MiniMax-H3 Ref2VA step-reduction measurements on 950PR

The author reported these 5-second workloads on four Ascend 950PR cards
relative to their corresponding 50-step dense controls. Each sampling
configuration used three seeds and eleven prompts. Both performance and quality
qualification remained **INCONCLUSIVE**. One seed in the 10-step dense
configuration lost 9.17% subject consistency. The 10-step Cache-DiT route
combines fewer denoising steps and lossy caching, so its speedup describes the
whole workload change. [Record #520](https://github.com/InferMatrixLab/InferRSI/issues/520) ·
[Evidence index #527](https://github.com/InferMatrixLab/InferRSI/pull/527).

| Configuration | Speedup | Relative time reduction |
| --- | --- | --- |
| 10-step dense | 5.04× | **−80.2%** |
| 10-step + Cache-DiT 0.12 | 7.37× | **−86.4%** |
| 11-step dense | 4.74× | **−78.9%** |
| 12-step dense | 4.34× | **−77.0%** |

TTFA is time to first audio. RTF is real-time factor. WER is word error rate. The
LFM3-Omni-2B change is computed from the rounded means above; upstream quotes
+108.4% from its unrounded values.

Upstream PR statuses checked on 2026-11-20. To refresh a row, substitute its PR
number in `gh pr view 10184 --repo vllm-project/vllm-omni --json state,isDraft`.

## Standalone engine benchmarks

### Standalone video/audio engines

[h3-metal](https://github.com/zuiho-kai/h3-metal) provides Metal-native FastH3 and MiniMax-H3 text-to-video/audio inference on Apple GPUs.

Author-reported results on **Apple M5 Max (40-core GPU), 128 GB, macOS 27**, at **768×448, 49 frames, seed 0**, using real weights with one engine running at a time.

| Engine | Device | Steps | Cold | Warm | vs. MLX (cold / warm) | vs. h3.c (cold / warm) |
| --- | --- | --- | --- | --- | --- | --- |
| `PipeNetwork/minimax-h3-mlx` (4-bit) | Apple M5 Max (40-core GPU) | 20 | 153.1 s | 134.6 s | 1.00× / 1.00× | 0.44× / 0.54× |
| `antirez/h3.c`, default preset | Apple M5 Max (40-core GPU) | 20 | 67.6 s | 73.3 s | 2.26× / 1.84× | 1.00× / 1.00× |
| **h3-metal**, original H3 | Apple M5 Max (40-core GPU) | 20 | **54.29 s** | **29.89 s** | **2.82× / 4.50×** | **— / 2.45×** |
| **h3-metal**, FastH3 4-step + block-sparse attention | Apple M5 Max (40-core GPU) | 4 ¹ | **48.23 s** | **18.20 s** | **3.17× / 7.40×** | **1.40× / 4.03×** |

Cold includes the first clip's weight loading, text encoding and preparation; warm reuses loaded weights and prepared state. h3-metal's cold time is 19.7% below h3.c's, just under the 20% bar this page highlights.

¹ FastH3 uses a distilled 4-step checkpoint, unlike the 20-step configurations. Warm values average clips 2–4 for the 20-step rows and two A/B/B/A warm runs for FastH3.

[Author's report and reproduction →](https://github.com/zuiho-kai/h3-metal/blob/53b7fa5d88e2497ab427ab9c7155535f7e6e6817/README.md#performance). These external results were not rerun in InferRSI.

### Standalone speech engines

Concurrency 1 (C1) results reported by each project. Values are **engine / vLLM-Omni / SGLang-Omni**; compare within a row, since workloads and audio-frame definitions differ.

| Project | Device | Throughput (frames/s) ↑ | TTFA p50 (ms) ↓ | Report and status |
| --- | --- | --- | --- | --- |
| [Drama 3](https://github.com/InferMatrixLab/drama-3-single-b300-engine) | 1× B300 | **309.17** / 195.89 / 169.80 | **32.83** / 47.29 / 79.38 | [3-run medians](https://github.com/InferMatrixLab/drama-3-single-b300-engine/blob/58a1882a4d941f8d21bfce6be37d3d5e7c9fde80/docs/current-results.md); overall target unmet |
| [Qwen3-TTS](https://github.com/InferMatrixLab/qwen3-tts-rsi-npu-engine) | 1× Ascend 910B1 | **61.12** / 12.71 / 4.31 | **50.41** / 263.51 / 439.72 | [3-run means](https://github.com/InferMatrixLab/qwen3-tts-rsi-npu-engine/blob/a29f8193b557c415175d70919bdfb9bd3dcd51fc/evidence/campaign-20261017/same-card-performance.md); source campaign accepted |
| [MiniCPM-o 4.5](https://github.com/InferMatrixLab/minicpm-o-4.5-single-gpu-engine) | 1× L20X | **397.43** / 187.52 / 278.72 | **126.2** / 295.3 / 381.2 | [5-run means](https://github.com/InferMatrixLab/minicpm-o-4.5-single-gpu-engine/blob/a4f4778f312791c2d190b48e521141887ed160c8/docs/current-results.md); target unmet, quality unqualified |

MiniCPM's SGLang baseline returns a complete waveform, so its TTFA equals end-to-end latency. These external results were not rerun in InferRSI.
