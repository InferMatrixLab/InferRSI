# Qwen-Image-2.1-Turbo decision and image benchmark

The frozen [protocol](protocol.json) connects retrieval to one local image-generation decision. The same rule accepts a target-specific pinned passage reporting interleaved RoPE and decoded output quality. The raw original query on main returned zero qualifying passages in its top five and kept eager RoPE. P1 used a second query with the checkpoint, device and workload, read the top-ranked 4,696-byte record, and selected fused RoPE for a local trial. Manual Find on main with the same second query selected fused too. The caller supplied the follow-up and the passage criterion. Each arm had the same maximum of five hits per query and 65,536 delivered source bytes.

Main was `7626c58f8158986770f0515888572ebb550d1751`. The [raw](raw.json), [manual](manual.json) and [P1](round.json) traces retain the ranked references, exact revision, delivered bytes, citation and resulting configuration.

## Workload

One Ascend 910B1, driver 25.5.0, BF16 checkpoint, vLLM 0.31.0 and the vLLM-Omni [engine checkout](https://github.com/amy-why-3459/vllm-omni/commit/399cc01d1bc4542964d91aaa17fb43862a8cf3b3). The public Ascend container manifest is `quay.io/ascend/vllm-omni@sha256:1f10e87fa4fcc9ed8fa966418161ae0a27b6a1a5f5cfaca35ef754a4a538f1e7`. The process sets `enforce_eager=True` for both arms; only the transformer's `QWEN21_NPU_ROPE` setting changes. Both arms use the same conditioning reuse, native eight-sigma schedule, prompt, 1280×704 resolution and guidance scale 1.

A fresh process loads the model per block. Two complete warm-ups use seeds 40 and 41. Three measured requests use seeds 42, 43 and 44. Time starts immediately before `Omni.generate` and ends after materializing decoded RGBA bytes on the host. This includes prompt encoding, denoising, VAE decoding and image delivery. Model load and PNG serialization are outside the interval. This offline, single-request fixture does not measure HTTP serving, concurrent traffic or cold startup.

## Measurements

| RoPE trial | First block mean | Second block mean | Overall mean | Median |
| --- | ---: | ---: | ---: | ---: |
| Raw → eager | 2.6368 s | 2.6342 s | 2.6355 s | 2.6361 s |
| P1 → fused | 2.4424 s | 2.4445 s | 2.4434 s | 2.4441 s |

In A1–B1–B2–A2 order, two blocks per configuration gave six measured requests each. Mean latency fell by **192.1 ms per image (7.29%)**, a **1.079×** speedup. All six matched-seed comparisons had identical RGBA SHA-256, SSIM 1.0 and infinite PSNR. The one-prompt sample covers three distinct seeds. Manual expanded Find led to the same fused configuration. The measured gain comes from that existing engine setting. The PR exposes how the evidence for trying it was found and read. The standalone decision calls took 0.60 s for raw, 1.15 s for manual and 1.18 s for P1 in one run per arm; these one-off costs are outside the per-image timing.

Every block saved all five images and returned from explicit engine close, then the container exited 134 during process teardown with `corrupted size vs. prev_size`. The container also reported a package-version warning for the mounted engine sources. All 20 saved PNGs were decoded again and verified against their timed RGBA hashes. The timings and quality comparisons describe completed requests. Clean process shutdown and production serving stability remain unverified. [Per-request measurements and exit codes](results.json) · [Checkpoint component hashes](checkpoint.json)

## Fresh model selection

After the image trial, Qwen2.5-VL-3B-Instruct independently selected a source from each ranked list by scoring the allowed single-letter answers. Each source choice saw titles and summaries, with an option to defer. A separate call saw up to 6,400 characters per delivered body and chose the local trial. The model received the same hardware, workload, preset follow-up and action criterion in both arms. The expected ref, scoring quotation, measured latencies and paired-image results were withheld. Both arms ran against the integrated reader, which returned the same ranked IDs as the main controls above.

With just the original query, the model read the generic cache-lifecycle Skill and chose eager. With the follow-up, it also selected the Qwen-Image Ascend record and chose fused. This five-call check reproduced the two choices after the hardware experiment; it covers one model and one task. [Model inputs and selection code](model_selector.py) · [Choices, logits, token counts and pinned reads](model-results.json)

## Replay

Use the [decision driver](decisions.py) on the stated main checkout for `raw` and `manual`, and on this PR for `round`. The checked-in arm traces drive the launch order. The host needs Bash, Docker with the Ascend runtime, the NPU allocator and Python with Pillow, NumPy and scikit-image.

```sh
d=docs/reviews/knowledge-retrieval/qwen-image
PYTHONPATH="$BASELINE/src" python "$d/decisions.py" raw
PYTHONPATH="$BASELINE/src" python "$d/decisions.py" manual
python "$d/decisions.py" round
docker pull quay.io/ascend/vllm-omni@sha256:1f10e87fa4fcc9ed8fa966418161ae0a27b6a1a5f5cfaca35ef754a4a538f1e7
export OMNI_CHECKOUT CHECKPOINT RESULTS
npu run --gpus 1 -- bash "$d/run_abba.sh"
python "$d/compare.py" "$RESULTS"
```

In a Transformers and torch-npu environment with the PR installed, run `npu run --gpus 1 -- python "$d/model_selector.py" "$SELECTOR_CHECKPOINT" model-results.json` with a local Qwen2.5-VL-3B-Instruct checkpoint to repeat the source-selection check.

Set `OMNI_CHECKOUT` to the pinned engine checkout, `CHECKPOINT` to the local Turbo model and `RESULTS` to a fresh results directory, all absolute paths. Each block retains every PNG, measured and warm-up durations, RGBA digests and its container exit code.
