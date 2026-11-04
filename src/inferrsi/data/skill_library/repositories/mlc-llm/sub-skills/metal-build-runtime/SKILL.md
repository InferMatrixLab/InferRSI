---
name: metal-build-runtime
description: "Investigate MLC Apple target, SDK, host, export and system-prefix contracts and pinned TVM Metal module/storage/stream boundaries without treating codegen, serializable fallback or submitted work as runnable completed GPU execution."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Apple target to actual Metal runtime

Use this source-derived candidate for an artifact that compiles/exports but
fails to load, a wrong SDK/ABI/prefix, or an incorrect copy/completion claim.
Low-level Metal belongs to MLC's pinned TVM fork, not to MLC main alone.

## Follow compilation, module and execution separately

1. Record both source revisions, target/host, SDK/architecture, output suffix,
   prefix, compiler callback/payload format and actual runtime build/device.
   A Metal target string or module kind is not evidence of native availability.
2. Reconcile [Apple presets and export](references/targets-and-export.md).
   iPhone/macabi static tar, x86-64 dylib and generic suffix-based builds differ.
   macabi's host triple and Metal SDK are distinct. Preserve the literal
   explicit-prefix/colon-hint behavior instead of silently normalizing it.
3. Use the [declaration helper](scripts/audit_apple_target_declarations.py) with
   its [bounded schema](references/helper-contract.md):

   ```bash
   python scripts/audit_apple_target_declarations.py --example
   python scripts/audit_apple_target_declarations.py --example | python scripts/audit_apple_target_declarations.py -
   ```

   Resolve paths from the installed sub-skill. This screens six source string
   contracts, not SDK availability, a compiled artifact or a device. It imports
   neither MLC nor TVM and performs no autodetection, compilation or binary read.
4. Check [module payload and runnable state](references/modules-and-streams.md).
   The same kind=metal can describe a serializable non-runnable fallback.
   InspectSource/export success, actual runtime factory, kernel loading,
   pipeline creation, dispatch and completion are different observations.
5. Preserve format declarations: legacy callback bytes/strings mean metallib;
   explicit payload/format can select source metal. Mixed formats are rejected.
   The inspection source map is not serialized; absent source after load does
   not alone mean lost executable payload.
6. Trace the selected buffer and stream branch. Private GPU storage, shared
   staging, queued copies, flush and wait are not interchangeable under unified
   memory. Default-stream counters and pending-work checks are not arbitrary
   cross-stream lifetime or per-request telemetry proofs.
7. Use [native discriminators](references/native-evidence.md), retaining exact
   assertions and skips. A test named export/load may only export; a GPU marker
   may guard a compile-rejection assertion. Source inspection cannot supply
   unexecuted native allocation, synchronization or numerical results.

## Stop at the evidence boundary

Use [troubleshooting](references/troubleshooting.md) to identify the failing
stage and smallest required native observation. Compiler, real module load,
Metal dispatch/sync/cache/model/fit/quality/service evidence remains
`BLOCKED_REQUIRED_BACKEND / not_run`. The [artifact contract](../artifact-contract/SKILL.md)
owns manifest/schema links; [runtime KV limits](../runtime-kv-limits/SKILL.md)
owns configuration/workspace provenance, not this helper's target strings.
