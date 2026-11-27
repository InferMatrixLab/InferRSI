# Field Notes: Ascend Video Diffusion Optimization

First-hand observations from video-editing diffusion campaigns on Ascend NPU. Use them as starting hypotheses and as a list of failures to avoid, never as defaults.

Provenance and limits:

- The observations cover two variants of one video-editing model family; both were edited for text and both used a vision-language condition encoder.
- Exact measurements were removed or coarsened. Remaining figures are order-of-magnitude recollections, not reproducible evidence.
- No campaign under a published evidence contract produced these notes. Treat them as `unverified` and non-reproducible.
- A redacted artifact cannot turn an unverified observation into local validation. Re-measure on the target model before relying on any figure below.

## Variants

- **Variant A.** OCR-oriented vision-language condition encoder; short-video text editing; a sparse-attention path that only becomes eligible above a video-token threshold.
- **Variant B.** Vision-language encoder plus a byte-level text encoder; video DiT with routed and shared MoE experts; temporal video VAE.

## Findings That Transferred Across Both Variants

1. Stage profiling repeatedly changed the optimization order. Condition encoding, DiT, and VAE dominated at different points; no single optimization stayed dominant through a campaign.
2. Correct visual downsampling mattered more than any kernel change. Accidentally retaining unrelated benchmark pixel settings multiplied condition-encoding time by roughly an order of magnitude.
3. Condition work and VAE encode could overlap only after the request dependency graph showed no edge between them before DiT. The observed gain depended on exposed time, stream safety, contention, and concurrent HBM — never assume the overlap pays off.
4. Sparse attention reduced DiT time modestly and could not fix VAE allocation failures.
5. Output quality could fail before memory capacity did. Running the full frame count in one pass left text artifacts even at full precision, which points at a model or sequence-length limit rather than a quantization defect.
6. VAE decode became dominant after DiT improvements, so every accepted DiT change required a fresh end-to-end profile.

## Sparse-Attention Observations

One same-workload comparison reported a low-single-digit end-to-end improvement and a mid-single-digit DiT-stage improvement, with mean image-similarity metrics staying above the campaign gates for the large majority of cases and a minority requiring visual review.

The accepted configuration enabled sparse attention only after the first denoising step and skipped boundary layers. This was a quality compromise specific to that model. Short or otherwise ineligible sequences fell back to dense attention.

Treat the method as lossy until exactness is demonstrated on the target workload.

## Residency And Quantization Observations

- Offloading both condition encoders to the host made prompt encoding dominate the entire request — tens of seconds against a few seconds of DiT and VAE work.
- Keeping the encoders resident cut steady-state latency substantially, but left too little HBM for a no-tiling VAE decode. Residency alone was not a winning configuration.
- Offline INT8 W8A8 on DiT weights roughly halved their footprint.
- Selectively quantizing only the language-MLP weights of the condition encoder freed a few GiB while attention, embeddings, normalization, and vision stayed in higher precision.
- The configuration that finally fit a single-device budget combined DiT W8A8, selective language-MLP W8A8, and resident encoders.

Component boundaries that were used, as hypotheses only:

- Quantized candidates: DiT attention projections, routed experts, shared experts, condition-encoder language MLP.
- Higher-precision holdouts: routers, normalization, embeddings, condition-encoder attention, vision tower, byte-level text encoder, VAE.

Revalidate every boundary for each checkpoint.

## Correctness Root Causes Observed

- **Wrong patch-assembly order.** Interpreting the projection output as channels-first patch axes instead of patch axes then channels collapsed prediction agreement to near zero; restoring the order returned near-exact agreement.
- **Missing text cleanup.** The reference implementation applied text normalization, HTML unescaping, and whitespace cleanup that the serving path skipped.
- **Different RNG advancement.** One framework advanced a global generator while the other reset per case, so equal seeds produced different initial noise.
- **Wrong architecture mode.** Loading a text-conditioned checkpoint through a non-text path silently selected the wrong branch and produced corrupted output.
- **Incorrect padding semantics** around a vision-language token refinement stage.
- **Missing contiguous materialization before a packed layout conversion.** A physical-layout mismatch corrupted the video; cloning to a contiguous tensor before conversion restored deterministic cold and warm output.

The localization sequence that worked: one denoising step, identical initial latent, first divergent block, then attention, routing, experts, and residual.

## Long-Video Policy

One validated policy used a bounded chunk length with a small overlap and an adaptive midpoint hard cut at the join. Linear blending produced doubled text and residual glyphs in overlap regions.

The specific values are not architecture constants. Derive chunk length and overlap from the target model's quality and memory curves.

## VAE Observations

- No-tiling decode improved short-video results when HBM headroom was sufficient.
- Long-video no-tiling decode requested more memory than remained and failed to allocate.
- Replacing incremental `torch.cat` in a temporal loop with list accumulation and one final concatenation preserved output exactly.
- Increasing the temporal decode chunk size gave a small speedup but a much larger peak-HBM increase, so it was rejected as a default.
- A graph-fusion experiment improved latency by less than one percent while adding several GiB.
- Existing fused operators written for a different VAE architecture did not match this VAE's structure.

## Rejected Or Dangerous Experiments

- Online low-precision float formats on the tested stack: unsupported dynamic quantization and incompatible MoE constraints.
- Moving VAE to CPU: unacceptable latency cost and possible numerical drift.
- Frequent layer or weight offload: transfer latency, fragmentation, and complexity outweighed the memory benefit.
- Aggressively releasing the DiT workspace: produced corrupted output on the tested path.
- Fused video-to-uint8 conversion: produced striped or corrupted output.
- Treating sparse attention as a VAE-memory fix: it reduced DiT work and left the decode allocation untouched.
- Static-shape compilation as a universal setting: it conflicted with mixed short and long video shapes and raised HBM risk.

## Profiler-Guided Follow-Ups

One steady-state profile identified:

- MoE precision-conversion copies as a significant share of an internal copy operator.
- Main-stream waits on condition streams as exposed synchronization time.
- The sparse attention kernel group as the largest DiT cost.
- VAE layout-conversion operations and temporal concatenation as notable decode overhead.

Keeping the first grouped-matmul intermediate in a lower-precision format produced a small latency gain with a small measured quality drift. The campaign accepted it as an approximation; an exact solution needs a kernel that supports the desired scale and output format combination.

## Reusable Acceptance Pattern

For each candidate:

1. Run a short representative case for fast iteration.
2. Check intermediate parity when the mechanism changes numerics or layout.
3. Run repeated warm latency and peak-HBM measurements.
4. Run automatic frame metrics and task-specific visual inspection.
5. Test the longest supported sequence.
6. Recheck cold start when loading, packing, or compilation changed.
7. Remove instrumentation and rerun the final artifact.
