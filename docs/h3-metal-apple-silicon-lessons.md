# h3-metal · MiniMax-H3 on Apple silicon: lessons

**Showcase engine result: a warm 768x448, 49-frame FastH3 clip takes 18.20 s on
one M5 Max (128 GB), 7.40× the MLX port and 4.03× upstream h3.c.** This is
same-prompt warm inference in one process, measured by the engine maintainers;
it is not an InferRSI acceptance result and has no acceptance issue.

[h3-metal](https://github.com/zuiho-kai/h3-metal) is a C/Metal engine derived
from [antirez/h3.c](https://github.com/antirez/h3.c). It was tuned with the
InferRSI method: gates frozen before the run, interleaved A/B timing and
model-proposed patches. This page records what that work taught, including the
directions that failed. Each row keeps observation, cause, action and source
apart.

## Sources and labels

| Label | Meaning |
| --- | --- |
| **public** | Number or behavior is in the h3-metal repository at the pinned commit. |
| **ledger** | From the maintainers' unpublished run ledger; not reproducible from this page. |
| **unverified** | Analysis or estimate reported during the work and not re-measured. |

Pinned h3-metal commits:
[`64ea9c9`](https://github.com/zuiho-kai/h3-metal/commit/64ea9c9ea7783d3ea2744b790a6c5c0806a5af91) first release ·
[`9186baa`](https://github.com/zuiho-kai/h3-metal/commit/9186baa04820a7991da07c6a51d65dffd1ba0e60) loop champion ·
[`8b06a20`](https://github.com/zuiho-kai/h3-metal/commit/8b06a208e8106be9c78f58e6a9416ad65e3aa50d) 20-step re-measure ·
[`dd82d1f`](https://github.com/zuiho-kai/h3-metal/commit/dd82d1fae4814c76a3a29f13d56cb08a7bc6bbd6) memory tiers ·
[`0874042`](https://github.com/zuiho-kai/h3-metal/commit/0874042579f74a4e9ebbaef0056495d5e92322e4) BF16 decoder in published commands.

Reference condition for every number unless stated: 768x448, 49 frames,
seed 0, real weights, one engine at a time, Apple M5 Max (40-core GPU), 128 GB.

## Results and scope (public)

| Engine | Steps | Cold | Warm |
| --- | ---: | ---: | ---: |
| MLX port, 4-bit | 20 | 153.1 s | 134.6 s |
| upstream h3.c, default preset | 20 | 67.6 s | 73.3 s |
| h3-metal, original H3 | 20 | 54.29 s | 29.89 s |
| h3-metal, FastH3 4-step + block-sparse attention | 4 | 48.23 s | 18.20 s |

Cold is the first clip in a fresh process. Warm is a later clip in the same
process: the mean of clips 2–4 for 20-step rows, the mean of two A/B/B/A warm
runs for the FastH3 row. The FastH3 row uses a 4-step distilled checkpoint, so
its speedup mixes algorithm and engine gains.

## Measurement lessons

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| The published quick-start command ran a warm FastH3 clip in about 30 s; the performance table said 18 s. | The table script set `H3_VAE_BF16=1` (BF16 video decoder); the README commands did not. Quiet re-measure: without it 51.6 s first / 30.4 s warm, with it 42.0 s / 17.0 s. | Diff the exact environment and flags of every published command against the benchmark script. | public (`0874042`) |
| Warm time for a **new** prompt was about 27.7 s against 17.4 s for the same prompt. | The text encoder rereads about 62 GB of weights per new prompt; same-prompt warm hits the conditioning cache. | Report same-prompt and new-prompt warm separately; the headline is same-prompt. | unverified |
| Keeping the text encoder resident made a new-prompt warm clip 2.6 s faster but cold start 3.6 s slower. | About 47 GB more resident memory evicted the DiT from the page cache. | Not made default; a trade-off belongs to a named profile, not the engine default. | ledger |
| Cold minus warm was dominated by about 23 s of DiT loading. | Page-fault overhead, not disk throughput. | Prefetch and parallel reads were tried, gave no gain and were reverted. | ledger |
| A loop candidate was promoted at about 1.3 s faster (champion 19.09 / 20.03 s, candidate 17.86 / 18.61 s) while both passes were flagged busy. | A shared headless browser held about 1.75 CPU cores during timing. | Re-measured on a quiet machine before publishing: old champion 19.54 s, new 18.20 s mean warm. The README compares 18.20 s with the earlier 18.55 s release figure. | ledger, public (`9186baa`) |
| A combined candidate was 0.135 s faster on average, yet an untouched stage (audio VAE) was 0.94 s slower. | Background CPU load from a browser and a search process. | Rule: if a stage the patch did not touch slows down clearly, mark the trial interfered and re-run when idle. | ledger |
| An A/B run during a large weight download slowed every pass (one champion pass to 56 s) and changed champion output hashes. | I/O and memory pressure from the download. | Run voided; downloads and GPU timing never overlap. | ledger |
| The pre-timing idle check reported "GPU busy" and aborted a valid run. | A broad process match on `h3` caught an unrelated agent session. | Match exact benchmark binary names. | ledger |
| A candidate's frame hash "differed" from the champion. | The reference hash came from profiling mode, which changes command submission. | Compare hashes only between runs in the same mode; the candidate matched normal-mode champion output. | ledger |
| Same settings in different processes gave slightly different outputs. | Not established. | Before a decoder quality comparison, freeze the decoder input and run the decoder alone. | unverified |

## What made it fast (public unless marked)

- **Fewer steps.** The FastH3 4-step distilled DiT loads into the same kernels
  through a tensor-layout map. Blind visual review placed the first FastH3 clip
  below the 20-step champion (ledger); the README labels steps per row.
- **Block-sparse attention on the GPU.** Coarse tile scores keep the top 12 of
  120 video tiles per query tile. Warm 20.32 → 18.55 s; four sampled frames
  showed no artifacts.
- **BF16 video decoder.** Decoder 19.9 → 9.6 s at the reference shape (ledger);
  real-weight check: mean PSNR 65.1 dB, worst frame 64.7 dB, max pixel error
  4/255 (ledger). Warm FastH3 30 → 17 s (public).
- **Loop champion `9186baa`.** VAE projections skip an F32↔BF16 round trip and
  FC2 uses row-wise int8: warm 18.55 → 18.20 s.
- **One process, one Metal command stream**, with text conditioning, prepared
  DiT and decoder resident across clips.

## Rejected directions

| Direction | Recorded observation and disposition | Revisit condition |
| --- | --- | --- |
| Hand-written BF16 flash attention | 27.4 ms against MPSGraph SDPA 18.0 ms, which is already 92% of the BF16 bound. DiT linear layers measured at 85–99% of the 119.3 TOPS int8 / 61.6 TFLOPS BF16 peak. Kernel-level work stopped; effort moved to step count. | A new hardware generation or a shape where SDPA falls well below its bound. |
| Driver-level tweaks: wait only on the last command buffer; WriteCombined CPU-filled buffers | Both inside the single-pass noise (about 1.5 s); zero gain. | Only with a profile that shows CPU–GPU sync or upload on the critical path. |
| Larger VAE tiles (448/512) | About 0.65 s faster but changed output. Not adopted. | Needs its own quality gate. |
| BF16 video VAE weights converted once and kept resident | VAE tensor peak 9.51 → 4.95 GiB, warm time unchanged. Kept as a memory option, not a speed change. | Useful for small-memory configurations. |
| `--ssd-streaming` with FastH3 | Same peak and time as without it. | The 4-step path does not use the streamed DiT. |
| Text encoder resident by default | See measurement lessons; cold start regressed. | Interactive multi-prompt sessions only. |

## Memory tiers (public, `dd82d1f`, `0874042`)

Process peak measured with `/usr/bin/time -l` (peak memory footprint) on the
128 GB machine, one cold clip:

| Setup | Peak | Time |
| --- | ---: | ---: |
| FastH3 + row-wise int8 FC2 | 22.9 GB | 51 s |
| FastH3, interactive session, two clips | 35.1 GB | 42 s, then 17 s |
| Original H3, SSD streaming, 640x384, 33 frames | 10.6 GB | 77 s |

The 16–24, 32–36 and 48+ GB tiers are inferred from these peaks; they were not
run on smaller Macs. The floor is the video decoder at 9.37 GiB, which does not
shrink with resolution, so 8 GB machines are out of reach without a smaller
decoder footprint. The BF16 decoder adds about 3 GB of peak, so the smallest
tier leaves it off.

## Search-loop lessons (ledger)

The unattended loop proposed a patch, compiled it in a sandbox, timed it in
A/B/B/A and promoted only on a warm gain of at least 1 s.

- **Most early rounds died before timing.** In one run 32 of 41 rounds failed at
  the proposal stage: empty edit lists, edit anchors that matched zero or
  several places, and malformed JSON. Fixing exactly those three classes cut the
  proposal failure rate from 75% to 10% over later runs.
- **Proposals that compile are not proposals that help.** After the fix,
  candidates compiled but gained at most about 0.1 s. Model-estimated savings
  did not match measurements; one candidate inflated its estimate by citing
  kernels it did not change. Cap an estimate at the measured time of the
  functions the patch actually edits.
- **Self-added rules can conflict.** "Change direction after four stalled
  rounds" and "only edit the slowest stage" together rejected every candidate.
- **Pre-build every pipeline.** A candidate exceeded the 32 KB threadgroup
  memory limit (42,240 bytes) and failed at runtime. Building all Metal
  pipelines in the sandbox before timing records it as a build failure instead.
- **Test sandbox rules under the real sandbox.** A `sandbox-exec` profile regex
  using `{6}` was accepted silently but never matched, so session directories
  were never created.
- **One step per task.** A single agent task that bundled proposal, ledger,
  quality gate and timing timed out at 10 minutes with nothing kept.
- **Read the stage profile first.** Proposals written against total time alone
  guessed wrong; per-kernel timing of the top stages made proposals checkable.

## Limitations

- One machine, one prompt family and seed; no service load, tail latency or
  concurrency.
- Ledger and unverified rows cannot be reproduced from public artifacts.
- Quality checks were output hashes, frame/duration matching, PSNR on the decoder
  and a blind visual review; no full video-quality benchmark.
- Tiers below 128 GB are inferred, not measured on those machines.
