# Verification recipe and current limits

This candidate has source/metadata/package validation only. Native h3.c, Metal,
model quality, storage overlap and target memory/performance checks are
**not_run**. The [readset](source-notes.md) distinguishes inspected code,
unexecuted assertions, imported observations and proposed checks. None is a
campaign PASS or proof this skill improves downstream agent behavior.

## Before a native run

Use the pinned source and the selected model/task checkpoint. Record model
payload SHA-256 values, tokenizer/configs, exact macOS/SDK/clang/Metal/FFmpeg
stack and actual chip/memory; headers alone cannot authenticate payloads.
Inspect upstream commands before execution. The Makefile links Apple
Foundation, Metal, MPS/MPSGraph and Accelerate; a Windows/Python catalog test
cannot substitute for those paths. External weights and `misc/fixtures/`
goldens are not supplied by this skill or guaranteed to exist in the Git tree.

Freeze scenario inputs, aligned geometry, numerical controls and acceptance
gates before candidate testing. Use matching reference and candidate runs.
Keep startup, preparation, cold request and warm requests separate, and retain
all unsuccessful/slow trials. Do not import upstream test tolerances as new
campaign-wide quality or performance gates.

## Inspected native checks

| Target / source | Actual assertion scope | Prerequisites and gap |
| --- | --- | --- |
| `make test` → `h3_tests`, `tests/test_h3.c` | Host temporal/canvas/sigma/layout/RNG/solver/row conversion, safetensors and Metal probe checks | Entire executable still links Apple frameworks; it does not prove complete model output or capacity |
| `make parity` → `h3_metal_tests`, `h3_bf16_tests`, `h3_text_tests` | Toy block/text fixture comparison; BF16 tests include exact token pooling/expansion, gate/AdaLN and final-head fusion comparisons | MLX-derived toy fixtures required. It is a subset, not full-model parity. Presence of `memcmp` assertions is TEST-SOURCE, not execution |
| `make real-parity` | Real prompt layer-50 output and one real DiT block versus golden tensors | Released weights and specific MLX goldens required; one block is not a complete denoise trajectory |
| `h3_real_dit_schedule_test` | Selected 20-step schedule row map, modulation tolerance and 52 submissions preserving sequential projection release | Build target is separate from the default `make test`; tested builder is `h3_schedule_build`, not automatically every serving schedule/audio-conditioned path |
| `h3_real_qwen_vision_test`, `h3_real_multimodal_text_test`, `h3_real_ref_video_text_test`, `h3_real_video_encoder_test`, `h3_real_audio_encoder_test` | Selected visual, multimodal presentation, reference video and input-encoder fixtures | FL2VA/Ref2VA paths and geometry differ; include each conditioning mode in the claimed scope |
| `h3_real_audio_vae_test`, `h3_real_video_vae_test`, `h3_semantic_dit_test`, `h3_semantic_vae_test` | Audio/video component outputs or selected complete denoise/decoded tensors versus goldens | Full model and external fixtures; semantic VAE `--resident-preview` checks representative preview and resident final decode byte equality against ordinary decode on its fixture |
| `h3_dit_bench`, `h3_dit_bench_864` | Fixed synthetic/model forward shapes and optional A/B controls; `H3_BENCH_ALL_BF16`, `H3_BENCH_SSD_STREAMING`, `H3_BENCH_LAYERS` wire load policy | Not service latency or real media-quality validation. Inspect each A/B's effective flags; head precision remains separately controlled |

The Makefile conditionally skips missing toy/tokenizer/model/FFmpeg fixtures in
`make test`; `make parity` and `make real-parity` invoke their named fixtures
directly. Capture passed, failed and skipped targets individually. A successful
top-level command containing skips does not establish those absent checks.

## Smallest discriminating probes (PROPOSED)

| Signal | Fixed controls and intervention | Observable falsifier / next decision |
| --- | --- | --- |
| Fails during prompt encoding | Identical prompt/media and model; compare synchronous Qwen reads with one fixed prefetch depth, then restore before another variable | If the peak remains in another phase, ring depth is not the cause. Compare physical peak and time, not worker count alone |
| Claimed AdaLN memory saving | Trace projection load → submit/fence → free for each block; compare golden row maps/modulation and table bytes for the exact schedule | Multiple live large projections, stale condition rows or incorrect output rejects the change; small table bytes alone prove neither |
| DiT fits but decode fails | Disable preview/interactive retention; keep geometry/precision unchanged; observe DiT release and VAE/host-RGB allocations | If failure persists solely inside decode, further DiT quantization does not address the peak. Qualify tiling/chunking without dropping output frames |
| Repeated request appears to leak | Same key request, then changed shape/media/precision and explicit cache clear/fresh process; record object/tensor/physical lifetimes | A stable deliberate cache plateau differs from growth after clear. File metadata keys cannot detect adversarial same-size/mtime media replacement |
| SSD saves tensor bytes but is slow | Resident BF16 versus streamed BF16, same head/shape/layers/schedule/outputs and controlled storage cache state | Collect output parity, total reads, throughput, unhidden wait and full phase wall time. Default int8 versus SSD confounds precision; join wait is not total runtime |
| Fusion claims exactness | Hold quantization and arithmetic path fixed; compare byte-level intermediate/output tensors against the corresponding unfused path on boundary shapes/tails | BF16 rounding/order/layout changes reject exactness even if average error is small. Follow successful operator checks with complete model outputs |
| Int8/reuse/layer/canvas change looks good on one frame | Freeze a complete joint audio/video protocol including motion, synchronization, reference preservation and multiple relevant seeds/prompts | Good still-frame appearance or velocity similarity cannot falsify audio/motion drift. Retain upstream rejected combinations as conditional leads |

For a memory-constrained target, freeze explicit pressure/swap/stop conditions
and track phase-level physical footprint, compression, swap, tensor bytes and
media-buffer lifetime. No-preview SSD mode is one candidate, not a guaranteed
64 GiB recipe. Do not quietly alter layers, duration, resolution, steps or audio
to report a fit. The imported [Apple comparison](minimax-h3-apple.md) preserves
why available upstream evidence leaves that target unqualified.

## Skill and package delivery

Use the existing readers independently of any research-preparation extension:

```bash
inferrsi knowledge search MiniMax-H3 --repo-type inferrsi --limit 100
inferrsi skills show audit-h3-runtime-residency
inferrsi skills resource audit-h3-runtime-residency references/phase-residency.md
inferrsi read inferrsi.common.skills.audit_h3_runtime_residency --material
```

`skills` commands require the optional YAML parser; core `read` and catalog
discovery do not. Delivery checks should verify typed source/candidate metadata,
registered discovery, complete owner resource closure, exact retained inventory
arithmetic/digests and noneditable-wheel access without importing an inference
framework. They verify package behavior and source bookkeeping only.

A future behavioral skill evaluation is separate: give an independent reader a
realistic memory-fit/precision request and permitted raw artifacts, inspect its
actual component ledger, compatible engine/format choice and proposed check,
and retain counterexamples. No No-Skill-versus-Skill comparison or empirical
efficacy result has been performed in this source distillation.
