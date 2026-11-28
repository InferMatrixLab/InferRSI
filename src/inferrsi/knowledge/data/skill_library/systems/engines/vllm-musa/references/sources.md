# Sources and revision pin

This skill is a source-derived candidate. It was written by reading the files
below; it was **not** validated by running a model on MUSA hardware.

| Identity | Value |
| --- | --- |
| Repository | `https://github.com/MooreThreads/vllm-musa` |
| Revision read | `7d5371a5ecfd1e04ea303f847e75cf3747e92fcd` |
| Omni image revision | `666d6f96d6e6ccc5439821f3c3ca34d049e3f176` |
| License | Apache-2.0 |

## Files read

- `vllm_musa/__init__.py` — `torchada` import order, `_torchada_available`,
  `musa_platform_plugin()` and the `torch_musa` fallback.
- `vllm_musa/platform.py` — `device_control_env_var`, `dist_backend = "mccl"`,
  `MtmlMUSAPlatform` and the MTML-versus-logical-id note.
- `docker/vllm-omni.Dockerfile` (at the Omni image revision) —
  `VLLM_OMNI_TARGET_DEVICE=musa`, the constraint list, the drift check and the
  smoke imports.
- `vllm_musa` commit `7d5371a5ecfd1e04ea303f847e75cf3747e92fcd` — removes a
  baked `MUSA_VISIBLE_DEVICES=all` from the image.

## Knowledge records that carry the same facts

- `vllm_musa.musa.llm.physical_device_identity`
- `vllm_musa.musa.llm.torchada_dispatch_boundary`
- `vllm_musa.musa.diffusion.omni_image_porting`

## Bounds

- No hardware, driver or SKU benchmark is included; no speedup is claimed.
- The plugin moves quickly; re-read the cited files at the revision you use and
  treat a changed file as a changed procedure.
- MATE, `torchada`, MUSA toolkit and Mooncake behaviour is out of scope for this
  pin: this skill describes the plugin's contract, not those libraries' tuning.
