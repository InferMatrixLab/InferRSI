Measure whether a change in the GLM-Image implementation in vllm-project/vllm-omni reduces single-request text-to-image latency on Ascend. Use the public Omni.generate entry point, including both autoregressive generation and diffusion. Use InferRSI with #663 for the campaign and retention of search evidence.

### Frozen comparison

- Start the vLLM-Omni comparison at `21a1d1bcc99de83cc23dadbb323dbe82133097df`. Record the exact winning code and its identity with the results.
- Use two reserved Ascend 910B1 cards, BF16 and a single request at a time. Place the AR stage on one card and the diffusion stage on the other. Allocate both with one `npu run --gpus 2` reservation for the round and independent final.
- Fix resolution at 512 × 512, denoising at 20 steps, guidance at 1.5, and the seed for each of two distinct prompts. Retain a separate warmup prompt. Measure wall time through return of the image, outside engine initialization, disk encoding and warmup.
- Keep both images identical to their respective baseline RGB pixels. Compare baseline and candidate in alternating AB/BA order. Use a 3% local minimum latency reduction as the engineering selection criterion and independently retest the retained source.
- Record stage timings when available. Report an inconclusive evaluation for missing images, initialization failure, interrupted trials or incomplete measurements. Limit conclusions to this workload and device configuration.

The vLLM-Omni repository owns the implementation. InferRSI owns the campaign evidence and protocol. Link the scoped changes and independent result here for review.

The stock baseline produced a nearly white blue-cover image for seed 771 (512×512, channel range 237–255, maximum channel standard deviation 1.43152). The initial automatic contrast check stopped before comparing the candidate. That attempt remains **INCONCLUSIVE**. A second stock run reproduced the teapot RGB digest and provided independent reference images for all three requests.

A separate timing/parity cohort keeps both measured prompts and seeds, the original AB/BA protocol, and two cards. Freeze all three stock RGB hashes before the comparison. Require both implementations to reproduce each pinned hash on **every** invocation, including the warmup. The warmup and teapot must still pass the original contrast check. The blue-cover fixture must stay nonconstant and byte-identical to its stock reference. Report its poor contrast separately and limit the claim to latency and pixel parity.
