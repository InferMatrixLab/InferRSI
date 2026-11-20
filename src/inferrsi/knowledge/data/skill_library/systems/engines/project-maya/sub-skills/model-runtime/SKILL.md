---
name: model-runtime
description: "Screen Project Maya's model-family dispatch, GGUF versus EXL3 pack contracts, expert-tier budgets and per-conversation memory ownership before attempting native inference."
license: NO_LICENSE
metadata:
  disco-role: operating
disable-model-invocation: true
---

# Maya model and runtime planning

Use this route for choosing the correct model-specific engine, diagnosing a
pack/layout mismatch, interpreting expert-cache slots, planning RAM/VRAM/SSD
residency, or explaining why a longer context or more simultaneous conversations
changes memory fit. This is source-derived **candidate guidance**, not a tested
CPU inference backend or a declaration that a checkpoint runs.

## Establish the contract first

Collect the exact source/build revision, release version, model/checkpoint
identity and byte hashes, family, quantization representation, pack metadata,
backend, device architecture/topology, compiler/runtime versions, actual context
and conversation count. A bare label such as `Maya-S`, a nominal bits-per-weight
number, or a successful file mapping does not identify a compatible model.

Read [model and memory](references/model-and-memory.md) for family-specific
boundaries and [troubleshooting](references/troubleshooting.md) for the smallest
discriminating checks. [Notices](references/notices.md) distinguish source code
from separately licensed models and optional components.

## Procedure

1. **Resolve family without guessing from the executable alone.** GLM uses
   `maya`, DeepSeek uses `maya-ds4`, MiniMax uses `maya-mm3`; the added Qwen
   CYBER-FROST route also uses `maya`. Inspect the installer family and the
   arguments together. `--pack` is not sufficient: Qwen's generated arguments
   include both `--pack` and `--ple-gguf`. Stop on conflicting identities rather
   than exploiting an upstream fallback to GLM.
2. **Freeze the actual representation.** Distinguish GGUF directory/type/offset
   contracts from EXL3 trellis/scale/codebook pieces, and keep each family with
   its own pack and geometry checks. Do not rename another family's metadata,
   reuse its slot stride, or treat equal bit width as layout compatibility.
   The Qwen route is inspected only at routing, setup-format and guard depth;
   its deeper kernels are not qualified here.
3. **Separate build eligibility from execution evidence.** Native inference
   needs the selected CUDA or HIP stack, supported hardware and actual model
   assets. CPU arithmetic/simulation tests cannot replace that evidence.
   Distinguish the source `VERSION` from historical CMake version constants and
   active architecture checks from stale comments.
4. **Create one physical-allocation ledger.** Identify unique allocations,
   separate copies from aliases, reserve room for dense weights, private state,
   scratch/staging, graphs and optional components, then allocate the expert
   tiers. On an APU, device aperture and host RAM are not two physical pools.
   On discrete cards, check each device and the host separately, not only their
   summed capacity. Count the maximum simultaneous live state, not just one
   active request or a model's download size.
5. **Interpret cache knobs in their own engine.** In GLM, `--expert-cache N`
   caps the first GPU's pool by N largest expert slots; it is not N bytes, N
   complete per-layer expert sets, or a promise of N permanently resident
   experts. Spares, prompt/vision lending, per-layer strides and later GPUs'
   automatic pools remain relevant. Do not transplant that interpretation into
   another family's staging or retained-conversation settings.
6. **Reconcile the planned and effective state.** GLM allocates extra sequence
   arenas before sizing its expert pool. MiniMax can reduce the effective
   context/staging plan, and parallel operation turns off KV streaming and
   DSpark. Record the engine's effective values and any reductions rather than
   reporting the requested settings as achieved. Recheck allocation peaks and
   reserve after the relevant native work, if such execution is authorized.

## Offline support

Run the bundled [audit_runtime_plan.py](scripts/audit_runtime_plan.py) on a small,
redacted planning projection:

```sh
python scripts/audit_runtime_plan.py --plan <PLAN_JSON>
```

It screens selected family markers and sums explicitly supplied allocation
estimates. Its success status is only `screened_ledger_only`; it does not inspect
weights, reproduce native budget selection, probe a device, compile an engine,
change configuration, or predict speed. The reference explains the input schema,
an example, exit codes and unchecked obligations.

Stop at a family/layout conflict, untrusted or unavailable weight bytes, an
overcommitted physical pool, unclear alias/lifetime ownership, missing native
resources or a task boundary requiring new authorization. Installation, model
download, setup/calibration and GPU execution are separate side-effecting work;
reading this skill or passing its helper does not authorize them.
