# Device identity on MUSA

Pinned to `vllm_musa/platform.py` and `vllm_musa/__init__.py` at the revision in
[sources.md](sources.md). Read this before every campaign, not just the first.

## The contract

- The plugin declares `device_control_env_var = "MUSA_VISIBLE_DEVICES"` and
  `dist_backend = "mccl"`.
- `MtmlMUSAPlatform` is the MTML path. Its docstring states that MTML is **not**
  affected by `MUSA_VISIBLE_DEVICES` and that its functions work on **real
  physical device ids**.
- The same class carries a note that CUDA maps a logical `device_id` to a
  physical one, but `torch.musa` uses logical ids when the env var is set, while
  `pymtml` does not remap. The plugin therefore queries the handle by the id it
  was given.
- Commit `7d5371a5ec…` is titled "fix: stop baking MUSA_VISIBLE_DEVICES=all into
  the image" — the image no longer decides visibility for you.

## Why an A/B can be invalid while looking healthy

```
MUSA_VISIBLE_DEVICES=2,3     # torch logical 0,1 -> physical 2,3
pymtml index 0,1             # physical 0,1  (a different pair)
```

An arm launched with that env and a harness that pins "device 0,1" through
`pymtml` can end up measuring card 2 while recording card 0. If the two arms
disagree on the mapping, the delta includes the hardware difference.

## Check, in this order

1. Start the target interpreter and print `pymtml` device count, plus
   `index`/`UUID`/`name` for each device.
2. Print `torch.musa.device_count()` and the per-device properties with the env
   var set and unset.
3. Tabulate env entry → physical index. Only an identity mapping lets a single
   integer name one card in both worlds.
4. Put the UUID set and the mapping in the run record, not just the env string.

## Rules

- Select by UUID when the harness accepts it; keep the integer only as a label.
- Two arms must show the **same physical UUID set**. Different sets invalidate
  the comparison regardless of identical flags.
- Do not reuse a "device 0" claim across hosts; re-read identity per host, per
  driver, and after any container restart.
- When `pymtml` is missing or `nvmlInit` fails, report the tool gap. Do not fall
  back to a logical index and call it physical.

The InferRSI adapter for this backend (`inferrsi --backend musa`) probes through
`pymtml` in the target Python and reports physical `index`/`uuid`/`name`; its
`qualify_devices` helper reads `MUSA_VISIBLE_DEVICES`, so it is only sound under
the identity mapping this page asks you to verify first.
