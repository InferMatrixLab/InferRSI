# Local / Remote Codex Test plan: B300 × 4 / LTX-2.5

This execution plan applies to local and remote environments. **It does not claim that the best configuration has already been found or that a 20% latency reduction has been achieved.** All run configuration uses CLI arguments; JSON stores derived results, references, and frozen evidence.

## Goal and fixed protocol

First find the lowest-latency configuration that passes quality checks within the listed four-worker search space. Freeze that configuration, establish a fresh baseline with repeated AB/BA measurements, and optimize the code to satisfy:

`median(candidate trial mean E2E ms) <= 0.80 × median(best-config baseline trial mean E2E ms)`

This defines an E2E latency reduction of at least 20%, equivalent to approximately 1.25× speedup. It is not a gain over the initial single-GPU setup, default configuration, or an individual kernel. Each trial averages three fixed requests; the final statistic is the median of five trial means. Do not substitute a pooled request median or production throughput.

| Condition | Main plan |
| --- | --- |
| Hardware | Exclusive use of the same four B300 GPUs; same host, CPU/NUMA placement, and interconnect |
| Omni baseline | `2f289bb179d85671c116c10208b5c84b5c53f18f` |
| Model | `Lightricks/LTX-2.5-Diffusers`, revision `a6de4b5354f078db24d9cf4778c14846788aea3d` |
| Pipeline | `LTX2DistilledTwoStagePipeline`, T2V + audio |
| Shape | 1280×704, 121 frames, 24 fps, BF16, request concurrency 1 |
| Actual schedule | Stage 1: 8 Euler-ancestral steps; Stage 2: 3 Euler refine steps; both sigma lists passed explicitly |
| Guidance / decoder | positive-only; Native DiffVAE; 48kHz stereo audio |
| Attention / codec | CUDNN_ATTN; H264 encoding with preset ultrafast / threads 0 / CRF 18 |
| Workload | Three fixed prompts in the script; measurement seeds 42/43/44 |
| Warmup | Two full-shape rounds per fresh server, using 10042..10044 and 11042..11044 to prevent measured requests from reusing completed warmup outputs |
| Timing | `/v1/videos/sync`, from sending the request through downloading the complete MP4; includes A/V generation, encoding, and transfer; excludes model loading, warmup, and profiling |

The default 720p-class shape is 1280×704. The two-stage pipeline requires both dimensions to be multiples of 64, so 1280×720 cannot run directly. To use 1280×768, pass `--width 1280 --height 768` consistently to every trial/search command **before the first reference**, and freeze the protocol and guards again. Do not combine results from different shapes.

This selects the best **tested** configuration for one fixed workload, not a global optimum across all LTX-2.5 variants, shapes, or throughput scenarios. Full / one-stage / I2V require separate protocols; do not switch variants or step counts to meet this target.

## Parallel search space

Fix CFG=1 and Ring=1. Distilled uses positive-only guidance, so adding CFG ranks does not create actual CFG work partitions.

| TP | Ulysses | VAE tile degree | Search purpose |
| --- | --- | --- | --- |
| 1 | 4 | 1, 2, 4 | Primary SP path |
| 2 | 2 | 1, 2, 4 | Conditional TP/SP candidates; must complete three full quality validations |
| 4 | 1 | 1, 2, 4 | Conditional TP candidates; must complete three full quality validations |

`TP × Ulysses = 4`; VAE degree reuses the same worker WORLD and does not multiply the GPU count again. Each cell uses three trials with fresh servers. OOMs, process exits, quality failures, and source drift disqualify a cell from the best-configuration ranking. A single worker serves only as the canonical quality reference, not the 20% performance baseline.

## 1. Remote preparation

Use a Linux environment with CUDA / vLLM-Omni prepared and four exclusively allocated B300 GPUs. First check that `model_index.json` can be downloaded at the pinned revision. A 401/403 response blocks model access: the operator must log in locally with an authorized HF account or provide a complete local cache of that revision. Do not substitute another model within this protocol. The unsandboxed Codex invocation below requires an isolated container dedicated to this task; do not use bypass flags on a shared host.

```bash
export LAB=/work/ltx25-b300-rsi
export OMNI_PY=/path/to/prepared-omni-venv/bin/python
export CUDA_VISIBLE_DEVICES=0,1,2,3   # Replace with the allocated IDs/UUIDs
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$LAB"/artifacts "$LAB"/cache "$LAB"/guards
export HF_HOME="$LAB/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"

git clone --branch feat/cli-rsi-bootstrap https://github.com/david6666666/OmniRSI.git "$LAB/OmniRSI"
git clone https://github.com/vllm-project/vllm-omni.git "$LAB/baseline"
git -C "$LAB/baseline" fetch origin 2f289bb179d85671c116c10208b5c84b5c53f18f
git -C "$LAB/baseline" checkout --detach 2f289bb179d85671c116c10208b5c84b5c53f18f
git -C "$LAB/baseline" worktree add -b codex-ltx25-b300-20pct "$LAB/candidate" HEAD

"$OMNI_PY" -m pip install --no-deps "$LAB/OmniRSI"
command -v ffmpeg ffprobe codex
codex --version
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
nvidia-smi topo -m
"$OMNI_PY" -m omnirsi doctor --repo "$LAB/baseline" --repo-type vllm_omni \
  --backend cuda --device-model B300 --device-ids "$CUDA_VISIBLE_DEVICES" --python "$OMNI_PY"
```

`OMNI_PY` must already be able to run the target revision; it is not a separate CPU control environment. That source revision's installation instructions require the matching vLLM 0.31.0 source-wheel path, Diffusers 0.40.0, kernels 0.16.1, and the corresponding Transformers range. Follow the pinned source's CUDA installation documentation rather than guessing a Torch version. Preserve `pip freeze`, driver and cuDNN/NCCL versions, and topology.

```bash
"$OMNI_PY" -m pip freeze > "$LAB/artifacts/pip-freeze.txt"
"$OMNI_PY" - "$LAB/artifacts/model-index.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
from huggingface_hub import hf_hub_download
p = Path(hf_hub_download('Lightricks/LTX-2.5-Diffusers', 'model_index.json',
                        revision='a6de4b5354f078db24d9cf4778c14846788aea3d'))
content = p.read_bytes()
Path(sys.argv[1]).write_bytes(content)
print(json.dumps({'requested_revision': 'a6de4b5354f078db24d9cf4778c14846788aea3d',
                  'cached_path': str(p), 'sha256': hashlib.sha256(content).hexdigest(),
                  'class': json.loads(content).get('_class_name')}, indent=2))
PY
```

This HF pin comes from maintained upstream tests and must be downloaded and verified independently in the local environment. If the remote environment lacks access or assets, resolve loading and caching first; such failures are not parallel-configuration performance results. Verify that baseline and candidate imports resolve to their respective checkouts; the helper explicitly sets subprocess PYTHONPATH.

## 2. Freeze measurement and quality tools

```bash
cp "$LAB/OmniRSI/examples/ltx25_b300.py" "$LAB/guards/"
cp "$LAB/OmniRSI/examples/ltx25_quality.py" "$LAB/guards/"
sha256sum "$LAB/guards/"*.py > "$LAB/artifacts/guards.sha256"
chmod a-w "$LAB/guards/"*.py
export VALIDATOR_SHA=$(sha256sum "$LAB/guards/ltx25_quality.py" | awk '{print $1}')

"$OMNI_PY" "$LAB/guards/ltx25_b300.py" trial --dry-run \
  --source-repo "$LAB/baseline" --cache-root "$LAB/cache" \
  --tp 1 --ulysses 4 --vae 4 --output "$LAB/artifacts/dry-run/result.json"
```

The helper fixes the model revision, both sigma schedules, decoder, and codec parameters. It also freezes source-file hashes for recipe/guidance/denoise/decoder/model-extra/serving/export; optimizations must not modify these protected paths. Transformer, ops, attention, and distributed operators may be optimized while preserving semantics. Do not change guards, metrics, thresholds, reference outputs, precision, steps, frame counts, the model, or completed-output caching.

Keep GPU caches and artifacts outside the source checkout. Freeze HF assets/config as well, retaining actual cache snapshot/config hashes. Matching dependencies may be installed in a task-specific environment during preparation; after freezing, Codex must not modify the model or install dependencies. Each trial records before/after source fingerprints, package versions, the helper SHA, and every MP4 SHA. Preserve startup and failure logs.

## 3. Canonical single-worker reference and repeatability

```bash
"$OMNI_PY" "$LAB/guards/ltx25_b300.py" trial \
  --source-repo "$LAB/baseline" --cache-root "$LAB/cache" \
  --single-reference --tp 1 --ulysses 1 --vae 1 \
  --output "$LAB/artifacts/reference/result.json"

"$OMNI_PY" "$LAB/guards/ltx25_b300.py" trial \
  --source-repo "$LAB/baseline" --cache-root "$LAB/cache" \
  --single-reference --tp 1 --ulysses 1 --vae 1 \
  --output "$LAB/artifacts/reference-repeat/result.json"

"$OMNI_PY" "$LAB/guards/ltx25_quality.py" \
  --reference-manifest "$LAB/artifacts/reference/result.json" \
  --candidate-manifest "$LAB/artifacts/reference-repeat/result.json" \
  --min-ssim 0.99 --min-psnr 35 --max-audio-nrmse 0.01 \
  --expected-validator-sha "$VALIDATOR_SHA" \
  --output "$LAB/artifacts/reference-repeatability.json"
chmod -R a-w "$LAB/artifacts/reference"
```

First confirm that the reference is complete and repeatable. The quality policy is a conservative gate declared in advance for this experiment, not an official standard: per-frame SSIM≥0.99 and PSNR≥35dB; NRMSE≤0.01 for both 48kHz audio channels; matching output dimensions, actual frame count, FPS, A/V durations and start times, and complete decoding. Allow at most approximately two frames of latent-grid/codec padding; extremely short audio tracks must fail. This measures consistency relative to the reference, not absolute perceptual quality. Human viewing/listening and upstream quality suites are still required.

If reference repeatability fails, stop and report it. Do not relax thresholds after observing candidate gains.

## 4. Search and freeze the best four-worker configuration

```bash
"$OMNI_PY" "$LAB/guards/ltx25_b300.py" search \
  --source-repo "$LAB/baseline" --cache-root "$LAB/cache" \
  --reference-manifest "$LAB/artifacts/reference/result.json" \
  --quality-script "$LAB/guards/ltx25_quality.py" \
  --include-tp-candidates --repetitions 3 \
  --output-dir "$LAB/artifacts/parallel-search"

mapfile -t BEST < <("$OMNI_PY" - "$LAB/artifacts/parallel-search/best.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))['best']
for key in ('tp', 'ulysses', 'vae'):
    print(b[key])
PY
)
export BEST_TP=${BEST[0]} BEST_U=${BEST[1]} BEST_VAE=${BEST[2]}
export BEST_PARALLEL="$BEST_TP,$BEST_U,$BEST_VAE"
cat "$LAB/artifacts/parallel-search/best.json"
sha256sum "$LAB/artifacts/parallel-search/best.json" > "$LAB/artifacts/best.sha256"
```

The complete search is 9 cells × 3 trials, with 6 full-shape warmups + 3 timed requests per trial; budget resources in advance. Do not edit the baseline during measurement or run other measurements concurrently. An implemented TP path does not qualify this checkpoint: eligibility requires all repeated tests and A/V quality checks to pass. If no cell is eligible, do not produce a best configuration.

Retain every failure, all raw request latencies, quality reports, and source/device/cache data. Remeasure the selected winner instead of using the luckiest search sample as the final baseline.

## 5. Optimize the fixed winner with Codex

Export the existing methods first, then run the following Codex command in **an isolated container with GPUs exclusively allocated to this task**. This invokes the external Codex CLI on the remote machine; OmniRSI's `--agent codex` does not automatically start Codex.

To let Codex perform the complete measurement workflow, run this section after preparing the environment and guards in sections 1–2. The task prompt first completes any missing reference and parallel search, then reads the winner and begins optimization. Sections 3–4 also provide commands for manual execution.

```bash
"$OMNI_PY" -m omnirsi context --repo-type vllm_omni --backend cuda \
  --scenario diffusion.video_generation --limit 5 \
  --output "$LAB/artifacts/diffusion-context.md"

{
  printf 'Campaign root: %s\nPrepared interpreter: %s\nAllocated devices: %s\n' "$LAB" "$OMNI_PY" "$CUDA_VISIBLE_DEVICES"
  cat "$LAB/OmniRSI/docs/prompts/ltx25-b300-optimize.md"
} | codex exec -C "$LAB/candidate" --sandbox danger-full-access --json \
  --output-last-message "$LAB/artifacts/codex-final.md" - \
  > "$LAB/artifacts/codex-events.jsonl"
```

On a shared host, use interactive Codex with workspace-write and the required approvals; do not copy the unsandboxed mode directly. Model selection follows your Codex configuration. The task requires reading this plan, best.json, the frozen reference, and sourced knowledge; profiling first; proposing falsifiable hypotheses individually; limiting optimization scope; and retaining evidence of every failure.

## 6. Short-step diagnostics, layered iteration, and final 20% AB/BA acceptance

```bash
# Short-step diagnostic only; diagnostic records have no performance metric.
"$OMNI_PY" "$LAB/guards/ltx25_b300.py" trial --diagnostic --profile-stage1-steps 2 --profile-stage2-steps 1 \
  --source-repo "$LAB/baseline" --cache-root "$LAB/cache" \
  --tp "$BEST_TP" --ulysses "$BEST_U" --vae "$BEST_VAE" \
  --output "$LAB/artifacts/best-profile/result.json"
```

By default, diagnostics retain the same shape, audio, and decoder, but sample the two DiT sigma schedules down to 2+1 steps. Adjust them with `--profile-stage1-steps 1..8` and `--profile-stage2-steps 1..3`. Diagnostic warmups use the same short schedule. Diagnostic records have a separate protocol hash and `diagnostic=true`, omit `metrics`, and cannot serve as a reference, search winner, or accuracy/performance acceptance result. Formal measurements always use the full 8+3 steps. Add a full-schedule profile at the end if needed; profiling timings cannot be used for the 20% comparison.

After profiling, iterate by layer according to the evidence, changing one factor at a time:

1. Pipeline stages: distinguish the text encoder, both DiT stages, upsampler, Native DiffVAE, audio, and encoding/download. Protected paths remain off limits.
2. Distributed execution: analyze TP/SP communication, unoverlapped waits, copies, and layout transforms while keeping the winner tuple fixed.
3. Operators: analyze attention, GEMM/FFN, norm, RoPE, and modulation; prioritize eliminating repeated computation or fusing equivalent operators.
4. E2E: candidates must pass a complete A/V trial and quality gates before an independent five-group AB/BA run. Kernel gains do not establish E2E gains.

For every iteration, record the hypothesis, variable, fixed controls, profile evidence, diff, latency, quality, and acceptance/rejection reason. Retain failed iterations too. Add iteration charts and links to raw evidence to the PR comment. Without model/profile evidence, report preparation or blockage only; do not fabricate a performance curve.

Codex or the operator can run the commands below once candidate code is stable. Baseline and candidate use the same fixed winner, protocol, dependencies, and reference. `--agent codex` is only a handoff label.

```bash
BASELINE_CMD="$OMNI_PY $LAB/guards/ltx25_b300.py trial --source-repo $LAB/baseline --cache-root $LAB/cache --tp $BEST_TP --ulysses $BEST_U --vae $BEST_VAE --output {result}"
CANDIDATE_CMD="$OMNI_PY $LAB/guards/ltx25_b300.py trial --source-repo $LAB/candidate --cache-root $LAB/cache --tp $BEST_TP --ulysses $BEST_U --vae $BEST_VAE --output {result}"
QUALITY_CMD="$OMNI_PY $LAB/guards/ltx25_quality.py --reference-manifest $LAB/artifacts/reference/result.json --omnirsi-run --expected-parallel $BEST_PARALLEL --expected-validator-sha $VALIDATOR_SHA --min-ssim 0.99 --min-psnr 35 --max-audio-nrmse 0.01 --output {result}"

"$OMNI_PY" -m omnirsi run \
  --repo "$LAB/baseline" --candidate-repo "$LAB/candidate" \
  --repo-type vllm_omni --backend cuda --device-model B300 \
  --device-ids "$CUDA_VISIBLE_DEVICES" --python "$OMNI_PY" \
  --scenario diffusion.video_generation --mode code --agent codex \
  --model Lightricks/LTX-2.5-Diffusers --model-revision a6de4b5354f078db24d9cf4778c14846788aea3d \
  --workload-id ltx25-dd2-1280x704-f121-24fps-s8plus3-seeds42-44 \
  --baseline-command "$BASELINE_CMD" --candidate-command "$CANDIDATE_CMD" \
  --validation-command "$QUALITY_CMD" \
  --metric-key metrics.latency_ms --metric-unit ms --comparison-scope sync_video_audio_e2e \
  --direction minimize --repetitions 5 --min-improvement-pct 20 \
  --max-minutes 240 --output-dir "$LAB/artifacts/final-runs"
```

The `/work/...` paths above are assumed to contain no spaces. For other paths, quote paths inside the command strings according to argparse's quoted-argument rules. Each trial uses a fresh server and the same full-shape warmup, with alternating AB/BA measurements. Validation locates the current run through `OMNIRSI_RESULT_PATH` and checks **all baseline/candidate trials**, not just the final video.

Use five fresh baseline trials of the selected winner as `L0`, and five candidate trials as `L1`. Accept the 20% claim only when complete requests and source/guard/parallel/quality checks all pass, and `L1/L0≤0.80`. The first release reports descriptive medians/ranges, not statistical significance. A separate generalization check with prompts/seeds frozen in advance as a held-out set is recommended.

## Deliverables and failure handling

- Deliver every search cell, the winner, four-GPU topology, versions and source identities, frozen model/assets, per-request data, profiles, quality outputs, the HTML report, Codex JSONL, the candidate diff, and commits made with `git commit -s`.
- Do not meet the target by reducing steps, resolution, or frame count; disabling audio; switching decoder/variant; quantizing; caching completed outputs; or changing measurement/quality rules.
- Changes to protected semantics or dependencies fail the automatic gates; do not bypass them. Such changes require an independent protocol and semantic review and cannot inherit this 20% claim.
- Ctrl-C / timeout cleanup may terminate only servers/workers owned by this task. Inside OmniRSI, the helper inherits the trial process group; standalone execution uses a separate owned server group. Broad device-wide process termination is prohibited.
- Report a missed 20% target honestly. Stop if there is no valid best configuration. Missing evidence remains INCONCLUSIVE; do not fabricate verified performance.

## Pinned sources

- [LTX-2.5 recipe](https://github.com/vllm-project/vllm-omni/blob/2f289bb179d85671c116c10208b5c84b5c53f18f/recipes/LTX/LTX-2.5.md)
- [recipes/schedules](https://github.com/vllm-project/vllm-omni/blob/2f289bb179d85671c116c10208b5c84b5c53f18f/vllm_omni/diffusion/models/ltx2/ltx2_recipes.py)
- [TP implementation](https://github.com/vllm-project/vllm-omni/blob/2f289bb179d85671c116c10208b5c84b5c53f18f/vllm_omni/diffusion/models/ltx2/ltx2_transformer.py)
- [CUDA source installation](https://github.com/vllm-project/vllm-omni/blob/2f289bb179d85671c116c10208b5c84b5c53f18f/docs/getting_started/installation/gpu/cuda.inc.md)
- [Codex non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode); [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
