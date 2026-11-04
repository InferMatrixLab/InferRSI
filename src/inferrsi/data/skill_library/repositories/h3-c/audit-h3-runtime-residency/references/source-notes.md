# Pinned h3.c source and construction scope

Repository: [antirez/h3.c](https://github.com/antirez/h3.c/tree/8974cc055ea9c02fcd14cc27dfda3e1027c05153).
Revision: `8974cc055ea9c02fcd14cc27dfda3e1027c05153`, inspected 2026-10-23
from a detached Git checkout. [Source identity](source-identity.json) records
Git blob IDs, byte counts and SHA-256 values for the bounded readset. Those are
source-byte checks, not executed model or kernel checks. Unlisted code and
dependencies are outside this audit.

The root [MIT license](../LICENSE) attributes Salvatore Sanfilippo. The retained
[third-party notice](THIRD_PARTY_NOTICES.md) covers ccv-derived Morton/int8
TensorOps design under BSD-3-Clause. No upstream implementation code is bundled.
Engine licenses do not establish licenses for model weights, FFmpeg builds or
comparison-engine/model exports; inspect those independently.

Evidence classes: **CODE** is an inspected source contract; **TEST-SOURCE** is an
unexecuted native assertion; **UPSTREAM-REPORT** is an author's result;
**PROPOSED** is a diagnostic or transfer check. No AREX/DisCo distillation run,
native build, model payload validation, media-generation evaluation or local
performance measurement occurred. This is manual source-anchored, capability-
specific distillation informed by InferRSI's existing Repo-To-Skill ledger for
[Repo-To-Skill v1](https://arxiv.org/abs/2609.02749v1), not a reproduction of its
construction system or benchmark gains.

## Readset and architecture

Ranges below identify the inspected slice, rather than claiming every file was
read end to end. Source links use the immutable revision. Detailed mechanisms
and their verification recipes live in the linked owner-local resources.

| Source | Inspected scope | Extracted decision |
| --- | --- | --- |
| [h3.h](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3.h#L65-L189), `h3_internal.h`, [h3.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3.c#L407-L477) | Public parameters/cache/result ownership; context cache fields; `h3_load_dir`, `h3_free` | Metadata inventory/Metal probe precedes model loading; request defaults and cache retention are separate |
| [h3.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3.c#L848-L1725) | `h3_generate` component selection, reference preparation and phase transitions; cache keys/clear at 31–192; selected parameter guards at 480–627 | [Phase ledger and dependency-complete reuse audit](phase-residency.md); optional Ref2VA, preview and retained DiT change capacity |
| [h3_weights.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_weights.c), `h3_weights.h`; [h3_safetensors.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_safetensors.c#L183-L440) | Weight-store implementation and public contract; selected dtype, shape, byte-range and header validation | Exact raw BF16/F32 schema; header reading does not verify payload integrity or decode MLX affine packing |
| [h3_host.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_host.c#L15-L44) | Frame/latent formulas; separate schedules at 129–164; layout-builder symbols and solver entry points | Requested/output/reference temporal geometry is distinct; match schedule builder before parity |
| [h3_text_encoder.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_text_encoder.c#L124-L393) | Geometry at 12–26; streamed layer load, prefetch allocation/read/join and 648–779 execution/cleanup | Fifty language layers, per-layer release and future-layer ring; I/O-worker count is not ring depth |
| [h3_vision_encoder.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_vision_encoder.c#L425-L631), [h3_multimodal.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_multimodal.c#L130-L340) | Patch geometry/constants; block load/free, merger/deepstack outputs; selected splice/tag/presentation call chain | Visual VAE latents do not replace Qwen visual tokens; merged and three deepstack arrays survive into language encoding |
| [h3_video_encoder.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_video_encoder.c#L638-L814) | Geometry constants; spatial tile construction, extraction/stitching and encoder entry/cleanup | Input encoder has its own weight/workspace peak and host tile/latent output |
| [h3_audio_vae.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_audio_vae.c#L660-L711) | Constants/cleanup; decode stage load/run/free; 1275–1343 encoder entry, geometry and cleanup | Reference encode and output decode have distinct buffers; stage streaming does not erase PCM/latent ownership |
| [h3_video_vae.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_video_vae.c#L892-L1251) | Constants and ordinary/chunked/resident decode, preview, tile/chunk iteration and cleanup | Resident decoder retains weights/activations; tiled/chunked execution still retains complete RGB output |
| [h3_dit_schedule.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_dit_schedule.c), `h3_dit_schedule.h` | Schedule row construction, time-embedding projection, block/final precompute/free/prune and row map | [AdaLN contract](phase-residency.md#adaln-and-prepared-state): tables replace projection residency for one concrete schedule/layout |
| [h3_dit.c](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_dit.c#L502-L761) | Block load/free, stream-source schema/slots, quantization; 1180–1294 layer choice/load; 1481–1690 activation/load policy; 1884–1980 dispatch; 2154–2305 core/SSD path; 2408–2439 reset; 2540–2554 and 2861–2991 reuse; 2995–3062 cleanup | [Precision/SSD procedure](precision-and-streaming.md); transient conversion peaks, effective dispatch, approximation and slot ordering |
| [h3_gpu.m](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_gpu.m#L350-L395) | TensorOps selection/fallback; 175–206 stats formatting; 549–809 shared allocation, mmap, direct/uncached read and free; 889–945 continue/submit | Optional M5 kernels; tracked bytes differ from physical memory; submit waits for all retained commands |
| [h3_shaders.metal](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/h3_shaders.metal#L11-L58) | BF16 rounding, quantizer structs; selected symmetric quantizers at 1366–1682, QKV layout at 1685–1705 and fused gate/AdaLN/quantize at 3319–3515 | Preserve rounded materialized intermediates; symmetric row/group quantization and checkpoint head order are numerical contracts |
| `main.c`, `h3_cli.c` | Selected flag assignments/guards and interactive cache enable/clear call sites | CLI flags must match library behavior; interactive mode enables retention |
| `Makefile`, [README.md](https://github.com/antirez/h3.c/blob/8974cc055ea9c02fcd14cc27dfda3e1027c05153/README.md#L406-L425) | Build/test targets and fixture guards; selected residency/precision/diagnostic and approximation sections | [Native verification map](validation.md); fixture-dependent skips and author-reported results remain separate |
| Native test sources listed in [identity record](source-identity.json) | Selected assertions, fixture paths and argument/default handling; not full test-suite execution | Schedule row/submission assertions, BF16-fusion byte checks, preview parity, component/semantic error gates and benchmark control wiring |

The request path is metadata/probe → selected media input encoders → Qwen
vision/language conditioning → text refinement/AdaLN preparation → joint DiT
video/audio denoising → audio VAE → video VAE → RGB/media output. Some stages
are omitted without the relevant conditioning. Per-stage GPU contexts release
their allocations; host outputs and interactive caches cross stage boundaries.

## Imported model/header research

[MiniMax-H3 Apple comparison](minimax-h3-apple.md) is adapted from InferRSI
`f804ec1503e977787c572d5d27d1f3258017b01f`, originally under the research
workflow. Its [inventory](minimax-h3-weight-inventory.json) is retained
byte-for-byte: 29 official and four selected app-export safetensors JSON-header
digests, pinned model revisions, dtype/packing rules and totals. Header requests
and comparison-source collection were performed by the prior author; they were
**not rerun** in this distillation. No weight payload is included or authenticated.
The comparison's engine/card evidence retains its original independent pins.
Only its discovery instructions and connection to this new source audit change.

## Unread and unverified boundary

No full audit of every Metal kernel, MPSGraph/driver internals, FFmpeg/media
decoder/mux implementation, tokenizer implementation, all failure/exception
paths or concurrent-caller safety was performed. Model payloads, external MLX
goldens, complete checkpoint configs/cards and downstream engine implementations
were not newly inspected. Native correctness, all model/backend combinations,
audio/video quality, physical/compressed/swap peaks, I/O overlap, service
stability and skill efficacy remain unverified. A candidate or a generated
catalog record does not change that boundary.
