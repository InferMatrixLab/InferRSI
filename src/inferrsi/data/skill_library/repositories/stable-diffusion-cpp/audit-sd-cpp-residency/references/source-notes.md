# Source scope and image call path

Repository: leejet/stable-diffusion.cpp. Declared revision:
`b13a48219d5cdf408edcb93da6cd69b612ed03d3`. License: MIT, Copyright
(c) 2023 leejet; the original [LICENSE](../LICENSE) is retained. Mechanisms are
rewritten guidance with immutable source links; no runtime implementation is
transplanted.

The readset was inspected on 2026-10-22 from the supplied codeload archive,
without extracting the whole archive, executing its code or fetching models.
The supplier manifest initially matched only the README Git blob. A separate
2026-10-22 [identity receipt](source-identity.json) follows the pinned Git commit
to tree `df847d004c6529eefb02bb629d7ee26e740121a9` and matches Git blob IDs and
sizes for 18 bounded readset paths plus one separately identity-checked
`README.md` against the archive bytes (19 blobs total). The readset includes
selected header declarations; file identity does not imply a complete-file review.
This authenticates those 19 file identities, not every archive member or
the contents of the four submodules. The pinned submodule commit IDs are
recorded separately; their source was not fetched or verified.
The absent GGML/frontend/libwebp/libwebm submodules are declared by
[.gitmodules](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/.gitmodules#L1-L12).
No complete AREX environment/native verification is claimed.

Header coverage is limited to selected owner/state declarations in
[`src/model_manager.h`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.h),
not a complete header review. The README identity check is not an implementation read.

## Bounded CODE path

1. The CLI creates the context and calls the image API:
   [main.cpp](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/examples/cli/main.cpp#L894-L932).
   [`new_sd_ctx`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/stable-diffusion.cpp#L643-L669)
   owns `StableDiffusionGGML`, calls `init`, and cleans failed initialization.
2. [`init`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L931-L1046)
   constructs the model manager, configures mmap/segmentation/prefetch, discovers
   model metadata and establishes backend placement. Selected component files
   enter through
   [`init_model_loader`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L726-L783).
   These entry points do not prove all weight bytes are resident or a request fits.
3. The [C API image call](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/stable-diffusion.cpp#L743-L755)
   creates `ExecutionScope`. Its
   [context operation](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.h#L216-L254)
   rejects concurrent/reentrant use of the same context, checks source refresh
   before generation, and ends runners on scope exit when ready. This is not a
   blanket thread-safety guarantee for every API.
4. [`pipeline::generate_image`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/image.cpp#L783-L847)
   checks model capability, builds a `GenerationRequest`, preprocesses inputs,
   seeds RNGs, applies LoRAs and prepares latents/conditioning. The conditioning
   helper calls
   [`get_learned_condition`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/image.cpp#L420-L520).
5. It calls
   [`sd->sample`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/image.cpp#L849-L921)
   with the plan's sigmas, model-dependent conditioning and latent inputs;
   optional hires work is a separate additional pass. Final latents go through
   [`decode_image_outputs`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/image.cpp#L539-L638)
   and `decode_first_stage`, then
   [API output finalization](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/image.cpp#L1041-L1062).

The generic runner's resource path is separately traced through
[`GGMLRunner::execute_graph`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/ggml_runner.cpp#L829-L1028),
`SegmentWeightPipeline` and `ModelManager`, as detailed in
[phase residency](phase-residency.md). Model-specific conditioner/denoiser/VAE
implementations and the sampler's full numerical loop were not traversed; the
two bounded paths must not be advertised as every model's complete call graph.

## Source refresh is separate from physical release

[`refresh_model_sources` / `apply_model_update`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L270-L305)
compares loader/catalog state and rebuilds affected runner groups.
[`reset_runners`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L229-L267)
clears conditioning caches, ends runners and unregisters parameters before
resetting components. The loader's complete file-change predicate was not
inspected; do not call it a content hash or assert equal mtime/size means equal
model bytes. Actual model revisions belong in the validation input ledger.

## Build and verification boundary

[`cmake/ggml.cmake`](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/cmake/ggml.cmake#L1-L27)
requires `ggml-impl.h` from source matching the selected GGML library, including
system-library builds. Upstream-GGML mode changes INT8/convrot and FP8 handling;
it is not an interchangeable backend for a claimed comparison. The inspected
[CI CPU and Vulkan jobs](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/.github/workflows/build.yml#L57-L152)
perform recursive checkout and builds; they do not establish image inference,
memory-budget correctness or quality. No test-named regular files were found
in the supplied archive inventory; this is a bounded snapshot observation,
not a statement that upstream has never had tests.
