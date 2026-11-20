# The Omni lane on MUSA

Pinned to `docker/vllm-omni.Dockerfile` at commit `666d6f96d6…` (see
[sources.md](sources.md)). That file is the only Omni-specific artifact in the
cited revision; re-read it at the revision you actually build.

## What the image does

- Inherits the MUSA base image (torch, `torch_musa`, `torchada`, `triton`,
  `mate`, `vllm`, `vllm-musa` already installed).
- Sets `VLLM_OMNI_TARGET_DEVICE=musa` so the vllm-omni build does not fall back
  to CPU when no GPU is visible during `docker build`.
- Records the installed versions of `flash_attn_3`, `flash_mla`, `mate`,
  `torch`, `torch_musa`, `torchada`, `triton`, `vllm`, `vllm-musa`; installs
  vllm-omni under that constraint file; then fails the build if any constrained
  distribution changed.
- Smoke-imports `torchada`, `torch`, `torch_musa`, `vllm`, `vllm_musa`,
  `vllm_omni` and asserts `torch.version.musa is not None`.

## Consequences for optimization work

- **CUDA-only accelerators are out of scope by construction.** If a CUDA Omni
  optimization's mechanism is `flash_attn_3` or `flash_mla`, it cannot be the
  cause of a change inside this image.
- **The MUSA stack is the fixed point.** Upgrading one pinned distribution to
  chase a CUDA-side patch breaks the image's own invariant check; treat that as
  a deliberate, separately funded experiment.
- **Reachable levers** are engine-side and model-side: reuse of conditioning or
  text embeddings across requests, work shared across denoise steps, tile and
  batch geometry for VAE decode, scheduler/batching decisions, and whatever
  attention path vllm-omni actually registers for `musa`.

## Procedure for one Omni candidate

1. Build or pull the image; capture the printed constraint list and the image
   digest. If you cannot produce them, stop — the runtime identity is unknown.
2. Establish the baseline inside that image: one model, one resolution, one
   frame/duration setting, fixed seed and prompt set, service warm before timing.
3. Check the quality gate first, on the baseline, so a later failure can be
   attributed: pixel-identical decode where the change claims losslessness;
   otherwise an explicit tolerance with the reference it was measured against.
4. Apply one candidate. Profile one denoise step and one decode step to confirm
   the mechanism moved (see [dispatch.md](dispatch.md)).
5. Run the pair with [measurement.md](measurement.md): both arms in the same
   image, same device UUIDs, AB/BA order, restart between arms.
6. Record latency **and** the quality verdict. An image/video gain with an
   unqualified quality comparison stays INCONCLUSIVE.

## Do not carry over

CUDA numbers from the vllm-omni knowledge records are scoped to their hardware
and revision. They are useful as a list of *candidate mechanisms*, never as an
expected percentage on MUSA.
