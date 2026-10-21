# MiniCPM-o 4.5: single-L20X throughput study

Acceptance: [InferRSI #49](https://github.com/InferMatrixLab/InferRSI/issues/49).

**Original strict quality verdict: FAIL** for the completed speaker-only candidate. A separately authorized noninferiority evaluation on previously unused prompts is pending; it does not change the original verdict. Component PASS does not establish service PASS.

## Scope and controls

- One NVIDIA L20X (143771 MiB) per serving engine; shared host, reserved GPUs. vLLM baseline and speaker candidate use the same physical GPU. Other comparisons use the same GPU SKU.
- Official model revision and all asset hashes: `plan/official-model-manifest.json`. The initially discovered local checkpoint had different metadata and was excluded.
- Current main revisions are frozen in `plan/baseline-plan.json`. Main means those fetched snapshots, not a moving branch.
- Seed-TTS English voice cloning: disjoint warmup, tuning and evaluation pools; source metadata and reference WAV hashes are frozen.
- Concurrency 1, 2, 4, 8, 16, 32. Each baseline cell has 320 requests per repeat, one discarded run, then three measured repeats. Warmup uses 2 × concurrency separate rows.
- Persistent-server steady state: caches are not reset between runs/cells. `cache_policy: none` means no reset procedure, not disabled caches. This is not the peer engine strict cold-cache certification; C32 uses 320 rather than its 640 requests.
- Throughput is 25 × delivered audio seconds / measured wall time; it is an audio-frame equivalent, not video fps. The table averages three run throughputs. TTFA percentiles pool 960 requests; RTF is the mean per-request last-audio latency divided by generated duration.
- vLLM streams audio chunks. SGLang returns a terminal waveform, so its TTFA is effectively completion latency. Do not interpret the two TTFA columns as equivalent streaming capability.

The native main configurations also differ: SGLang Code2Wav uses float16, compiled DiT/HiFT, eight reference workers and a 32-entry prompt cache; this vLLM baseline uses its default FP32 CFM path and serial CPU reference preparation. These are native-engine comparisons, not an isolated backend comparison with identical numerical kernels and scheduling.

## Main-branch baselines

| Engine | C | Frames/s | TTFA p50 ms | TTFA p95 ms | RTF mean |
|---|---:|---:|---:|---:|---:|
| vllm | 1 | 192.6 | 307.5 | 343.1 | 0.132 |
| vllm | 2 | 295.5 | 410.9 | 534.6 | 0.172 |
| vllm | 4 | 394.0 | 881.6 | 1000.2 | 0.267 |
| vllm | 8 | 488.4 | 1375.3 | 1602.6 | 0.426 |
| vllm | 16 | 513.3 | 1702.7 | 2727.5 | 0.797 |
| vllm | 32 | 540.2 | 2752.3 | 4732.2 | 1.502 |
| sglang | 1 | 291.3 | 371.0 | 461.9 | 0.089 |
| sglang | 2 | 476.6 | 451.3 | 578.7 | 0.109 |
| sglang | 4 | 713.8 | 599.6 | 799.9 | 0.145 |
| sglang | 8 | 1043.2 | 835.1 | 1042.6 | 0.198 |
| sglang | 16 | 1558.5 | 1112.0 | 1411.5 | 0.264 |
| sglang | 32 | 1918.5 | 1763.5 | 2479.4 | 0.425 |

All 11,520 measured baseline requests completed successfully. Raw per-request metrics, individual run variation and WAV hashes are in `results/*-main-repeated.json.gz`. Generated WAVs, wire payloads and unredacted server logs remain local.

## Reproduction

Set paths explicitly; do not point the benchmark at an unrelated running service. Use separate compatible environments for the two engines, matching the package manifests under `plan/`.

```bash
export MODEL=/absolute/path/to/pinned-official-model
export PEER=/absolute/path/to/minicpm-o-4.5-single-gpu-engine
export SEED_TTS_ROOT=/absolute/path/to/seed-tts-eval
export EVIDENCE=/absolute/path/to/this/evidence/directory
export RUNS=/absolute/path/to/output-directory
export VLLM_OMNI=/absolute/path/to/vllm-omni
export SGLANG_OMNI=/absolute/path/to/sglang-omni
```

The peer benchmark revision is recorded in `validator/benchmark-sources.json`; do not silently substitute a newer client. The driver uses explicit adapter sampling and prompt settings from that snapshot.

Baseline vLLM server (activate its environment first, reserve one GPU):

```bash
python -m vllm_omni.entrypoints.cli.main serve "$MODEL" --omni \
  --served-model-name openbmb/MiniCPM-o-4_5 --host 127.0.0.1 --port 29161 \
  --deploy-config "$VLLM_OMNI/vllm_omni/deploy/minicpmo_4_5_turn.yaml" \
  --trust-remote-code --init-timeout 1800 --stage-init-timeout 1800
```

Baseline SGLang server (activate its environment first, reserve one GPU; use unused distributed ports and a writable private endpoint directory):

```bash
python -m sglang_omni.cli serve --model-path "$MODEL" --model-name minicpmo \
  --thinker.engine.mem_fraction_static .55 --talker.engine.mem_fraction_static .15 \
  --thinker.engine.dist_init_addr 127.0.0.1:29671 \
  --talker.engine.dist_init_addr 127.0.0.1:29672 \
  --thinker.factory.max_seq_len 8192 --endpoints.base_path "$RUNS/endpoints" \
  --host 127.0.0.1 --port 29171
```

After readiness, run the matched benchmark client:

```bash
PYTHONPATH="$PEER" python "$EVIDENCE/validator/run_baseline.py" \
  --adapter vllm-omni --url http://127.0.0.1:29161 \
  --out "$RUNS/vllm-main" --concurrency 1 2 4 8 16 32 --requests 320 --repeats 3
PYTHONPATH="$PEER" python "$EVIDENCE/validator/run_baseline.py" \
  --adapter sglang-omni --url http://127.0.0.1:29171 \
  --out "$RUNS/sglang-main" --concurrency 1 2 4 8 16 32 --requests 320 --repeats 3
```

For tuning use `--id-set tuning --requests 64 --repeats 1`. Do not mix tuning rows with held-out evaluation. Original baselines used driver v1; v2 only adds tuning-pool selection, with unchanged evaluation behavior. File hashes and usage are recorded in `validator/driver-revisions.json`.

## Speaker candidate reproduction

Check out the candidate revision in `patch/candidate.json`; install the optional
TensorRT package matching CUDA (this run used `tensorrt-cu13==11.4.0.106`).
Copy `patch/speaker-only.yaml` beside `minicpmo_4_5_turn.yaml` in the vLLM-Omni
deploy directory. Start the same server with that overlay as `--deploy-config`.
Set `COSYVOICE3_TRT_CACHE` to a writable persistent directory; first startup
builds the engine. Use the identical benchmark command against the candidate
port and a separate output directory. No DiT TensorRT, quantization, cache-size
or sampling changes are part of this candidate.

## Accuracy and numerical validation

Quality uses existing SGLang-Omni scorers: Qwen3-ASR WER, WavLM speaker similarity (reported ×100), and UTMOS. Scorer weight hashes are frozen in `validator/scorer-model-hashes.json`. Score C1/C16/C32 run1 WAVs after each run has finished saving files; merely seeing `summary.json` is insufficient.

```bash
PYTHONPATH="$SGLANG_OMNI:$PEER" python "$EVIDENCE/validator/score_outputs.py" \
  --run "$RUNS/vllm-main/c32/run1" --out "$RUNS/quality-main-c32.json" \
  --scorers /absolute/path/to/scorer-assets --asr-port 29181 --device cuda:0
```

The ASR service is a separate Qwen3-ASR-1.7B SGLang-Omni server. The scorer validates nonempty finite audio and retains per-request scores. Public quality artifacts omit generated transcripts but retain WAV hashes and error counts.

Speaker numerical validation uses the checked-in `validator/bench_speaker.py`. It covers 32 tuning references plus short partial-window inputs, with 10 warmups and 30 synchronized latency samples. `speaker_trt_ieee.py` is the preserved historical precision-only diagnostic helper; the final CPU-reference path imports the candidate implementation directly.

```bash
PYTHONPATH="$PEER:$VLLM_OMNI" python "$EVIDENCE/validator/bench_speaker.py" \
  --model "$MODEL" --backend trt --cpu-reference --out "$RUNS/speaker-micro.json"
```

## Interpretation limits

The optimization target is high-concurrency throughput with no speech-quality regression, not a globally optimal configuration. English voice cloning does not establish multilingual, visual, full-duplex or interruption correctness. Historical reference-engine results are prior art, not measurements reproduced by this campaign. Profiling perturbed MRv2 execution, so its stack samples are diagnostic only and excluded from performance tables.

## Separately authorized noninferiority holdout

The original zero-regression gates are preserved. After seeing first-cohort results, the user authorized a new engineering tolerance: WER +0.20 percentage points, SIM (×100) −0.50, UTMOS −0.05. These are not published perceptual equivalence thresholds. `plan/noninferiority-holdout.json` freezes unused evaluation rows 320–639, concurrency 1/16/32, and the paired 20,000-resample prompt bootstrap. Every one-sided 95% degradation upper bound must meet its margin; missing evidence is INCONCLUSIVE. Model/profile selection uses the existing throughput cohort before opening the new holdout. No threshold adjustment or tuning is allowed after those outputs are inspected.

## Completed speaker-only service result

The three-repeat speaker-only run completed all 5,760 measured requests. The original quality gate is **FAIL**, even though high-concurrency throughput improved in every repeat. Run-level variation and all requested latency metrics are retained in `results/speaker-comparison.json`. C1 SIM/UTMOS decreased; C16/C32 WER increased. Repeated C1 scoring and waveform diagnostics are preserved rather than relabeling the differences as noise.

| C | Frames/s | TTFA p50 ms | TTFA p95 ms | RTF mean |
|---|---:|---:|---:|---:|
| 1 | 190.8 | 314.0 | 350.3 | 0.133 |
| 2 | 298.0 | 405.8 | 499.2 | 0.170 |
| 4 | 457.0 | 611.3 | 736.3 | 0.226 |
| 8 | 626.7 | 885.2 | 1096.9 | 0.331 |
| 16 | 728.9 | 1180.8 | 1683.7 | 0.560 |
| 32 | 803.4 | 1745.6 | 2421.3 | 1.008 |

## Selected speaker + MPS profile

All 5,760 measured requests completed. The profile was selected by the predeclared geometric mean of C16/C32 three-repeat throughput, before generating the new holdout. Its original strict speech verdict is also **FAIL**; use `results/mps-comparison.json` for that verdict and `results/noninferiority-holdout.json` for the separate new decision when available. Copy `patch/speaker-mps.yaml` beside the base deploy YAML to reproduce this optional profile.

| C | Frames/s | TTFA p50 ms | TTFA p95 ms | RTF mean |
|---|---:|---:|---:|---:|
| 1 | 184.1 | 312.2 | 354.1 | 0.138 |
| 2 | 323.8 | 351.7 | 423.3 | 0.157 |
| 4 | 519.3 | 479.4 | 619.0 | 0.196 |
| 8 | 710.5 | 697.1 | 954.1 | 0.290 |
| 16 | 829.4 | 1042.0 | 1602.3 | 0.493 |
| 32 | 942.3 | 1510.9 | 2712.0 | 0.858 |

![Concurrency comparison](results/concurrency-comparison.png)

Bands show the minimum/maximum run throughput, not confidence intervals. Quality qualification is separate. MPS improves high-concurrency throughput here but reduces C1 throughput; C32 TTFA p95 is worse than speaker-only even though throughput is higher.

## Reproduce the separately frozen holdout

Run `validator/holdout_pair.py --help` for explicit environment/repository paths.
It starts baseline then candidate inside a single externally reserved GPU,
uses `run_holdout.py --eval-offset 320 --requests 320 --repeats 1`, and saves a
`complete` marker only after all WAVs are written. Use the selected MPS overlay
and the model, package, scorer and source pins in this evidence tree. Do not run
another performance client against either service concurrently.

Score run1 at C1/C16/C32 for both roles with `validator/score_outputs.py`, naming
outputs `vllm-holdout-main-c{C}.json` and
`vllm-holdout-candidate-c{C}.json` in a common quality directory. Then run:

```bash
python "$EVIDENCE/validator/noninferiority.py" \
  --plan "$EVIDENCE/plan/noninferiority-holdout.json" \
  --quality-dir "$RUNS/quality" --out "$RUNS/noninferiority-holdout.json"
```

The validator checks exact frozen prompt IDs and complete scorer coverage,
recomputes corpus WER from counts in each paired resample, and reports every
metric's degradation, confidence upper bound, margin and verdict. All nine
checks must pass. This inference is conditional on the generated outputs;
it does not establish equivalence across generation seeds or replace a
listening study. A failed upper-bound gate does not by itself prove perceptual
inferiority.

Host CPUs and the filesystem are shared with other jobs; GPU reservations are
exclusive, but CPU affinity is not isolated. The host has two Intel Xeon
Platinum 8480C sockets, 112 physical cores / 224 hardware threads. Results are
scoped observations on this host, not hardware-independent performance claims.
