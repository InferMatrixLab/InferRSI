---
name: runtime-kv-limits
description: "Investigate MLC compiled versus runtime context, prefill and batch limits, generic-cache lowering and automatic-capacity boundaries without treating metadata minima or device memory attributes as allocation or Metal cache correctness."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Compiled limits versus runtime cache configuration

Use this source-derived candidate for a configuration that exceeds compiled
shape limits, fails memory estimation, or changes prefill without reducing
workspace. It is not a complete engine admission validator or a capacity model.

## Follow the source of each value

1. Record MLC and its TVM gitlink, compiled model metadata, runtime model JSON,
   nested compile-time model config, engine overrides/mode and actual device.
   The same field name can describe a compiled bound, runtime preference or
   separately supplied engine override.
2. Read [limit reconciliation](references/limits-and-workspace.md).
   GetModelConfigLimits clamps a model's runtime sentinel/excess to a finite
   compiled context/prefill limit, then takes minima across models. Unbounded
   context and finite positive prefill/batch have different rules.
3. Use the [declaration helper](scripts/audit_kv_limit_declarations.py) and its
   [schema](references/helper-contract.md) for selected clamp/minimum checks:

   ```bash
   python scripts/audit_kv_limit_declarations.py --example
   python scripts/audit_kv_limit_declarations.py --example | python scripts/audit_kv_limit_declarations.py -
   ```

   Resolve paths from this installed sub-skill. Input is explicit synthetic or
   anonymized caller metadata. No MLC/TVM import, allocator, model or device is
   accessed. Output is not the effective engine configuration or an estimate
   of bytes/tokens that fit.
4. Reconcile workspace with the **nested compiled** prefill input, not only a
   smaller runtime prefill value. Preserve parameter, temporary, KV, auxiliary,
   model and logit-processor terms as distinct source assumptions; the helper
   intentionally does not reproduce the memory estimator.
5. Trace [generic-cache lowering](references/cache-lowering-and-evidence.md)
   before attributing a kernel. Metal uses the target's TIR cache path; the
   optional FlashInfer construction is CUDA-gated. Generic IR/metadata is not
   proof of cache append/fork/sliding behavior or actual Metal dispatch.
6. Distinguish automatic choices from explicit overrides. The source's Metal
   automatic-capacity cap is not a universal admission limit. A reported Metal
   working-set attribute is not authenticated free/unified memory or a
   successful allocation. Check the actual override/validation path rather
   than inventing rejection from an automatic branch.

## Return the unresolved boundary

Use [troubleshooting](references/troubleshooting.md) to name the conflicting
compiled/runtime source and smallest native discriminator. Keep declared
normalization, source estimator assumptions, actual allocation/cache behavior,
model output and service performance separate. Required compiler/native/cache
and model/fit/quality/service evidence remains `BLOCKED_REQUIRED_BACKEND / not_run`.
The [Metal build/runtime route](../metal-build-runtime/SKILL.md) owns SDK,
module and stream identity; the [artifact contract](../artifact-contract/SKILL.md)
owns parameter-only schema/resource declarations, not runtime KV allocation.
