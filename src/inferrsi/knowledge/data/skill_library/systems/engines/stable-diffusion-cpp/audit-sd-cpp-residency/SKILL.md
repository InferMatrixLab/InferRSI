---
name: audit-sd-cpp-residency
description: Audit stable-diffusion.cpp image-generation memory pressure by separating catalog freshness and weight-byte delivery from model parameter storage, compute weight residency, retained runtime buffers and segment prefetch under the actual backend.
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
        "stable-diffusion-cpp",
        "diffusion",
        "model-residency",
        "workspace",
        "prefetch",
        "state-ownership",
        "weight-loading",
        "storage-io"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/leejet/stable-diffusion.cpp",
          "commit": "b13a48219d5cdf408edcb93da6cd69b612ed03d3",
          "paths": [
            "src/stable-diffusion.cpp",
            "src/pipeline/image.cpp",
            "src/pipeline/diffusion_engine.h",
            "src/pipeline/diffusion_engine.cpp",
            "src/core/ggml_runner.cpp",
            "src/core/segment_weight_pipeline.cpp",
            "src/core/compute_workspace.cpp",
            "src/model_manager.cpp",
            "src/model_manager_prefetch.cpp",
            "src/device_residency_manager.h",
            ".github/workflows/build.yml",
            ".gitmodules",
            "cmake/ggml.cmake",
            "CMakeLists.txt",
            "examples/cli/main.cpp",
            "include/stable-diffusion.h",
            "LICENSE",
            "src/model_manager.h",
            "src/model_loader.h",
            "src/model_loader_files.cpp",
            "src/model_loader.cpp",
            "src/model_manager_files.cpp",
            "src/model.h",
            "src/core/util.h",
            "src/core/util.cpp",
            "src/model_io/tensor_storage.h",
            "src/model_io/safetensors_io.cpp"
          ],
          "readset": "references/source-notes.md"
        }
      ],
      "applicability": {
        "scope": "Source-grounded audit of native image-generation weight/runtime residency, optional segment prefetch and bounded non-ZIP safetensors catalog/read/staging ownership; confirm the actual source, GGML, backend, model and executing path independently.",
        "prerequisites": "Access to the pinned source/storage boundaries and evidence of the actual image runner/backend dispatch; native capacity or prefetch checks require matching GGML, model and backend resources.",
        "input_contract": "Runtime/GGML revisions and selection, compiled/loaded backends and devices, model/components and numerical image settings, effective memory/prefetch/placement settings and actual dispatch; retain available phase allocations, cache/workspace, transfer events and completed-image counts.",
        "produced_artifact": "A phase-by-runner/backend/device ownership table for stored and resident weights, retained runtime, pending allocations, pin/prefetch ownership and release/eviction, with one discriminating check and its actual status.",
        "failure_modes": "Treating max_vram as proof of segmentation, unpin as physical freeing, or configured prefetch as completed useful overlap can misidentify the capacity cause; missing observations cannot be read as zero.",
        "refusal_point": "Stop when the cause is resolved or matching GGML/model/backend resources are unavailable; invoking this audit does not authorize dependency installation, model downloads, policy changes or device provisioning."
      },
      "limitations": [
        "Source-derived candidate; native inference, allocator behavior, image quality and performance were not run.",
        "Eighteen bounded readset paths plus one separately identity-checked README match the pinned Git commit/tree blob IDs and sizes (19 blobs total); header coverage is limited to selected owner/state declarations, and this does not authenticate every archive member or submodule contents.",
        "The loader/storage extension separately authenticates twelve bounded C++ source blobs and the retained MIT text; its line-scoped readset does not replace the historical archive receipt. Catalog stamps are not content hashes; read/mapping/backend calls do not establish storage throughput or device completion.",
        "GGML and other submodules are not expanded; matching private GGML headers are required even for a system library.",
        "CPU bypasses the inspected accelerator capacity gate and segmentation eligibility, so CPU checks cannot qualify accelerator memory budgets or prefetch.",
        "Video/audio pipelines, detailed model kernels, approximate denoising caches and full multi-device execution remain outside this readset.",
        "Loader rules select ordinary non-ZIP safetensors; full GGUF/Torch/ZIP parsers, special quantization/conversion correctness and native failure injection remain unqualified."
      ],
      "provenance_readsets": [
        "references/source-notes.md",
        "references/loader-storage-boundaries.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Separate parameter storage, compute-resident weights, retained workspace/output caches and pending allocations for each runner and phase.",
        "Verify the actual monolithic, segmented or multi-device path before interpreting a memory budget or prefetch setting.",
        "For a policy comparison, hold model, inputs, numerical settings and device fixed; check completed images and quality before latency, and separate startup, first and warm requests."
      ]
    }
---

# Audit diffusion weight and workspace residency

Source-derived candidate for leejet/stable-diffusion.cpp at
`b13a48219d5cdf408edcb93da6cd69b612ed03d3`. Read the
[source scope](references/source-notes.md) and retained MIT license before
transferring the procedure. No native inference, accelerator memory behavior,
image quality or performance result has been established for this candidate.

Use when this runtime fails to fit an image workload, repeatedly transfers
weights, or appears to ignore a configured device-memory budget. The output is
an ownership audit and the smallest discriminating check. Follow the
[loader/storage boundaries](references/loader-storage-boundaries.md) when
source refresh, short reads or host/mapped storage affect this audit. Keep
generic startup-I/O optimization with the existing weight-loading method;
the procedure below addresses request-time weights and runtime buffers.
It does not prescribe LLM KV policy,
training activation checkpointing, approximate denoising caches, or the separate
video/audio paths.

## Required inputs

- Exact runtime and GGML revisions, patched/upstream GGML selection, compiled
  backends, loaded backend libraries, physical devices and effective placement.
- Model/component files and revisions; precision/quantization, LoRAs, image
  dimensions, batch, seed, sampler/sigmas, conditioning and VAE configuration.
- Effective `backend`, `params_backend`, `split_mode`, `max_vram`, eager-load
  and prefetch settings; actual monolithic/segmented/scheduler dispatch.
- Per-phase observations when available: weight load/staging events, retained
  workspace/cache bytes, pending allocations, actual device free/used bytes,
  host memory, transfer/event traces and completed image count. Missing data
  remains a limitation, not an inferred zero.

## Procedure

1. **Locate the real image path.** Trace context creation, the C API execution
   scope, request preparation, conditioning, sampling and VAE decoding using
   [source notes](references/source-notes.md). Record model-dependent shapes
   and stages. Do not assume a universal VAE scale or that a successful load
   proves the first image can execute.
2. **Build a phase ledger.** For conditioning, each relevant denoising runner
   and VAE decoding, distinguish parameter storage, compute-resident weights,
   retained workspace/output caches and pending allocations. Name the runner
   and backend/device owner. A logical parameter or released pin is not a
   physical allocation counter.
3. **Check the two capacity questions.** Follow
   [phase residency](references/phase-residency.md): can the device supply the
   next allocations, and does managed weight plus runtime residency fit the
   explicit budget? Keep missing weights, current/other runner residency,
   reusable workspace and pending cache outputs separate. Treat the pinned
   safety/headroom constants as implementation details, not portable tuning
   rules or guaranteed process-memory caps.
4. **Verify dispatch before diagnosing segmentation.** At this source revision,
   graph segmentation requires a non-CPU, single-device runner, enabled manager,
   valid multi-segment cuts and a monolithic fit failure. Multi-device scheduling
   and CPU are different paths. Check the actual path instead of assuming a
   small `max_vram` setting forced segmented execution.
5. **Follow one segment's lifetime.** Record active and queued parameter sets;
   capacity protection; prepare/pin; computation and synchronization; output
   capture; unpin; later eviction. Preparing weights can run LoRA work and
   reclaim workspace, so inspect the subsequent measurement/capacity checks.
   Unpinning permits later reclamation; it does not itself free all weights.
6. **Audit optional prefetch.** Confirm missing next-segment weights and backend
   async capability, protected active/queued weights, capacity admission,
   successful scheduling and activation before use. Separate configured,
   scheduled, completed and useful overlap. An unsupported/failed prefetch
   disables that pipeline; subsequent weight preparation remains required.
7. **Choose one real check.** Use the
   [validation boundaries](references/validation-boundaries.md). Compare the
   same model, inputs, numerical configuration and device while changing only
   the relevant residency/prefetch policy. Check completion and image quality
   before interpreting latency. Include startup, first request and warm requests
   separately, plus host/device peaks and transfer events. CPU cannot stand in
   for the accelerator capacity or async-prefetch path.
8. **Return a bounded decision.** State the supported cause, counter-explanation,
   invariant at risk, one next action and its falsifier. Stop when the cause is
   resolved or matching GGML/model/backend resources are unavailable. Do not
   install dependencies, download weights, change policy or provision devices
   merely by invoking this audit.

## Expected output

Return one table containing `phase`, `runner/backend/device`, `weight storage`,
`compute-resident weights`, `retained runtime`, `pending allocation`, `pin or
prefetch owner`, `release/eviction boundary`, and `evidence/unknown`; then the
chosen check and actual pass/fail/not-run status. Keep CODE observations,
runtime measurements and transfer hypotheses distinct. Catalog/packaging tests
do not validate this runtime or promote the candidate.
