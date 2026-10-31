# MiniMax-H3 Ref2VA on Ascend

Governing acceptance: [InferRSI #293](https://github.com/InferMatrixLab/InferRSI/issues/293).
Status: **INCONCLUSIVE**. This campaign is in progress. No accepted speedup or
model-quality result exists yet.

`plan/` records the initial scope, `validator/` freezes the adopted quality gate,
`results/` retains attempted and rejected outcomes, and `patch/` identifies engine
changes when available. Private runtime paths and raw host logs stay outside the
published tree; public artifacts use labelled paths and hashes.

## Attribution and candidate selection

| Candidate family | Source at the frozen baseline | Experiment requirement |
| --- | --- | --- |
| Component residency / weight transfer | [NPU recipe](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/recipes/MiniMaxAI/minimax-h3-ref2va-8-rank-resident.yaml) | Measure transfer/encode/decode separately; resident layers require rank-local transfer, so compare that changed transfer strategy explicitly. |
| Exact AdaLN projection reuse | [shared cache](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/cache/exact_projection_cache.py) | Already enabled by default. Do not claim it as new work. Offload can invalidate storage signatures; count actual hits before relying on reuse. |
| Reference-KV reuse | [reference cache](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/models/minimax_h3/reference_kv_cache.py) | Approximate across timesteps even with BF16 cache storage. Validate reference refresh, SP layout, host transfer and audio/video quality. |
| Cache-DiT | [request quality policy](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/models/minimax_h3/quality_policy.py) | Record actual hit counts and refresh policy. Repeated inputs must not hide cross-request cache leakage. |
| INT8 / RainFusion | [NPU recipe](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/recipes/MiniMaxAI/MiniMax-H3-NPU.md) | Separate quantization, sparsity and combined rows; preserve configured step count. T2VA sparse-window guidance is not Ref2VA acceptance. |
| Fused indexed modulation | [shared operators](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/layers/indexed_modulation.py) | Already exists, including NPU grid chunking. Profile before proposing a new kernel. |

The current baseline explicitly rejects Ref2VA TeaCache in `cache/teacache/backend.py`
because it has not been calibrated. The older TeaCache record is not a runnable
main-supported Ref2VA option; use supported Cache-DiT first.

The imported H3 TeaCache/reference-KV/head-bucket records identify older reports,
not measurements of this baseline. FastH3's T2VA-only distillation is outside this
Ref2VA campaign. Existing features adopted via configuration receive upstream
attribution, not new implementation credit.

## Validator scope

Video SSIM/PSNR use FFmpeg's full-video filters from the upstream accuracy helper.
Audio metrics are copied verbatim from the pinned H3 quantization test. LPIPS uses
the same AlexNet, native-resolution normalization and every decoded frame, but
streams frames through one CPU model to bound memory. Full-length metadata and
PCM shape checks precede acceptance; no truncation to the shorter output is allowed.
The frozen helper snapshot retains the upstream LPIPS function for audit.

Run with an optional CPU environment containing `torch`, `torchvision`, `numpy`,
`lpips==0.1.4`, plus `ffmpeg` and `ffprobe`:

```bash
python validator/compare.py --baseline <BASELINE_MP4> \
  --candidate <CANDIDATE_MP4> --frames <EXPECTED_FRAME_COUNT> \
  --output <QUALITY_JSON>
```

Missing dependencies or malformed media fail the command; they never establish
PASS. A validator PASS is only matched video/audio parity under the frozen gates.
It does not establish reference identity, semantic correctness, lip synchronization,
temporal benchmark scores, request latency, or clean server lifecycle. Those
claims need their own retained evidence.

## RSI lessons to evaluate

1. Inspect current source before importing old optimization patches: distinguish
   a missing implementation from an existing option needing qualification.
2. Qualify the execution identity and runtime before spending full-model time.
   Shared-NPU reservations depend on real process ownership; a display label is
   insufficient. Library ownership checks may use primary rather than supplemental
   groups; retain the actual failure and repair in environment evidence.
3. Treat a correct benchmark as an optimization prerequisite. Video container
   validity and reduced denoise time alone cannot establish joint audio/video E2E
   improvement.

These are campaign observations and workflow hypotheses. No controlled experiment
has yet shown that they improve an optimizer's success rate or search efficiency.
