---
name: audit-h3-runtime-residency
description: Audit MiniMax-H3 generation in h3.c on Apple Silicon by tracing conditioning, AdaLN precompute, DiT residency, Metal precision paths, SSD streaming and audio/video decoding.
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "MIT",
      "tags": [
        "h3.c",
        "MiniMax-H3",
        "apple-silicon",
        "metal",
        "diffusion",
        "video",
        "audio",
        "multimodal-conditioning",
        "adaln",
        "model-residency",
        "ssd-streaming",
        "int8",
        "bf16"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/antirez/h3.c",
          "commit": "8974cc055ea9c02fcd14cc27dfda3e1027c05153",
          "paths": [
            "h3.h",
            "h3_internal.h",
            "h3.c",
            "h3_weights.c",
            "h3_weights.h",
            "h3_safetensors.c",
            "h3_host.c",
            "h3_text_encoder.c",
            "h3_vision_encoder.c",
            "h3_multimodal.c",
            "h3_video_encoder.c",
            "h3_audio_vae.c",
            "h3_video_vae.c",
            "h3_dit_schedule.c",
            "h3_dit_schedule.h",
            "h3_dit.c",
            "h3_gpu.m",
            "h3_shaders.metal",
            "main.c",
            "h3_cli.c",
            "Makefile",
            "README.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "tests/test_h3.c",
            "tests/test_bf16.c",
            "tests/test_real_dit_schedule.c",
            "tests/test_real_prompt.c",
            "tests/test_real_multimodal_text.c",
            "tests/test_semantic_dit.c",
            "tests/test_semantic_vae.c",
            "tests/test_real_audio_vae.c",
            "tests/test_real_video_vae.c",
            "tests/bench_dit.c"
          ],
          "readset": "references/source-notes.md",
          "identity": "references/source-identity.json",
          "license": "MIT",
          "third_party_notices": "references/THIRD_PARTY_NOTICES.md"
        },
        {
          "type": "git",
          "url": "https://github.com/InferMatrixLab/InferRSI",
          "commit": "f804ec1503e977787c572d5d27d1f3258017b01f",
          "paths": [
            "src/inferrsi/data/skill_library/workflows/research/inference-engine-research/references/minimax-h3-apple.md",
            "src/inferrsi/data/skill_library/workflows/research/inference-engine-research/references/minimax-h3-weight-inventory.json"
          ],
          "scope": "Prior model/engine comparison and safetensors header observations, reused without reissuing range requests; inventory bytes preserved."
        },
        {
          "type": "document",
          "url": "https://huggingface.co/MiniMaxAI/MiniMax-H3/tree/42ed227ee7df40d41602854ae760620d6eb651fe/FL2VA",
          "version": "42ed227ee7df40d41602854ae760620d6eb651fe",
          "scope": "29 JSON-header digests and component aggregates retained from prior inspection; payload and complete model license not newly verified.",
          "license": "UNKNOWN",
          "readset": "references/minimax-h3-weight-inventory.json"
        },
        {
          "type": "document",
          "url": "https://huggingface.co/appautomaton/minimax-h3-base-8bit-mlx/tree/9a08116a349ab469b097775b5a483affcb5ccd34",
          "version": "9a08116a349ab469b097775b5a483affcb5ccd34",
          "scope": "Four selected export JSON-header digests/packing aggregates retained from prior inspection; payload and model/export license not newly verified.",
          "license": "UNKNOWN",
          "readset": "references/minimax-h3-weight-inventory.json"
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "capability-specific",
        "strategy": "direct",
        "status": "portable-candidate",
        "native_import": "not-run",
        "method": "Manual pinned-source distillation informed by the existing Repo-To-Skill ledger; no AREX/DisCo execution or behavioral efficacy claim."
      },
      "applicability": {
        "scope": "MiniMax-H3 joint audio/video C/Metal runtime audit: raw checkpoint compatibility, input encoders, schedule precompute, phased/cached residency, numerical controls and SSD streaming on Apple Silicon. Common catalog placement is a discovery classification, not cross-backend qualification.",
        "prerequisites": "Access to the pinned source architecture and selected component/format inventory; native checks need matching model, fixture and backend resources within an authorized experiment budget.",
        "input_contract": "Runtime revision/patches, macOS/SDK/GPU and memory budget, FL2VA/Ref2VA selection, component formats, prompt and ordered media, requested/aligned frames, canvases, steps/seed, layer/reuse/token/precision policies and preview/interactive-cache state.",
        "produced_artifact": "A phase/component/owner ledger with resident weights, runtime/host buffers, overlap, release/reuse boundaries and observations/unknowns, followed by a discriminating check, actual result and remaining gap.",
        "failure_modes": "Estimating fit from model-file bytes, confusing runtime int8 with incompatible MLX bundles, ignoring preview/cache overlap, or reducing DiT residency to address a VAE/host-output peak can produce a wrong capacity diagnosis.",
        "refusal_point": "Stop at unavailable model/fixture/backend resources or the accepted experiment budget; missing target evidence remains unverified/INCONCLUSIVE."
      },
      "limitations": [
        "Native h3.c/Metal execution, target peak memory, audio/video quality, performance, service behavior and skill efficacy were not run.",
        "Only the bounded readset was inspected; complete kernel, driver/MPSGraph, tokenizer, FFmpeg, concurrent-caller and failure-path coverage is not established.",
        "The retained inventory authenticates only prior JSON header observations, not weight payloads; full official versus selected truncated/packed export inventories are distinct.",
        "Upstream 128 GB M5 Max results and tracked DiT bytes do not qualify a 64 GiB target, a different workload or total physical memory.",
        "MIT covers the h3.c source; retained BSD-3-Clause notices and independent model/export/tool licenses remain separate. UNKNOWN source-license fields are unresolved."
      ],
      "provenance_readsets": [
        "references/source-notes.md",
        "references/source-identity.json",
        "references/minimax-h3-weight-inventory.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Resolve the actual conditioning and output components before counting residency; do not add alternative checkpoints or count shared files twice.",
        "Trace one-shot, preview and interactive ownership separately, including AdaLN schedule dependencies and prepared-cache reset boundaries.",
        "Classify approximation and precision controls before comparison, then measure the relevant phase with tensor, physical/compressed/swap and storage observations."
      ]
    }
---

# Audit h3.c runtime residency and numerical paths

Source-derived candidate for `antirez/h3.c` at
`8974cc055ea9c02fcd14cc27dfda3e1027c05153`. Use for MiniMax-H3
text/image/video/audio conditioning, memory-fit diagnosis, kernel changes or a
dedicated-engine design derived from this C/Metal runtime. Start with the
[source readset and architecture](references/source-notes.md). For the model's
aliases, component roles and input/output modalities, open the
[MiniMax-H3 profile](references/minimax-h3-profile.json) and its pinned model card. Native execution,
media quality, performance and behavioral skill efficacy are **not_run**.

## Inputs and decision

Record the runtime revision/patches, macOS/SDK/GPU, memory budget, selected FL2VA
or Ref2VA checkpoint and complete component/format inventory. Freeze the prompt,
ordered reference media, requested and aligned frames, output/internal canvas,
steps, seed, layer/reuse/token policies, all precision controls, preview and
interactive-cache state. An installed engine name or a successful metadata load
does not identify this execution configuration.

Produce a phase ledger and one smallest discriminating check. The useful output
is a supported cause, invariant, counter-explanation and falsifier; model-file
bytes alone do not decide whether a workload fits unified memory.

## Procedure

1. **Resolve the executing pipeline.** Follow `h3_generate` through the
   [phase ledger](references/phase-residency.md). Ordered references select the
   separate Ref2VA DiT; FL2VA first/last-frame conditioning still needs both the
   video input encoder and the Qwen vision/language path. Audio conditioning and
   audio output decoding are different calls. Count the selected input and
   output components without adding alternative checkpoints or repeated shared
   files. Use the [retained weight inventory](references/minimax-h3-weight-inventory.json)
   for its exact checkpoint selections, not as a universal model-size constant.
2. **Check representation before capacity.** The raw loader validates exact
   names, rank, shape and BF16/F32 dtype. Runtime symmetric int8 conversion is
   different from loading MLX affine `U32` bundles. A smaller published bundle
   needs a compatible engine or an explicit conversion; matching bit width is
   insufficient. Keep header validity and payload integrity separate.
3. **Trace ownership across phases and requests.** Distinguish host embeddings,
   media/latent/output buffers, shared Metal tensors, file-backed mappings,
   AdaLN tables and prepared-model/decoder caches. In the one-shot path the DiT
   is freed before decoding; preview and interactive retention can overlap
   phases. Audit cache keys and clear/reset boundaries before diagnosing a leak
   or assuming a warm request has cold-request memory behavior.
4. **Preserve the schedule contract.** AdaLN tables are indexed by the actual
   video/audio schedule, conditioning presence, modality tags and layout.
   Each projection is submitted and released before loading the next. Rebuild
   when those dependencies change; do not replace conditioning timesteps or
   collapse audio/video rows because their step counts match. See the
   [schedule and cache invariants](references/phase-residency.md#adaln-and-prepared-state).
5. **Classify every numerical change.** Follow
   [precision and streaming](references/precision-and-streaming.md). Separate
   BF16-preserving fusions from int8 approximation, BF16 output-head conversion,
   layer thinning, velocity/core reuse, token reduction and internal-canvas/RoPE
   changes. On M5, 50 layers and `--reuse 1` still allow default int8 paths.
   Select the explicit BF16 controls and F32-head diagnostic when that is the
   frozen reference. A kernel parity result is not full audio/video quality.
6. **Choose the residency tradeoff that addresses the measured phase.** Qwen
   prefetch overlaps current-layer compute with future-layer reads and increases
   resident buffers. Mapped persistent DiT weights remain file-backed; explicit
   SSD mode instead rotates two BF16 matrix slots and disables int8. It changes
   I/O and command boundaries. Reducing DiT residency will not resolve a VAE,
   reference-media or host-output peak. Track physical/compressed/swap memory
   alongside tensor counters and storage reads.
7. **Run the matching check when resources exist.** The
   [validation recipe](references/validation.md) maps native targets, required
   fixtures and proposed probes to these invariants. Preserve skipped fixtures,
   startup/first/warm timing, both output modalities and all failed trials.
   The [Apple feasibility comparison](references/minimax-h3-apple.md) is retained
   imported research; neither its upstream measurements nor packaged-reader
   tests qualify a new Mac, workload or 64 GiB memory budget.

## Report and stop

Return a table with `phase`, `component and format`, `owner`, `resident weights`,
`runtime/host buffers`, `overlap`, `release or reuse boundary`, and
`observation/unknown`; then the exact check, actual outcome and remaining gap.
Stop at unavailable model/fixture/backend resources or the accepted experiment
budget. Reading this skill does not install an engine, download weights, run a
distiller, authorize a campaign or promote this candidate. Missing target
evidence remains unverified/INCONCLUSIVE.
