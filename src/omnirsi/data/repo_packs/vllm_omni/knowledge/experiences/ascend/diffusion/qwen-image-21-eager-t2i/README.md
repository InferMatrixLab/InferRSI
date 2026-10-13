# Qwen-Image-2.1 eager text-to-image on one 910B1: reuse plus interleaved RoPE, 30% not met

The author reports that on one Ascend 910B1, conditioning reuse plus `npu_rotary_mul` interleaved RoPE cuts the eager BF16 1280×704 eight-step mean from 3111.5 ms to 2459.6 ms with identical RGBA. Opt-in VAE fastpath reaches 2425.5 ms and passes the quality gate without pixel identity. A 30% line at 2178 ms was not met.

This entry imports the NPU measurements reported by [amy-why-3459](https://github.com/amy-why-3459). Status is `imported`, locally verified is `false`, and evidence level is `open_pr`. Raw timings, image outputs and a frozen validator are not included in this import; OmniRSI acceptance remains `INCONCLUSIVE`. Search and show retain this attribution and do not execute patches or commands.

## Scope

- Repository: `vllm_omni`
- Backend: `ascend`
- Scenario: `diffusion.image_generation`
- Hardware: 1× Ascend 910B1, 64 GiB HBM

### Software and workload

- vLLM 0.31.0
- vllm-omni branch `amy/qwen-image-21-conditioning-reuse` at `399cc01d1bc4542964d91aaa17fb43862a8cf3b3`
- Qwen-Image-2.1-Turbo
- BF16, eager, `TORCH_SDPA`, CFG=1, 1280×704, checkpoint native 8 sigmas
- Two warmup rounds, then three repeated prompts with seeds 42/43/44
- Unoptimized baseline mean 3111.5 ms; 30% line is 2178 ms

## Findings and evidence

- **upstream_reported**: Conditioning reuse only: mean 2654.3 ms, −14.7% vs 3111.5 ms, decoded RGBA identical. An earlier same-patch cohort on this host was 2658.2 ms (−14.6%).
- **upstream_reported**: Reuse plus `npu_rotary_mul` interleaved RoPE: mean 2459.6 ms, −21.0%, RGBA identical. Atlas A2 `npu_apply_rotary_pos_emb` has no interleave mode. The fp32 cos/sin table follows the current freqs object; decode slices a longer table to the target-token tail.
- **upstream_reported**: Reuse plus NPU RoPE plus `QWEN21_VAE_FASTPATH=1`: mean 2425.5 ms, −22.0%. Quality gate passed and pixels were not identical. A later rerun was 2431.9 ms (−21.8%).
- **upstream_reported**: A timed first request on the RoPE plus VAE stack spent about 550 ms in prompt encode, 1.5 s in the eight-step denoise, and 190 ms in the VAE.
- **counterexample**: Eager RoPE cos/sin cache, expanded SDPA mask cache, `npu_fusion_attention`, `TASK_QUEUE_ENABLE`, `enforce_eager=0`, and dropping the prompt-cache autograd guard did not clear the keep bar. Per-step input cache and fusion-on-top-of-VAE failed with NPU out-of-memory.
- **quality_limit**: The 2425.5 ms stack is not pixel-identical. Do not describe it as the B300 384.16→266.60 ms five-group HTTP PASS.

## How to use this experience

- Keep `npu_rotary_mul` interleaved RoPE as the NPU default for this complex-pair layout, with `QWEN21_NPU_ROPE=eager` as the fallback.
- Treat `QWEN21_VAE_FASTPATH` as opt-in until a pixel-identical VAE path exists.
- Do not enable `npu_fusion_attention` or per-step input caching on a 64 GiB 910B1 that is already near a 30 GiB allocator watermark.
- Budget the next hypothesis on the eight-step denoise, which remains the largest timed piece.

## Remote validation plan

- Repeat the three-seed warm cohort on a quiet 910B1 before quoting a new mean.
- Keep pixel identity and the SSIM/PSNR gate as separate columns.
- Re-time prompt encode, denoise, and VAE on a warm cache hit before claiming another stage win.

## Limits

- Single 910B1 eager cohort. Not a four-card B300 HTTP result and not a 30% PASS.
- Three measured requests after warmup. No production tail claim.
- Later repeats were blocked when the allocator could not reserve a small extra block and the NPU runtime reported insufficient compute resources.
- Ascend 910B1 evidence does not transfer to CUDA, ROCm, or other Ascend SKUs.

## Sources

- [vllm-omni#8729](https://github.com/vllm-project/vllm-omni/pull/8729) — `399cc01d1bc4542964d91aaa17fb43862a8cf3b3` (open); accessed 2026-10-12.
