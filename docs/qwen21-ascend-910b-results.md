# Qwen-Image-2.1-Turbo on one Ascend 910B1

This cohort is separate from the [B300 campaign](qwen21-turbo-b300-phase2-results.md). It does not replace that 384.16 → 266.60 ms PASS, and it does not meet a 30% reduction.

## Setup

- One Ascend 910B1, Qwen-Image-2.1-Turbo, BF16, eager, `TORCH_SDPA`, CFG=1.
- 1280×704 and the checkpoint's native 8 sigmas.
- Two warmup rounds, then three repeated prompts with seeds 42/43/44.
- Unoptimized baseline mean: **3111.5 ms**. A 30% line is **2178 ms**.
- vLLM 0.31.0. Upstream patch: [vllm-omni#8729](https://github.com/vllm-project/vllm-omni/pull/8729) at `399cc01d1`.

Means below are the mean of the three measured requests. Warmup stays outside the mean. Pixel identity is recorded separately from the SSIM ≥ 0.99 and PSNR ≥ 35 dB gate.

## Kept

| Stack | Mean | vs 3111.5 ms | RGBA |
| --- | ---: | ---: | --- |
| Conditioning reuse only | 2654.3 ms | −14.7% | identical |
| Reuse + NPU interleaved RoPE | 2459.6 ms | −21.0% | identical |
| Reuse + NPU RoPE + `QWEN21_VAE_FASTPATH=1` | 2425.5 ms | −22.0% | quality gate passed, not pixel-identical |
| Same stack, later rerun | 2431.9 ms | −21.8% | quality gate passed, not pixel-identical |

The first published conditioning-reuse number on this host was 2658.2 ms (−14.6%). The 2654.3 ms row is a later cohort of that same patch.

NPU RoPE uses `npu_rotary_mul` in interleave mode. Atlas A2 `npu_apply_rotary_pos_emb` only implements half mode, which is a different pairing from this model's complex RoPE. The fp32 cos/sin table follows the current freqs tensor. On decode, a longer table is sliced to the target-token tail. `QWEN21_NPU_ROPE=eager` keeps the unflatten/stack path.

## Rejected

Steps, resolution, and the sampler stayed fixed.

| Change | Mean | Outcome |
| --- | ---: | --- |
| Cache eager RoPE cos/sin only | 2657.2 ms | slower, pixels identical |
| Cache per-step mask and prompt tensors | — | NPU OOM |
| Cache the expanded SDPA mask | 2667.5 ms | slower, pixels identical |
| `npu_fusion_attention`, precise=2 | 2655.2 ms | no gain, pixels identical |
| `npu_fusion_attention`, precise=0 | 2623.7 ms | about 1%, below the keep threshold |
| Fusion only when the step has no mask | 2631.7 ms | too small |
| `TASK_QUEUE_ENABLE=1` | 2654.4 ms | no gain |
| `TASK_QUEUE_ENABLE=2` | 2661.1 ms | slower |
| `enforce_eager=0` | 2718.8 ms | slower than eager |
| Drop the autograd guard on the prompt cache | 2474.7 ms | same band as the current best |
| RoPE + VAE fastpath + fusion attention | — | OOM during initialization |

## Where the time goes

A timed first request on the RoPE + VAE stack spent about 550 ms in prompt encode, 1.5 s in the 8-step denoise, and 190 ms in the VAE. Denoise is still the largest piece. Later requests on a busy host could not be used once the allocator failed a small extra reservation and the NPU runtime reported insufficient compute resources.

Ascend image-generation context:

```bash
python -m omnirsi context --repo-type vllm_omni --backend ascend \
  --scenario diffusion.image_generation --output diffusion-context.md
```

Imported Ascend records are mostly `diffusion.video_generation`, so this export returns the shared `diffusion.*` guidance. These means are descriptive. They are not the B300 five-group HTTP result.
