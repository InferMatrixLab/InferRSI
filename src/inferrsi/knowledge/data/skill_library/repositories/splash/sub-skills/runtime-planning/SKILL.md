---
name: runtime-planning
description: "Plan Splash model-format compatibility, Metal and host memory, streamed experts and PLE rows, context bounds and KV/recurrent precision with explicit Apple-backend limits."
license: NO_LICENSE
metadata:
  disco-role: operating
disable-model-invocation: true
---

# Splash runtime planning

Use this route before selecting a model, interpreting a memory refusal, changing
`--max-memory`, streaming experts/PLE rows, or altering KV/recurrent precision.
Splash's native runtime requires Apple Silicon M3 or newer and macOS 26.4 or
later at the inspected revision. A Python parser working on another OS does
not make Metal, ANE or model execution available.

This is a source-grounded candidate. Actual Metal/ANE allocations, SSD/model
state, quality and service behavior remain `BLOCKED_REQUIRED_BACKEND` where
matching native evidence is unavailable. Reading it grants no installation,
download, server-launch or experiment authority.

## Inputs and outputs

Record engine revision, macOS/SDK/chip, physical memory and recommended Metal
working set; exact target files/configuration, formats and draft identity;
vision and ANE selection; requested memory/context, expert/PLE/hot-KV settings;
KV and recurrent formats, disk-cache policy and workload/concurrency.

Produce a representation/owner ledger, effective memory/context bounds, the
reason for any refusal/fallback, and one smallest discriminating check. Keep
requested sizes, planned storage, actual device allocations and process RSS
distinct. Use [memory and formats](references/memory-and-formats.md) for the
complete bundled contract and [troubleshooting](references/troubleshooting.md)
for concrete failures.

## Procedure

1. **Identify, do not guess, the family.** Compatibility follows target
   configuration and scalar/tensor metadata, not repository names, a model-card
   label or nominal bit width. Check target and DFlash2 draft together. A valid
   header/configuration is not a complete tensor-shape, payload or native-run
   check. Whole-unquantized GGUFs and unsupported per-tensor formats stop here.
2. **Resolve the format-dependent footprint.** Count target, draft and optional
   vision weights, runtime arenas, ANE split and disk-state staging. Streaming
   changes the loaded representation and scratch requirements; derive the
   final plan from the loaded formats rather than subtracting file size from
   RAM. A `Weights loaded again` message can mean reconciliation with the
   loaded arena geometry, not an unbounded leak.
3. **Apply floors before optional capacity.** The planner protects fixed
   storage, one lane's state, KV runway, smallest streaming stores and, where
   supported, spill floors. Only the remainder can fund expert/PLE stores,
   additional states and KV. A requested store below its minimum is an error,
   not an invitation to bypass it.
4. **Distinguish the budgets.** `--max-memory` can lower, not raise, the
   automatic OS-safe ceiling. It is not combined process RSS. The PLE host row
   cache is nevertheless charged alongside Metal to the engine plan; additional
   host scratch, metadata and allocator overhead still exist. Preserve host
   pressure, reservations and runtime audit checks instead of equating a
   syntactically valid number with a safe allocation.
5. **Interpret controls literally.** `--ple-memory off` and
   `--expert-memory off` load the whole corresponding part; they do not disable
   its weights. `--sparse-kv-memory` has a floor and no `off`. `--max-cache-disk 0`
   disables the disk tier. Context units differ from byte units. For safe
   offline syntax validation, run the bundled
   [budget parser](scripts/parse_budget.py); it does not calculate fit.
6. **Treat precision as a semantic condition.** Target KV `int8`/`bf16` is
   independent of recurrent state `fp32`/`bf16`. BF16 state keeps FP32 compute
   but rounds at stored chunk/capture/decode boundaries, so chunking and
   checkpoint policy can affect final bits. Restart to change either format
   and preserve format-specific cache identity; do not call the formats
   numerically interchangeable.
7. **Check the actual selected path.** Capture startup's effective plan and
   warnings, the memory audit and `/status` bounds. At an authorized native
   run, distinguish model, resident-memory, spill-floor and disk limits; compare
   cold/warm phases and interleaved requests. Source/header/parser checks are
   useful prerequisites, never substitutes for that evidence.

## Safe offline support

From this skill's directory, for example:

```sh
python scripts/parse_budget.py --kind max-memory 2.5G
python scripts/parse_budget.py --kind ple-memory off
python scripts/parse_budget.py --kind max-cache-disk 0
```

The helper prints normalized JSON and performs no network, file mutation,
model import, device probing or allocation. It adapts only the pinned byte-size
parser contract; it is not Splash's installer, context parser or memory planner.

Stop at unsupported hardware/format/draft, missing actual model metadata,
mandatory floors exceeding the safe budget, missing native verification or a
required action outside authorization. Do not alter OS limits, disable guards,
download a smaller model silently or promote the candidate from parser success.
