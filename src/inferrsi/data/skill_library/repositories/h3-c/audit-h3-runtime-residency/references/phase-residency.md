# Phase ownership and schedule-dependent state

All **CODE** observations below refer to the [pinned source readset](source-notes.md).
The ledger is for `h3_generate`, not a universal MiniMax-H3 implementation.
`h3_load_dir` inventories headers and probes Metal; it does not eagerly load
the complete pipeline. Its success cannot qualify the first generation peak.

## Phase ledger

| Phase / source owner | Weight and working-state lifetime | Host state crossing the boundary | Discriminating check / counter-signal |
| --- | --- | --- | --- |
| Metadata — `h3_load_dir`, `h3_weight_store_open` | Sorted component shards/header metadata; FL2VA required, optional Ref2VA checked by index presence | Context owns model path/inventory/device information | Check selected component paths and exact tensor schema; inventory is not payload SHA-256 or successful inference |
| Reference audio — `h3.c` reference loop, `h3_audio_vae_encode` | Input PCM enters its own audio GPU context; encoder operations free temporary tensors and cleanup on return | Packed normalized width-32 condition rows retained for DiT; original PCM and temporary latent freed | Measure input encoder separately; no audio reference means this peak is absent; standalone audio requires a visual reference in this public path |
| Reference images/video — `h3_video_vae_encode` | Input encoder loads its weights; spatial tiles run sequentially, then encoder cleanup | Tile latent arrays accumulate until stitched; packed video condition rows remain, source pixels remain for Qwen vision until consumed | Follow both tile-local and full host allocations; VAE input temporal compression is `ceil(T/4)`, not output decoder's temporal formula |
| Qwen vision — `h3_vision_encode_bf16` | 27 visual blocks load/run/free; local activation/work contexts freed at return | Merged visual features plus three deepstack arrays survive until language encoding; video uses sampled two-frame presentations | A video VAE latent is insufficient for the language path; token/vision geometry and tags must match presentation order |
| Qwen language — `text_encode` | Embedding plus current language-layer weights, shared activation arenas and a future-layer prefetch ring; completed layer weights retire after synchronous submit | BF16 host embedding (`tokens × 5120`) and optional tags; local GPU/store/activations freed at return | Runtime consumes 50 language layers; the complete official stored encoder inventory also contains unexecuted layers/buffers. Profile prefetch off versus a fixed depth to separate I/O latency from ring residency |
| DiT prepare — `load_dit`, `refine_text`, AdaLN precompute, `load_core` | Text refiner weights are temporary; schedule tables retained; active core weights resident or two streamed matrix slots; activation arenas and projection/row/RoPE maps retained | Host text and condition rows are freed after DiT has copied/prepared its inputs; optional conditioning cache retains copies | A lower denoise peak can coexist with an AdaLN setup or BF16-to-int8 conversion peak. Observe each load boundary |
| Joint denoise — `h3_dit_denoise_euler_preview` | Active DiT core, schedule/maps and activations; optional residual/velocity histories; preview adds a resident video decoder | Video/audio latents and optional preview RGB frame; preview callback data freed after callback | Both modalities use their own sigma deltas and independently seeded RNG instances. Same requested seed is not a single concatenated RNG stream |
| Audio output — `h3_audio_vae_decode` | Normally DiT already freed; decoder streams seven stages, frees each stage and cleans GPU/store at return | Video latent remains while host stereo PCM is produced; audio latent then freed | Prepared DiT retention or preview breaks the simple one-phase-at-a-time peak assumption |
| Video output — ordinary or resident decoder | Ordinary path cleans its VAE context; resident/preview decoder retains weights and activations until explicit free/cache clear | Complete F32 RGB output plus temporal overlap, later u8 RGB and waveform; generation cleanup frees these buffers after callbacks/media writing | Spatial/temporal tiling bounds compute tiles, not full RGB output. Check peak during conversion, resize and media writing as well as GPU execution |

**PROPOSED accounting:** build a timeline from actual overlapping owners.
Checkpoint bytes, logical elements, cumulative tensor allocation, live tensor
bytes, physical footprint, compression and swap are different quantities.
Unified-memory shared buffers are not an extra independent VRAM budget to add
again to RAM. File-backed pages can be reclaimable while still incurring faults,
I/O and pressure. The [header inventory](minimax-h3-weight-inventory.json) gives
stored components, not a sum of simultaneous allocations.

## AdaLN and prepared state

**CODE — precompute:** `prepare_rows` creates rows for each step's
`1 - sigma_video` and `1 - sigma_audio`; equality shares that step's row.
It adds visual/audio condition rows when present. Visual conditioning uses
0.999 and audio conditioning 1.0 until the corresponding target reaches that
boundary. Text uses the video time with per-token modality tags: ordinary text
1, vision presentation 0; audio rows use tag 2. `row_map` validates layout,
segment bounds and tag count before forming `time_row × 3 + modality`.

`h3_dit_schedule_precompute` loads each block's AdaLN weight/bias, computes the
BF16 output table, calls `h3_gpu_submit`, then frees that projection before the
next one. The final AdaLN projection follows the same pattern. It retains
tables rather than every large projection. All 50 block tables are initially
computed; gate-ranked layer selection then prunes inactive tables before core
loading. A layer reduction does not remove the initial precompute work.

**TEST-SOURCE:** `test_real_dit_schedule.c` uses the separate integer-grid
`h3_schedule_build(20)` and visual conditioning. It checks 40 time rows,
multimodal row-map entries, golden modulation error and 52 GPU submissions.
The generation path uses `h3_serving_schedule_build`; a test for the former
does not certify every serving schedule or audio-conditioned row map.

**PROPOSED invariant:** retained tables and maps require unchanged schedule
values/steps, condition presence, modality tags, layout and model numerics.
Recompute after changing any of these. The payload still includes the original
projection weights: releasing runtime projections does not reduce stored model
element counts or authenticate a converted export.

## Request and cache boundaries

**CODE:** caching is disabled by the library default and enabled by the
interactive CLI. `h3_ctx` owns three distinct retained products:

| Product | Inspected key/reset | Consequence |
| --- | --- | --- |
| Conditioning copies | Prompt and FL2VA/Ref2VA mode; when media present, render geometry/frame count/image-size mode plus ordered media kind/audio inclusion/path/size/mtime | Reuses host embeddings/tags and condition rows. Path metadata is not a content hash; external file replacement preserving metadata is a counterexample to treating this as integrity proof |
| Prepared DiT | Conditioning key, render shape, steps, active layers, core reuse, token reduction, row-FC2, reference RoPE, SSD and named slower-path flags | A matching key reuses schedule/maps/weights/activations. `h3_dit_reset_run` refreshes condition rows and clears core-forward/residual readiness. Seed and whole-velocity reuse are per-run inputs, not schedule-construction inputs |
| Resident video decoder | VAE directory plus latent height/width | Retains decode weights/workspace across requests; duration still affects returned RGB host allocation |

Mismatched prepared/decoder keys free the old object. `h3_cache_clear` frees all
three products; disabling the cache calls it. A denoise failure invalidates a
cached DiT before cleanup. This bounded read does not prove universal exception
cleanup, concurrent-call safety or key completeness.

Environment-controlled numerical/kernel choices are not all encoded in those
keys. **PROPOSED:** start a fresh process or explicitly clear the cache when
changing environment diagnostics, weight bytes or source implementation. Never
use a cache hit as evidence that newly requested precision was selected.

## Temporal and output contracts

**CODE:** output frame alignment rounds upward to `5 + 17k`; video output
latent time is `2 + 5k`, while reference-video input compression is `ceil(T/4)`.
Generation further requires at least a trained 22-frame decoder chunk. The
resident decoder requires latent time at least 7 with `(T - 2) % 5 == 0` and
returns `(T - 2)/5 × 17 + 5` frames, blending five overlapping frames between
chunks. Its host `final_rgb` spans the complete output even when chunks run
sequentially. Final frame callbacks run after this full decode and RGB conversion;
their buffers are borrowed for the call. `h3_result` contains generation metadata,
not retained RGB/PCM. Do not advertise constant total memory with duration.

Keep requested frames, aligned output frames, reference frames, latent geometry,
internal/output canvas and media duration distinct in the RunSpec. A lower
internal canvas plus upscale, a changed RoPE grid or omitted audio modifies the
workload/quality contract; it cannot silently rescue a fit or speed claim.
