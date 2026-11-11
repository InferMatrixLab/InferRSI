# MiniMax-H3-Image: four-device Ascend iteration record

Governing acceptance and requester-approved scope:
[InferRSI issue 390](https://github.com/InferMatrixLab/InferRSI/issues/390).
This is an exploratory evidence export, **INCONCLUSIVE for campaign acceptance**.
All three latency targets remain unmet. No final A/B/B/A qualification or
independent cross-hardware image-quality comparison is claimed.

## Delivered evidence

- `plan/`: frozen author workload, the separately authorized approximate-image
  screen, environment and source provenance.
- `results/`: per-request timings and pixel hashes, image-screen reports,
  rejected quantization diagnostics and component measurements.
- `patch/`: the consolidated downstream engine revision and retained scope.
- `validator/`: byte-identical experiment/validator code. The `plan/` copy inside
  this directory preserves the original quality validator's relative lookup.

The historical runs use the earlier source revision recorded in provenance.
The submission runs use the updated upstream base and the consolidated patch;
these groups must not be silently combined. The baseline for an incremental VAE
comparison is the same-layout native SP4 integration control with AdaLN offload,
not the historical TP4 run. Single-launch medians are observations, not a
reproducible service speedup claim or proof of the H200 target.

Historical candidate source manifests are included where available; their full
experimental source snapshots remain local. Raw images, profiler traces and host
logs also remain local. Published request
records omit prompts, local file names and process identifiers. Pixel hashes
identify retained outputs, but this export alone cannot independently recompute
image-quality scores. Reproduction requires the public checkpoint and example
assets, four allocated devices, and rerunning the recorded workloads. Numerical
screen PASS is narrower than final image-quality acceptance.

## Lessons from this iteration

1. **Establish repeatability first.** The initial native TP4 outputs changed
   across identical requests. Deterministic PyTorch algorithms and HCCL settings
   established same-device controls before pixel comparisons.
2. **Reduce residency before selecting parallelism.** Host-master AdaLN staging
   made resident SP4 feasible in the tested memory budget. Preserve the owning
   stager's transfer and projection-cache semantics; do not conflate this with
   approximate activation reuse.
3. **Graph lifetime is part of correctness.** VAE decoder replicas need separate
   streams and static buffers. Encoder autocast casts must be graph-owned rather
   than borrowed from a temporary autocast cache. Weight relocation invalidates
   captures, and retained outputs must survive reuse of a replica's buffers.
4. **Validate complete images after every numerical change.** Whole-model W8A8,
   SmoothQuant and all 58 bounded precision diagnostics failed the frozen screen.
   Small raw-projection differences in a communication-fusion trial also caused
   a W2 image failure, despite passing isolated operator probes. Padding the
   reordered weights did not resolve it. No failed variant was adopted.
5. **Microbench improvement is not service improvement.** Output-only fused
   communication preserved the tested image hashes but did not improve the
   overall HTTP result. SHMEM, static AdaLN graphs and AllGather-KV also lacked
   a consistent benefit in the tested configurations.
6. **Observe process exit, not only application shutdown.** The application
   cleanup message preceded NPU runtime finalization by roughly 20 seconds.
   A shared NPU-specific graceful deadline allowed natural worker exit while
   retaining bounded escalation and the existing deadline on other platforms.

The latest batched VAE candidate has 12 measured/warmup images and six heldout
seed images screened locally. The published overview was visually inspected without an obvious content or
structure regression; additional prompts and full-resolution visual review of
that exact configuration remain incomplete. The prior FP16-encoder/batch8
configuration has broader evidence; it does not automatically qualify batch32.

## Reproduction

Use the downstream engine's `docs/user_guide/diffusion/minimax_h3_image_npu.md`
for serving. In an isolated experiment directory, place the validator scripts
alongside the supplied `plan/` directory and install `requests`, `Pillow`,
`numpy` and `scikit-image`. For each fresh server configuration:

```bash
python benchmark.py --plan plan/workload.json \
  --examples "${MODEL_PATH:?}/examples" --output results/control
```

Repeat with a distinct candidate output directory and the same workload. Use
`--quality` for heldout seeds; validate only complete, independent matched runs:

```bash
python validate_approximate_images.py \
  --reference results/control --candidate results/candidate \
  --output results/candidate/quality-screen.json
```

The original validator remains frozen. The cached variant verifies all request
identities and image hashes, then reuses PSNR/SSIM only for identical image pairs;
its complete result matched the original on the failed full-fusion run. Neither
validator substitutes for prompt coverage, visual inspection, ABBA or independent
review. Rejected attempts and the remaining acceptance work are intentionally
preserved rather than presented as a successful campaign.

The [downsampled overview](results/quality-overview.png) is a visual aid only.
The [check summary](results/checks.json) records the current validation limits.

Engine delivery: [vLLM-Omni PR 10184](https://github.com/vllm-project/vllm-omni/pull/10184).
