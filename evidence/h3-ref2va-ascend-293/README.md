# MiniMax-H3 Ref2VA on Ascend

Governing acceptance: [InferRSI #293](https://github.com/InferMatrixLab/InferRSI/issues/293).
Status: **INCONCLUSIVE**. This campaign is in progress. No candidate speedup
is accepted yet. The dense baseline passed the adopted media gates, but worker
teardown remains unqualified and final repeated A/B is pending.

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

## Dense screening evidence

The first 50-step, 5-second dense arm completed its warmup and measured request.
[Timing receipt](results/dense-screening.json): warmup 569.43 s, one measured
request 403.49 s, with pipeline profiling enabled. These are pilot observations,
not an unprofiled or statistically qualified baseline. Eight workers needed
terminate and seven needed kill; the API server and container still returned 0.

[Official reference video parity](results/official-video.json) passed with SSIM
0.980571 and PSNR 42.63 dB. [Warmup-versus-measured media parity](results/baseline-repeat.json)
also passed: SSIM 0.986017, PSNR 46.26 dB, LPIPS 0.01584, audio spectral cosine
0.99961 and RMS ratio 1.00139. Repeated outputs are not byte-identical.

Teardown stack samples repeatedly located rank-local text-encoder reconstruction
in `restore_tensor_storage`, reached from DLO shutdown. The existing terminal
path skips AllGather reconstruction but still copies rank-local weights. A
downstream candidate skips terminal reconstruction for all managed blocks while
retaining ordinary disable and startup rollback. Its 116 DLO CPU tests and
applicable pre-commit checks pass. The cleanup-only NPU smoke removes the sampled
reconstruction but still requires forced process termination; see
[the partial result](results/shutdown-fixed-smoke.json) and [follow-up candidate](patch/README.md).
This is a lifecycle candidate and has no claimed inference-latency benefit.

## Cache-DiT screening evidence

The existing `quality=high` policy completed both requests. Its
[pilot receipt](results/cachedit-screening.json) records a 341.44 s warmup and
212.75 s measured request, versus dense's 403.49 s: an observed single-sample
47.27% reduction, with profiling enabled in both arms. This is not a final gain.
[Matched media parity](results/cachedit-quality.json) passed: SSIM 0.985838,
PSNR 46.08 dB, LPIPS 0.01615, audio spectral cosine 0.99775 and RMS ratio 1.00429.
This qualifies one seed and duration only; longer clips and held-out seeds remain
pending. Eight workers required terminate and seven required kill, so lifecycle
remains unqualified despite zero server/container exit codes.

The active policy logged `DBCache_F1B0_W4I1M0MC1_R0.04_N50_CFG0`.
The runner's summary condition incorrectly requires a startup Cache-DiT backend
even when request-owned Cache-DiT is active. Consequently no actual hit count is
claimed from this run. The upstream implementation receives optimization credit;
the downstream summary correction is observability work, not an inference gain.

## HSDP feasibility evidence

The [HSDP smoke receipt](results/hsdp-smoke.json) records one successful 2-step
request (124 frames, stereo 32 kHz) at 190.18 s, including first-request work.
This is not a 50-step performance or quality comparison. Per-rank model loading
took 402.62–1178.93 s; startup native sampling located CPU BF16 weight copies.
The full run's sampled peak reached 65,480 MiB on a device, including loading;
it is not a steady-state active-tensor footprint or a 15-second capacity result.

Teardown still required eight terminate and seven kill signals. The reply owner
finished while peers were still in first-call audio decode, and several workers
logged cleanup completion before their processes were terminated. Cleanup callback
completion and process exit are separate evidence requirements.

The existing pre-sharded HSDP loader is not a direct substitute for this native
checkpoint: its documented contract excludes tensor layout transforms, while H3
loading reorders grouped QKV weights. That path was not runtime-tested here.


## MC2 cache screening

The isolated `max_continuous_cached_steps=2` arm completed one warmup and one
measured 50-step, 5-second request. [Receipt](results/cache2-screening.json):
338.59 s warmup and 250.19 s measured, including cold peer work left after the
first response. Both requests reused 28 of 50 steps. The measured denoise stage
was 170.18 s and hot audio decode was 0.92 s. Do not rank this single sample as a
steady-state comparison against the earlier MC1 pilot.

[Decoded-media quality passed](results/cache2-quality.json): SSIM 0.985777,
PSNR 46.05 dB, LPIPS 0.01624, audio cosine 0.99841, RMS ratio 1.00311; scoring
exited 0. Under the diagnostic 60-second shutdown grace, the server/container
exited 0 with no terminate/kill calls; client completion to container exit was
27.24 s. Individual worker exit codes were not captured. This does not qualify
production-default cleanup or final performance. MC4 and the remaining isolated
arms are still running.


MC4 also passed [matched media quality](results/cache4-quality.json): SSIM
0.985651, PSNR 45.84 dB, LPIPS 0.01632, audio cosine 0.99755. Its
[screening receipt](results/cache4-screening.json) records 303.95 s warmup,
262.39 s measured E2E, and 162.50 s measured denoise. The larger peer cold tail
means the E2E sample is not a steady-state ranking. Both requests reused 29
steps, only one more than MC2. Diagnostic cleanup took 25.72 s with no forced
signals and server/container exit 0; individual worker exit codes were not
captured. Production qualification remains pending.
