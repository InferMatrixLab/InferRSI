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
| HSDP weight residency | [FSDP2 loader](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/distributed/hsdp.py) | Existing generic NPU-capable path; qualify H3 load-time memory, 8-rank USP interaction, output parity and latency before recommending it. |
| Exact AdaLN projection reuse | [shared cache](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/cache/exact_projection_cache.py) | Already enabled by default. Do not claim it as new work. Offload can invalidate storage signatures; count actual hits before relying on reuse. |
| Reference-KV reuse | [reference cache](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/models/minimax_h3/reference_kv_cache.py) | Approximate across timesteps even with BF16 cache storage. Validate reference refresh, SP layout, host transfer and audio/video quality. |
| Cache-DiT | [request quality policy](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/models/minimax_h3/quality_policy.py) | Record actual hit counts and refresh policy. Repeated inputs must not hide cross-request cache leakage. |
| INT8 / RainFusion | [NPU recipe](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/recipes/MiniMaxAI/MiniMax-H3-NPU.md) | Separate quantization, sparsity and combined rows; preserve configured step count. T2VA sparse-window guidance is not Ref2VA acceptance. |
| Fused indexed modulation | [shared operators](https://github.com/vllm-project/vllm-omni/blob/c7f56f0155953c7d4a77276a2f4fcbd844ab0da2/vllm_omni/diffusion/layers/indexed_modulation.py) | Already exists, including NPU grid chunking. Profile before proposing a new kernel. |

The pinned Git history attributes Cache-DiT request quality policies to
[vLLM-Omni #5853](https://github.com/vllm-project/vllm-omni/pull/5853), reference-KV
reuse to [#8072](https://github.com/vllm-project/vllm-omni/pull/8072), the resident
Ref2VA recipe to [#8577](https://github.com/vllm-project/vllm-omni/pull/8577), HSDP
infrastructure to [#1339](https://github.com/vllm-project/vllm-omni/pull/1339), and
H3 RainFusion/INT8 integration to [#5706](https://github.com/vllm-project/vllm-omni/pull/5706).
The frozen tree also contains later fixes, including mixed-video RainFusion span
handling in [#9241](https://github.com/vllm-project/vllm-omni/pull/9241). These are
implementation origins, not evidence that this campaign has reproduced a gain.

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
   A native HCCL TLS initialization failure was traced to a missing passwd UID
   entry; setting Python USER/LOGNAME alone was insufficient. Eight-rank all-reduce
   passed after supplying the entry. This is runtime qualification, not a model gain.
   Shared-NPU reservations depend on real process ownership; a display label is
   insufficient. Library ownership checks may use primary rather than supplemental
   groups; retain the actual failure and repair in environment evidence.
3. Treat a correct benchmark as an optimization prerequisite. Video container
   validity and reduced denoise time alone cannot establish joint audio/video E2E
   improvement.

These are campaign observations and workflow hypotheses. No controlled experiment
has yet shown that they improve an optimizer's success rate or search efficiency.

## Bringup qualification

The repaired runtime generated one 2-step, 5-second Ref2VA smoke response
(HTTP 200, 124 frames, 1344×768, 24 fps, stereo 32 kHz). This is neither
a 50-step performance sample nor a model quality acceptance. The server and
container returned zero, but all eight workers needed termination after the
15-second graceful-exit budget; TBE subprocess and resource-tracker warnings
followed. Lifecycle remains INCONCLUSIVE.

An isolated import probe found that the installed vLLM runtime leaves fresh
workers with no vLLM logging handler and an effective WARNING level until
logging is explicitly configured. Pipeline profiling INFO messages are therefore
missing from the initial launcher's logs. A diagnostic launcher applies the
installed vLLM LoggingConfig in each spawned process. It is an instrumentation
change and must not be credited as an inference speedup.

## Portable request timing client

`plan/run_client.py` adopts the multipart request contract from the pinned H3
accuracy test. Install `requests` in an isolated environment and provide FFprobe.
Start the server under the site's NPU reservation first; this HTTP client does
not own or reserve accelerators. Use a fresh output directory for each arm and
independent server lifecycle. For example:

```bash
python plan/run_client.py --base-url http://127.0.0.1:19421 \
  --prompt <PROMPT_TXT> --video <REFERENCE_MP4> --audio <REFERENCE_MP3> \
  --seconds 5 15 --steps 50 --seeds 0 --repeats 3 \
  --quality lossless --output <NEW_ARM_DIRECTORY>
```

Use `--quality high` only for the isolated Cache-DiT arm. The client times upload
through receipt of all response bytes; disk writes and FFprobe are outside the
clock. It retains one warmup per duration, every response, and each failure, and
stops on the first invalid request. Metadata checks are preliminary: run the
frozen decoded-media validator separately. Repeated requests in one server are
not independent process rounds, and the client does not qualify server teardown.
The initial screening uses an earlier private runner with the same request and
timing contract; do not relabel those runs as executions of this public script.
