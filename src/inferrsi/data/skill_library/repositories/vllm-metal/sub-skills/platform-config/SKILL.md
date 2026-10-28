---
name: platform-config
description: "Diagnose vllm-metal platform registration, MLX versus PyTorch MPS
  selection, configuration parsing, native artifact ABI, and model-loading
  compatibility before an authorized Apple inference run."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Platform, configuration and native identity

Use this route when the plugin imports but no Metal platform appears, a setting
is ignored, native artifacts are stale, or a checkpoint chooses an unexpected
text/multimodal/backend path. Source-derived candidate; not a runnable engine.

## Establish the boundary

1. Read [platform and loading contracts](references/platform-and-loading.md).
   Record source/package versions, Python, OS/architecture, selected backend,
   model and tokenizer identities, executor and effective runner configuration.
   A successful lazy root import proves neither registration nor inference.
2. Distinguish MLX's device choice from the alternative PyTorch MPS backend.
   `VLLM_MLX_DEVICE=cpu` is not a substitute for Apple Metal tests.
   An explicit runner override is not silently repaired; MLX implements the V1
   runner while MPS defaults to the upstream V2/hardware-agnostic route.
3. Before changing host software, use the offline
   [selected-knob checker](scripts/check_environment_plan.py) with an explicit
   JSON plan. It reads no ambient environment and has no optional dependencies.
   It checks syntax only, not cross-feature compatibility or platform health.
4. Follow the [configuration reference](references/configuration.md) to separate
   environment variables, vLLM flags and `additional_config`. Do not invent a
   removed memory override or assume every boolean spelling means true.
5. Match the native extension and shader build to the tested runtime and source.
   Exact MLX ABI pairing matters; changing only a Python package or inspecting
   a selector cannot prove the loaded native path is current.
6. Choose the effective model route, not merely the advertised architecture.
   Keep checkpoint format, quantization, vision assets and processor identity
   together. If selection drifts between API and worker, restart with stable
   inputs rather than forcing a mismatched adapter.
7. If a native dependency/device is absent, return the concrete block. Do not
   install broad extras, execute setup scripts, download weights or enable a
   listener just to make a diagnostic look successful.

## Safe support example

Create `plan.json` containing only the selected explicit strings:

```json
{"VLLM_METAL_BACKEND":"mlx","VLLM_MLX_DEVICE":"gpu",
 "VLLM_METAL_DECODE_PIPELINE":"1","VLLM_METAL_SPEC_INGEST_CHUNK":"0"}
```

Run from this sub-skill directory:

```bash
python scripts/check_environment_plan.py plan.json
```

Success returns `syntax_screened_only`, always with native verification
`not_run`. Invalid choices/ranges return exit 2 and all selected-key errors.
Unknown keys and non-string values are rejected by this wrapper; upstream
validation has a different, complete engine environment registry.

## Choose the next owner

- For physical memory, lazy KV residency, host/disk tiers and restore/sleep,
  use [cache lifecycle](../cache-lifecycle/SKILL.md).
- For speculative pairing, deferred outputs, actual dispatch and measurement,
  use [qualification](../qualification/SKILL.md).
- For concrete import/build/model errors, read
  [troubleshooting](references/troubleshooting.md).

## Stop and report

Return inspected identity, intended/effective route, supporting evidence class,
the exact contradiction, smallest safe check, actual result and remaining gap.
Apple MLX/Metal or MPS/native model work remains `BLOCKED_REQUIRED_BACKEND`
without the actual compatible environment. No CPU import, syntax check, wheel
metadata or scaffold CI qualifies that engine/backend/device combination.
