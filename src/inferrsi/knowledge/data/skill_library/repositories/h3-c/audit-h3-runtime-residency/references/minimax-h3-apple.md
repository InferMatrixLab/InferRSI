# Worked preparation: MiniMax-H3 on a 64 GiB Apple Silicon target

Source observation date: **2026-10-23**. This is source-derived research and
metadata inspection, with **target execution, peak memory and joint media
quality unverified**. No model payload was downloaded or run. The caller's
"M5 Mac Studio 64 GB" label is treated as a 64 GiB planning budget; inspect the
actual chip, installed bytes, usable budget, OS and toolchain before acceptance.
This example does not assert availability of a particular Apple configuration.

The comparison and header observations below are retained from InferRSI
`f804ec1503e977787c572d5d27d1f3258017b01f`; their HTTP ranges and popularity/card
lookups were not rerun during this source distillation. The new
[h3.c source audit](../SKILL.md) supplies the separate runtime mechanisms,
readset and verification recipe. No model payload is bundled.

## Identify and discover

H3-Base is joint video/audio diffusion conditioned by a Qwen3-VL encoder, with
separate visual and audio VAEs. FL2VA and Ref2VA are alternative task checkpoints.
Image/video conditioning also needs the visual encoder and VAE input paths;
audio references need audio encoding. The hosted Context-IR and 2K regeneration
stages are not locally released in this snapshot. These distinctions come from
the [official architecture and release layout](https://github.com/MiniMax-AI/MiniMax-H3/blob/d21241f0a4b3acbb34c97dae47fa417b7065e438/README.md).

Use independent catalog queries rather than requiring all these words in one
record:

```bash
inferrsi knowledge search MiniMax-H3 --repo-type inferrsi --limit 100
inferrsi knowledge search diffusion --repo-type vllm_omni --limit 100
inferrsi knowledge search MLX --repo-type inferrsi --limit 100
inferrsi read inferrsi.common.skills.audit_h3_runtime_residency --material
```

The first query locates this registered repository skill; the other queries
expose independently sourced mechanisms that need not name both H3 and MLX.
Leaving backend filters unset permits cross-backend discovery, not automatic
transfer. Inspect each result's source, backend, applicability and unverified
state. Narrow filters only for an intentional scope; catalog absence is not
lack of upstream support.

For a legacy cited export, its existing required flags still apply:

```bash
inferrsi context diffusion --repo-type vllm_omni --backend cpu --scenario diffusion.video_generation
```

The `cpu` filter retrieves common guidance here; it does not qualify an Apple
accelerator. To read this packaged example outside the checkout:

```python
from importlib.resources import files

owner = files("inferrsi").joinpath(
    "data/skill_library/repositories/h3-c/audit-h3-runtime-residency"
)
print(owner.joinpath("references/minimax-h3-apple.md").read_text(encoding="utf-8"))
```

## Select an implementation reference

The bounded comparison covers three inspected source engines that execute H3 on
Apple Silicon, including C/Metal as well as MLX. Counts were read from each
repository's GitHub API on the observation date; they are popularity snapshots,
not compatibility or quality scores. Wrappers, hosted API clients and unrelated
repositories are outside this set.

| Candidate and pinned source | Stars | Reference considerations |
| --- | ---: | --- |
| [antirez/h3.c](https://github.com/antirez/h3.c/tree/8974cc055ea9c02fcd14cc27dfda3e1027c05153) | 2,946 | Native C/Metal; MIT code; selected as the implementation reference within this set |
| [PipeNetwork/minimax-h3-mlx](https://github.com/PipeNetwork/minimax-h3-mlx/tree/b2f7e4d2b7861cefe68b75e4b59ab81cc4e7c318) | 87 | MLX; Apache-2.0 code; useful quantization and full-pipeline parity readset |
| [appautomaton/mlx-h3](https://github.com/appautomaton/mlx-h3/tree/adee6a39f8d0dc639e6c5e371fdafb7ef19e4dad) | 34 | MLX phase residency and full runtime bundle; GitHub license API unknown at this pin, while the model card describes runtime code as MIT; verify code license before reuse |

Star observation endpoints: [h3.c](https://api.github.com/repos/antirez/h3.c),
[PipeNetwork](https://api.github.com/repos/PipeNetwork/minimax-h3-mlx),
[appautomaton](https://api.github.com/repos/appautomaton/mlx-h3).
This establishes the largest count among these candidates, not a global maximum.

For dedicated-engine generation, read the [pinned source mechanisms](source-notes.md),
[phase ledger](phase-residency.md), [numerical/SSD contracts](precision-and-streaming.md)
and [verification recipe](validation.md). These distill loaders, input/output
components, schedule precompute, caching, kernels and tests directly from the
selected h3.c tree. Manual source reading installs no distillation tool and
establishes no AREX/DisCo execution or empirical skill efficacy.

## Count all selected weights

The [header inventory](minimax-h3-weight-inventory.json) records exact source
revisions, selected paths, header SHA-256 values, dtype/packing accounting and
aggregate file bytes. HTTP ranges read only safetensors lengths and JSON headers;
payload integrity and trained-parameter counts were not verified. The values
below are **logical stored tensor elements**, including buffers. MLX packed
8-bit `U32` weights count four logical elements per packed element; companion
quant scales/biases are excluded from that logical count but included in bytes.

| Component | Complete official FL2VA, billion elements | Selected appautomaton export, billion elements | Selected export weight-file GiB |
| --- | ---: | ---: | ---: |
| One DiT | 33.122993 | 33.122993 | 34.756 |
| Qwen3-VL language + vision encoder | 33.357390 | 25.753096 | 27.730 |
| Video VAE, input encoder + decoder | 2.603871 | 2.603871 | 4.850 |
| Audio VAE, input encoder + decoder | 0.151327 | 0.151287 | 0.564 |
| **Selected weight total** | **69.235581** | **61.631247** | **67.899** |

The official selected weight files total **144,016,376,436 bytes** (134.126 GiB),
with its full encoder and F32 video VAE. The selected mixed export totals
**72,905,799,600 bytes** before tokenizer/configs. The export retains language
layers 0–49 and visual tensors; full versus truncated encoders and repacked
VAE/buffer inventories explain the different totals. These are concrete source
inventories, not an assumed "at least 70B" constant or a 33B whole-pipeline model.
Reinspect any different checkpoint/export/conditioning mode.

The [export's weight procedure](https://github.com/appautomaton/mlx-h3/blob/adee6a39f8d0dc639e6c5e371fdafb7ef19e4dad/docs/weights.md)
defines one selected DiT, phase release, dense VAEs, quantization exceptions and
AdaLN precompute. Do not add the alternative Ref2VA DiT, repeated shared copies,
BF16 conversion sources or unselected adapters to one request. Conversely, keep
the selected visual tower, both VAE input/output paths and any selected adapter
in the appropriate conditioning/decoding phase. AdaLN schedule precompute can
release roughly 13B DiT elements after building tables; it reduces execution
residency without changing the original checkpoint total.

## Compare compatible engine/weight pairs

| Pair | Coverage and memory evidence | Decision for the target |
| --- | --- | --- |
| h3.c + official mixed BF16/F32 weights | Pinned loader checks names/shapes/dtypes; phase-scoped loading and optional SSD streaming. Its author reports about 40.1 GB physical peak and zero swap for two bounded reference-media workloads on a **128 GB M5 Max** | Preferred source reference. A controlled 64 GiB trial is plausible, but workload, physical peak, speed and quality require target validation |
| appautomaton/mlx-h3 + [full mixed 8-bit bundle](https://huggingface.co/appautomaton/minimax-h3-base-8bit-mlx/blob/9a08116a349ab469b097775b5a483affcb5ccd34/README.md) | DiT + truncated language/vision encoder + both dense VAEs + tokenizer; one DiT selected. Models are released between phases. Default active-memory guard is **70 GiB**, above the requested budget | Not an accepted 64 GiB configuration. Measure a lower explicit budget and each phase; experimental M5 W8A8 requires separate quality validation |
| PipeNetwork MLX + [4-bit DiT](https://huggingface.co/pipenetwork/MiniMax-H3-MLX-4bit/blob/95a0e7d97f23f8b0029afea9411f13535262d935/README.md) or [8-bit DiT](https://huggingface.co/pipenetwork/MiniMax-H3-MLX-8bit/blob/e55f97c8ebf340066de8d6b4554a2a6767fe54e9/README.md) | **Transformer only**. Author reports 25.3/35.3 GB disk and 11.5/21.5 GB retained DiT residency, plus schedule tables; text encoder, VAEs and working memory remain additional | Useful lower-residency candidates after completing the pipeline inventory. Keep 4-bit and 8-bit as separate quality candidates |
| Pinned PipeNetwork runtime + patches + [MrMofer full 8-bit pipeline](https://huggingface.co/MrMofer/MiniMax-H3-MLX-8bit/blob/166a35fea1e83203a438ba9517aef89ea9fe04f0/README.md) | Includes language/vision encoder, DiT, VAEs, processors/configs and optional LoRA. Card pins base `b2f7e4d2` plus patch `7210b93e6df86bf9c7206091c9542b6983c10c30`; reports M4 Max "68.7 GB", release-encoder behavior, and workload-dependent RSS/compression | An additional complete-package candidate, not an M5 result. 68.7 decimal GB is approximately 64 GiB; resolve units and reproduce the exact patch/conditioning path rather than assuming a larger machine or a portable result |

These pairs cannot be mixed arbitrarily. [h3.c's loader](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_weights.c)
does not establish support for MLX affine packed weights. Engine code licenses
also do not replace the upstream model/weight licenses; inspect the pinned cards
and notices before reuse.

Keep precision and workload changes visible. The
[h3.c defaults and diagnostics](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/README.md)
include M5 int8 paths, layer reduction/velocity reuse presets and a faster output
head. Restoring 50 layers and `--reuse 1` alone does not establish a BF16 oracle;
inspect its slower BF16 controls and F32-head diagnostic for the frozen comparison.
Its roughly 2 GiB SSD figure describes tracked DiT storage, not total RAM, and
preview decoding adds roughly 10 GiB. The
[PipeNetwork quant evaluation](https://github.com/PipeNetwork/minimax-h3-mlx/blob/b2f7e4d2b7861cefe68b75e4b59ab81cc4e7c318/README.md#published-quants)
reports materially different 4/8-bit velocity errors and a failed lower-bit
candidate; inspect complete audio/video outputs as well as operator metrics.

## Conditional feasibility and next handoff

The unphased official stored tensors exceed 64 GiB before activations. The
selected 8-bit files also exceed it on disk, but neither total is simultaneous
residency. Phased release, exact schedule precompute, supported quantization and
SSD streaming make 64 GiB worth a bounded trial; available evidence does not
establish it as supported. OS/display memory, allocator/workspace, conditioning
references, VAE decode, resolution/duration and swap can decide the outcome.

For predictable headroom, investigate a **96/128 GiB-class** memory budget,
subject to actual available hardware; the cited h3.c M5 report used 128 GB.
That is a planning option, not a proven minimum or a guarantee of native-resolution
quality or latency. If 64 GiB is fixed, prepare a phase/peak measurement with an
explicit workload, no preview, supported streaming/quantization, and fail/stop
conditions for swap or memory pressure. Do not quietly reduce layers, steps,
resolution or quality to claim a fit.

The next engine-generation handoff must carry the selected source/weight pins,
complete component and format inventory, conditioning mode, OS/toolchain,
physical/tensor/compressed memory metrics, SSD requirements, exact/approximate
controls, frozen quality/performance gates and remaining unsupported/unverified
features. Freeze these in the acceptance issue/evidence, then run required
operator, full joint audio/video and end-to-end checks. All target conclusions
remain unverified until that evidence exists.
