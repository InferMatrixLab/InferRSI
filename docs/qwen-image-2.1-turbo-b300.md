# Qwen-Image-2.1-Turbo · 4× B300

**Historical accepted result: 384.16 → 266.60 ms HTTP E2E, 30.60% lower latency,
with all 44 formal/held-out output files matching the canonical RGB and alpha
pixels exactly.** This is warm repeated-prompt inference under the controls
below, not a general cold-prompt or production-tail claim.

[Acceptance issue](https://github.com/InferMatrixLab/InferRSI/issues/3) ·
[Upstream optimization PR](https://github.com/vllm-project/vllm-omni/pull/8739) ·
[Ascend cohort](qwen-image-2.1-turbo-ascend.md)

## Results and scope

| Cohort | Baseline → candidate | Reduction | Decision |
| --- | --- | ---: | --- |
| Phase 1, five AB/BA groups | 385.0696 → 335.4234 ms | 12.89% | Historical 20% target missed |
| First phase 2 cohort | 382.9154 → 268.7692 ms | 29.8098% | 30% target missed; retained FAIL |
| Final H19 cohort | 384.1617 → 266.6048 ms | 30.6009% | 30% target met; 44 exact images |

Each value is a median of five trial means, with three requests per trial.
Final baseline means: `[384.1617,382.9615,377.6383,386.3696,399.7588]` ms;
candidate means: `[264.8543,268.7395,266.6048,261.8247,294.6473]` ms. The slow
fifth trial is retained. Ranges are descriptive; significance is not established.

The original-source baseline is `f69b1f2b19cece03f6736c7da093ea25de0e24fd`;
the accepted candidate is `330d411d2dd567bc061cb3124f4e39d195a4be45`.
The [complete historical patch](../evidence/qwen21-turbo-b300-20261010/patch/qwen21-turbo-b300.patch)
includes the earlier changes and applies to that baseline only. The final cohort
used devices 2/4/6/7 after foreign activity interrupted the earlier 2/5/6/7 group.
Both sides were freshly measured on the same selected devices; no outside task
was terminated. The 30.76% comparison to the earliest 385.07 ms value is
cross-cohort and is not the final formal denominator.

## Fixed workload

| Control | Value |
| --- | --- |
| Model revision | `Qwen/Qwen-Image-2.1-Turbo@d65dbc9a7e8f6b5479e33dee6030eaab2a906509` |
| Hardware | Four B300 SXM6 AC, NV18, NUMA 0; identical selected cards per comparison |
| Output | One native 1280×704 RGBA PNG/base64 response, concurrency 1 |
| Inference | BF16, CFG1, native eight sigmas, eager, FLASH_ATTN/FA4 |
| Parallelism | TP1 / Ulysses4 / Ring1 / VAE1, untiled VAE |
| Workload | Three prompts, seeds 42/43/44; held-out prompts use 142/143/144 |
| Warmup | Two full-shape rounds, seeds 10042–10044 then 11042–11044 |
| Timing | POST through complete JSON/base64 response download; parsing/writes excluded |
| Quality | Every native image, including the first response; RGB and alpha checked separately |

The exact prompt set and sigma grid are in the [runner](../examples/qwen21_turbo_b300.py).
Historical gates are SSIM ≥ 0.99 and PSNR ≥ 35 dB per RGB/alpha channel; the
accepted outputs were additionally pixel-identical. No quantization, approximate
cache, step/resolution reduction, sampled-latent reuse or image replay is used.

Historical runtime: Python 3.12.3, Torch 2.13.0+cu130, vLLM 0.31.0,
Diffusers 0.40.0, Transformers 5.14.1, kernels 0.16.1, FA4 4.0.0b18 and driver
610.43.02. Default compilation failed preparation with `NameError: s28`; eager
was frozen before comparisons. Failed preparation is not a performance baseline.

## Reproduce or start a new campaign

For the upstream patch, use the [A/B serve and request commands](https://github.com/vllm-project/vllm-omni/pull/8739#issuecomment-6119754582)
and their [separately pinned rebase results](https://github.com/vllm-project/vllm-omni/pull/8739#issuecomment-6119846759).
The default-main → explicit-symmem PR recipe changes a communication flag;
do not call its reduction a matched-configuration code-only gain.

For a new InferRSI campaign, install the control package in the prepared inference
environment, reserve idle devices, pin the engine/model/runtime and freeze new
helpers and canonical images before search. Keep source, cache and output paths
separate. The current helper hashes the installed control package transitively.
Historical manifests require their original frozen bundle; do not mix them with
current helpers.

```bash
# Use absolute paths to prepared local resources.
export RSI_REPO=/path/to/InferRSI
export INFERENCE_PY=/path/to/prepared-env/bin/python
export ENGINE_REPO=/path/to/pinned/vllm-omni
export CAMPAIGN=/path/to/new-campaign
export MODEL_SNAPSHOT=/path/to/pinned/model-snapshot
export CUDA_VISIBLE_DEVICES=0,1,2,3
export OMP_NUM_THREADS=4

"$INFERENCE_PY" "$RSI_REPO/examples/qwen21_turbo_b300.py" --help
"$INFERENCE_PY" "$RSI_REPO/examples/qwen21_turbo_quality.py" --help
```

Preparation must materialize `$CAMPAIGN/artifacts/model-assets.json`, containing
`model`, `revision` and a `files` list with `path`, `sha256`, `bytes`, `mtime_ns`
for every snapshot file. Hash actual local files before freezing; the runner
checks full coverage and size/mtime against this manifest. The model path must
end in the pinned revision. Keep the prepared cache under `$CAMPAIGN/cache` and
place outputs outside the engine source. These prerequisites are not performed
by the trial command.

Generate a canonical reference and independent repeatability run first:

```bash
"$INFERENCE_PY" "$RSI_REPO/examples/qwen21_turbo_b300.py" \
  --source-repo "$ENGINE_REPO" --model-path "$MODEL_SNAPSHOT" \
  --cache-root "$CAMPAIGN/cache" --single-reference --tp 1 --ulysses 1 \
  --output "$CAMPAIGN/artifacts/reference/result.json"
# Repeat with a fresh reference-repeat output directory, then compare:
"$INFERENCE_PY" "$RSI_REPO/examples/qwen21_turbo_quality.py" \
  --reference-manifest "$CAMPAIGN/artifacts/reference/result.json" \
  --candidate-manifest "$CAMPAIGN/artifacts/reference-repeat/result.json" \
  --output "$CAMPAIGN/artifacts/repeatability.json"
```

The campaign helper still checks the reservation of four B300 devices for this
reference command, even though it starts one worker. Keep all four reserved.

**Profile before editing.** Use the same image shape and an explicit shortened
sigma grid for diagnostics; changing `num_inference_steps` alone does not shorten
this Turbo model. Diagnostic runs are excluded from acceptance:

```bash
"$INFERENCE_PY" "$RSI_REPO/examples/qwen21_turbo_b300.py" \
  --source-repo "$ENGINE_REPO" --model-path "$MODEL_SNAPSHOT" \
  --cache-root "$CAMPAIGN/cache" --tp 1 --ulysses 4 \
  --diagnostic --profile-steps 2 \
  --output "$CAMPAIGN/artifacts/profile/result.json"
```

Then qualify TP/Ulysses 1/4, 2/2 and 4/1 with full eight-step output validation.
The historical TP2/U2 and TP4/U1 cells failed quality; they were not promoted.
For each new iteration freeze one hypothesis, isolated variable, fixed controls
and stop condition; progress from pipeline/framework work to profile-derived
operators. Validate numerics, then full images and E2E. Do not run owned GPU
profilers concurrently with formal measurements, even on other cards.

A full trial uses the same runner without diagnostic flags. Use fresh output
paths, then validate the complete manifest:

```bash
"$INFERENCE_PY" "$RSI_REPO/examples/qwen21_turbo_b300.py" \
  --source-repo "$ENGINE_REPO" --model-path "$MODEL_SNAPSHOT" \
  --cache-root "$CAMPAIGN/cache" --tp 1 --ulysses 4 --repetitions 1 \
  --output "$CAMPAIGN/artifacts/trial-001/result.json"
"$INFERENCE_PY" "$RSI_REPO/examples/qwen21_turbo_quality.py" \
  --reference-manifest "$CAMPAIGN/artifacts/reference/result.json" \
  --candidate-manifest "$CAMPAIGN/artifacts/trial-001/result.json" \
  --expected-parallel 1,4 --output "$CAMPAIGN/artifacts/trial-001-quality.json"
```

Use the [CLI run contract](quickstart.md#real-remote-experiment) for five fresh
alternating AB/BA groups and an explicit quality command. Freeze the 30% target
against a fresh original-source baseline before search. Current aggregate
validation accepts `--inferrsi-run --output {result}`; the
[v4 directory adapter](../examples/qwen21_turbo_validation_adapter.py) is only for
the historical validator's run-root convention. It requires ten complete trial
reports and all 40 comparisons, without changing numerical gates.

## Optimization ledger

Exploratory values below are not additive gains or the final five-group score.
Rejected attempts and failed cohorts remain part of the record.

| Round | Optimization / observation | Exploratory result and disposition |
| --- | --- | --- |
| H1 | Pack equal Q/K/V into one 5D exchange | 394.68 ms, quality passed; reverted |
| H2 | Bounded exact text-conditioning reuse | 369.54 ms; retained, exact pixels |
| H3 | Initial Q/K RMSNorm + complex RoPE fusion | Operator tests passed, full images failed; reverted |
| H4 | Share token selection and scale/gate tanh per step | About 360 ms; retained, exact pixels |
| H5 | Byte-preserving symmetric-memory Ulysses | About 347 ms; retained, exact exchange/pixels |
| H6 | Graph QKV projection/norm/RoPE | About 345 ms; no material E2E gain, removed |
| H7 | Graph post-attention residual/norm/FFN | About 352 ms; replay/copy costs, removed |
| H8 | Reuse request-local geometry/RoPE/mask metadata | About 340 ms; retained, exact pixels |
| H9 | Fuse residual gate multiply/add and SiLU/multiply | 331.45 ms; retain BF16 materialization, exact pixels |
| H10 | Fuse RoPE with the actual complex FMA ordering | 327.15 ms; retained as normalization fallback |
| H11 | Fuse casts and norm/RoPE suffix around ATen mean | 300.94 ms; exact pixels, superseded by H13 |
| H12 | Reuse exact VAE norm epilogue | 280.25 ms; retained, no convolution/tiling changes |
| H13 | Match ATen reduction tree in head128 norm/RoPE | 277.44 ms quiet trial; retained, exact pixels |
| H14 | Broadcast decode scale/gate instead of dense rows | 283.61 ms; no demonstrated benefit, removed |
| H15 | Direct strided staging + batched QKV exchange | 265.19 ms after removing H14; retained, exact pixels |
| H16 | Skip empty decode joint-query concatenation | 271.52 ms; no demonstrated benefit, reverted |
| H17 | Reorder pointwise eligibility/property checks | 359.88 ms with observed host load; reverted, no causal claim |
| H18 | Probe compiled Triton launch API | Host enqueue 6.41 → 3.95 μs; no E2E integration |
| H19 | Validate native BF16 pointwise contracts once per step | 266.47 ms on new qualified cohort; retained, exact pixels |

This is 18 code hypotheses plus one API investigation. Corrections and reruns
are not extra rounds. H13 also had a failed startup and a concurrent-diagnostic
342.14 ms attempt; neither was silently removed or promoted.

The H8 → phase 2 same-shape, two-step profile showed communication kernels
768 → 384 and CUDA launches 10,581 → 4,173 (60.56% fewer launches). H19 reduced
pointwise eligibility calls 576 → 6. These are diagnostic counts, not inferred
critical-path speedups. Profile-stop API timeouts remain failed diagnostics even
when all four traces exported successfully.

KDA references used for the operator workflow:
[workflow](https://github.com/NVlabs/kda/blob/ef6ce617693ef0782b3ecb9f37e39bbf10226a90/docs/agent-flow.md),
[KernelWiki](https://github.com/mit-han-lab/KernelWiki/blob/76d27b56f804e7e7295d4c570e1e5d7eef4b0a75/SKILL.md),
[ncu-report](https://github.com/mit-han-lab/ncu-report-skill/blob/d1887948c7d53690cfe6605f59c1329b8a1c6bb5/SKILL.md).
MiniMax-H3 fusion ideas were references; its published gains and approximate
methods were not substituted for Qwen measurements.

## Review lessons and evidence

Keep common framework dispatch generic and hardware/model policy in adapters.
Shared kernels must test every affected consumer, including Wan encoder/decoder,
dtype/layout/fallback behavior, deferred bias, gradients and hooks. Full Qwen
image success does not certify other models or hardware. Two Wan FP16 baseline
failures remained failures, even after matching main/candidate output hashes.
B300 validation does not establish H200/Hopper correctness.

| Evidence | Scope |
| --- | --- |
| [Historical archive manifest](../evidence/qwen21-turbo-b300-20261010/results/archive-manifest.json) | Downloadable source/results bundle and recomputation checksums |
| [Review matrix](../evidence/qwen21-turbo-b300-review-20261012/results/summary.json) | Separately pinned review-time comparison; not the historical denominator |
| [Shared-consumer regression](../evidence/qwen21-turbo-b300-human-review-20261012/results/summary.json) | Consumer map, checks and baseline-failure attribution |
| [Modularization regression](../evidence/modular-refactor-20261013/README.md) | 4/4 native RGBA pairs exact; functional smoke, no new latency claim |
| [Earlier detailed ledger](https://github.com/david6666666/OmniRSI/blob/ab343f98f7da55e428275c20c2324732201b9000/docs/qwen21-turbo-b300-phase2-results.md) | Immutable profile details, rejected trials and original source pins |

The [contribution guide](contributing.md) consolidates acceptance, evidence and
shared-component review rules. New runs must keep their own source and protocol
identity instead of inheriting an earlier campaign's verdict.
