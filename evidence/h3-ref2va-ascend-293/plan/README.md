## Goal and authority

User-requested campaign: minimize MiniMax-H3 Ref2VA delivered-video latency on Ascend NPU, retaining quality acceptance. The requester explicitly allows quantization and caches with quality gates. Codex acts as the implementation agent for the authenticated contributor. This authorizes this campaign only, not closure of other research issues or paid model evaluation.

Deliver accepted vLLM-Omni improvements in one PR, with each optimization's source and individually measured effect. Deliver reusable RSI experience and rejected experiments to InferRSI (the canonical successor of OmniRSI). No global optimality claim: report the best validated configuration within the declared search space.

## Frozen initial scope

- Baseline source: vllm-project/vllm-omni `c7f56f0155953c7d4a77276a2f4fcbd844ab0da2`.
- Hardware: one node, 8 Ascend 910B1, 64 GiB/device, fixed physical allocation inside `npu run`; no unreserved workload.
- Environment image: `quay.io/ascend/vllm-omni:nightly-20261022-6b35bca`, local image SHA256 `7fc6c73bd19a6ef4ee8d6048009972234796a1fc1bd3067168a425343cc476f7`. Runtime compatibility is currently being checked; a changed environment requires a new frozen RunSpec before comparisons.
- Checkpoint: original MiniMaxAI/MiniMax-H3 Ref2VA BF16; local content identity to be recorded before formal measurements.
- Inputs: official Ref2VA test prompt plus video SHA256 `d6edc20ac82aa980c9cbd0b05b371f60d12dc8d018492e571b42de0086819c41` and audio SHA256 `2a48d447b343b38a2c504d5281a0c97c688db0ba87931ed9282c598bd6752454`. Downloaded content matches the pinned upstream accuracy test.
- Workload: 1344x768, 24 FPS, output durations 5 s and 15 s, seed 0, 50 configured inference steps, flow shifts 12/3, concurrency 1. Seeds/reference variations are held-out checks before broader claims. Short-step bringup is diagnostic only.
- Base serving: USP8/ring1, text TP8, VAE tile8, DLO, dense LaserAttention, original BF16. Startup, warmup, request upload-to-full-MP4 delivery, and stage timings remain separate.
- Quality gates: decoded-video SSIM >=0.97 and PSNR >=34 dB (from upstream H3 reference test), LPIPS <=0.20, audio multi-resolution spectral cosine >=0.80 and RMS ratio in [0.50,2.00] (from upstream H3 quantization test). Apply to matched baseline/candidate outputs; these are campaign adoption of existing thresholds, not evidence that the original CUDA tests qualify NPU. Require matching frame count/dimensions/FPS, audio rate/channels/sample count, finite values and successful decoding. Record baseline rerun variance. Temporal/perceptual generalization remains a separate limitation.
- Formal comparisons: alternating AB/BA, independent server processes, a warmup per workload/arm, at least three measured requests per workload/arm; fixed inputs/device/config except the named candidate. No estimated p95 from means; retain raw samples and report small sample limits.

## Search and attribution

Profiling first, then one hypothesis per step: residency/transfer, fused operators/packing, reference-KV reuse, TeaCache/Cache-DiT, INT8 and RainFusion. Existing main features are configuration baselines, not newly authored code. Do not use T2VA-only FastH3 distillation for Ref2VA. Test individual effects and the final combination directly; do not add percentages from separate cohorts.

Sources: [task benchmark selection #60](https://github.com/InferMatrixLab/InferRSI/issues/60), [engineering benchmark scope #252](https://github.com/InferMatrixLab/InferRSI/issues/252), pinned vLLM-Omni NPU recipe, H3 accuracy/quantization tests, and InferRSI source-attributed H3 records. Imported CUDA/older NPU results remain unverified on this campaign.

## Acceptance and delivery

- [ ] Runnable baseline, source/model/environment manifests and lifecycle evidence.
- [ ] Profiling-backed candidates with exact source attribution and rejected outcomes retained.
- [ ] Independent video/audio quality checks and matched repeated E2E for every accepted candidate.
- [ ] Direct original-baseline versus final-combination test at both durations.
- [ ] One vLLM-Omni PR with individual effects and exact evidence scope.
- [ ] InferRSI contribution using existing evidence/knowledge contracts; source and optimizer improvement claims separated.

Current status: INCONCLUSIVE, bringup underway, no optimization result claimed. Stop candidate promotion on failed quality, request failures, resource interference or incomplete process cleanup. Implementation readiness and campaign acceptance are separate; final acceptance remains with the requester. Any unavailable measurement is reported explicitly.
