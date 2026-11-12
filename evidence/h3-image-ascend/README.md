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
experimental source snapshots remain local. Most raw images, profiler traces and host
logs remain local. Six representative round-two full-resolution images are now
included in the [image gallery](results/round2-images/README.md). Published request
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

The attention component probes used real block weights and captured activations,
but synthetic RoPE and epsilon `1e-6` rather than the model's `1e-5`. They are
not complete model-correctness evidence. The K/V projection discrepancy was
measured before normalization; actual engine trials used the model epsilon.

The MLP layout probe used real weights from three blocks and captured activations
repeated to two token counts. Padding was slower and sometimes changed outputs;
transposed storage showed only small component differences. Neither variant is
adopted or evidence of an HTTP speedup. See `results/mlp-layout-probe.json`.

The evidence inventory validates the public export hashes. Historical source
hashes are classified as external dependencies, with original revision/context
metadata retained alongside each flat source manifest. These checks do not
qualify missing raw images or change the campaign verdict.

## Round-two generated images

[Control/candidate gallery and full-resolution PNGs](results/round2-images/README.md)
cover W1, W2 and W3 at seed 42, first measured request. The gallery includes the
30-image numerical-screen report and pixel-hash provenance. Panels were inspected
for presentation and obvious structural differences; this does not complete
full-resolution visual acceptance. The remaining 24 images are not bundled.

The subsequent real-weight NZ MLP probe covered three blocks, both MLP
projections and two token counts under two format settings (24 cases). All
outputs matched exactly. With internal formats disabled during linear execution,
observed component latency reductions ranged from 2.4% to 10.3%. Activations
were captured samples repeated to the tested lengths; these results do not
establish complete model parity or HTTP improvement. A same-VAE-configuration
four-device control/candidate experiment is pending; NZ is not yet adopted.

The [NZ round-four full-model trial](results/mlp-nz-round4/decision.json)
was rejected: all 30 image screens failed, and W2/W3 latency regressed.
The conversion affected 104 projections, including token-refiner MLPs outside
the original component probe. That scope mismatch is a diagnostic lead, not
an established cause. Both controls and candidates were repeatable. No NZ
change has been adopted in the downstream PR.

The main-block-only NZ retry also failed all 30 image screens and was rejected
(`results/mlp-nz-round5`). Parameter/2D/3D and complete MLP-chain component
probes remained exact on the sampled activations; this does not explain or
override the failed full-model result. An independent decoder-dtype probe
observed 68.15 ms BF16 versus 65.65 ms FP16 for a batch of 32 tiles, with
nonzero output error. A separate FP16 decoder model trial is queued; neither
component timing nor finite outputs establish image-quality acceptance.

The [FP16 decoder model trial](results/vae-fp16-round6/decision.json) passed
all 30 numerical image screens (minimum PSNR 46.90 dB, SSIM 0.99754), but
showed mixed latency: W1 improved while W2/W3 regressed. It is not adopted.
Complete visual acceptance and isolated repeated performance qualification
remain missing. Profiling the published configuration is queued to guide
the next distinct mechanism; all campaign targets remain unmet.

The refreshed rank-zero three-request profile was successfully exported in the
collection container after the initial offline export failed despite exit code
zero. Nonempty kernel/operator/step tables were verified. MatMulV3 and
FlashAttentionScore each account for about 39% of aggregate operator time;
these sums are not an E2E speedup claim. See `results/current-profile-round8.json`.

A controlled two-document layout probe preserved outputs but did not establish
consistent benefit. The FIA BSND probe showed roughly 4–5% reductions at medium
and large sequence sizes, with nonzero error. Its padding boundaries and input
tensors were synthetic, not captured model metadata. A three-image full-model
screen is running before any formal qualification; no attention change is adopted.

## Round nine: FIA rejected by whole-image screening

The three-image matched screen replaced native packed attention with FIA BSND
only in the 50 main transformer blocks. W1 scored PSNR 19.5261 dB / SSIM
0.849762 and W2 23.4763 dB / 0.935613, failing the unchanged numerical gates.
W3 passed (39.6448 dB / 0.993414); that does not qualify the candidate.
[Rejection and source identity](results/fia-round9-rejection.json) retain all
three checks. The full performance trial was skipped and no FIA code was
adopted into the engine PR. These cold screen requests establish no latency
improvement. Campaign acceptance remains **INCONCLUSIVE**.

Native FAS query tiling was also screened on synthetic 4432/6608/16768-token
inputs with real/padding document boundaries. All 12 cases were bitwise exact,
but all were slower than the unchunked operation; no engine integration or
HTTP trial followed. [Raw component samples](results/attention-query-tiling-probe.json)
do not establish a service result.

## Runtime compatibility and control-setting correction

`TASK_QUEUE_ENABLE=2` was rejected by the installed torch-npu graph capture
runtime before an HTTP experiment. A subsequent per-request row-index
preparation trial failed its dummy run because the new keyword was missing
from the model's strict forward contract. The corrected retry passed 14 CPU
checks; hardware qualification was pending at this checkpoint.
[Execution failures and retry identity](results/runtime-and-prepared-row-startup.json)
preserve these gaps without treating them as quality or performance results.

Review also identified a confound in historical graph-on/off comparisons:
the graph adapter disabled `allow_internal_format`, while a graph-off control
left the platform default enabled. Those samples compare coupled runtime
changes and cannot isolate the VAE contribution. The engine follow-up exposes
`npu_disable_internal_format` for matching future controls. Rounds 5, 6, 9 and
the prepared-row experiment use the same graph-on VAE setup in both arms;
their within-round comparisons do not have this specific confound.

Engine follow-up `7f8395fede3cb79991a256d1752c887b40faca30` restores deterministic caller state, propagates
the NPU worker grace through the outer stage client, and adds the explicit
internal-format control. [Checks and limitations](results/review-followup-checks.json)
record 26 CPU regressions and the single-device graph-output lifetime test.
These checks do not requalify historical HTTP measurements on the new revision.

## Round twelve: prepared row indices rejected

Preparing local embedding-row indices once per request preserved exact RGB
output in all 30 matched images. It did not improve HTTP latency: control
W1/W2/W3 medians were 11.039/2.574/4.243 seconds, versus candidate
11.197/2.925/4.502 seconds. [Samples and all quality checks](results/prepared-rows-round12-rejection.json)
record the unchanged workload and source identity. The candidate was not
adopted, and no final ABBA qualification was run. This experiment uses the
older ad37f7f engine base; it does not requalify the 7f8395fed follow-up.
Campaign acceptance remains **INCONCLUSIVE**, with all latency targets unmet.

## Round thirteen: request-local text preparation

Hoisting timestep-independent text projection and refinement preserved exact
RGB output in all 30 matched images. The candidate path was confirmed active.
Control W1/W2/W3 medians were 11.084/2.689/4.743 seconds, versus candidate
11.035/2.786/4.733 seconds. W1/W3 differ by less than 0.5%, while W2 is slower;
these sequential samples do not establish a consistent benefit.
[Samples, source identity and quality checks](results/prepared-text-round13-result.json)
use the current 7f8395fed base. The candidate was not adopted, and no final
ABBA qualification was run. All latency targets remain unmet.

## NZ load-order diagnosis

A full-model diagnostic compared ND repeats and NZ linear operations while
returning the original outputs. All 1,200 HTTP-stage comparisons were exact
(100 projections across four ranks and three input lengths), as were 400
startup comparisons. Only the first occurrence of each layer/input shape was
checked. All three output images remained exact; diagnostic timings are excluded.

The platform adapter runs before checkpoint loading. A separate real-weight
single-device probe found that copying chunks into a pre-converted NZ tensor
changed its contents, whereas converting populated weights was exact. H3's
merged fc1 loader performs chunked writes, making load order a plausible
explanation for prior NZ failures. [Probe results and limitations](results/nz-load-order-diagnosis.json)
also preserve the failed diagnostic attempt. Conversion after loading is being
qualified separately; these findings do not establish an end-to-end speedup.

## Round sixteen: NZ conversion after loading

Deferring MLP weight conversion until after checkpoint loading restored exact
RGB output in all 30 matched images. Four ranks each confirmed conversion of
100 populated projection weights. Control W1/W2/W3 medians were
10.842/2.480/4.191 seconds, versus candidate 10.727/2.556/4.065 seconds.
These mixed results do not establish a consistent overall benefit, and the
candidate was not adopted. [Samples and all quality checks](results/postload-nz-round16-result.json)
retain the source identity and protocol. Final ABBA qualification was not run;
all latency targets remain unmet.

A separate transposed-storage linear probe tested 18 cases using actual weights
and repeated captured activation samples. Twelve were exact; all six 1108-row
cases differed, and most cases were slower. [Component measurements](results/linear-transposed-storage-probe.json)
therefore did not lead to integration or an HTTP trial.
