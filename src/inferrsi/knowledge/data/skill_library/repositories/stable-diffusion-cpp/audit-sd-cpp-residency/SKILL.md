---
name: audit-sd-cpp-residency
description: Audit stable-diffusion.cpp image-generation memory pressure by separating catalog freshness and weight-byte delivery from model parameter storage, compute weight residency, retained runtime buffers and segment prefetch under the actual backend.
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
