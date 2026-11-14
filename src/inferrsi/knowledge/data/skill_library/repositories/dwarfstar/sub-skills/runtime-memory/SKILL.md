---
name: runtime-memory
description: "Diagnose DwarfStar model fit, resident versus SSD expert placement, shared prefill workspace ownership and per-session memory without confusing cache capacity with total process memory."
license: NO_LICENSE
metadata:
  disco-role: operating
disable-model-invocation: true
---

# DwarfStar runtime and memory

Use this route when a model will not fit, a larger expert cache makes decoding
worse, extra server slots unexpectedly consume memory, or a multi-GPU placement
is being proposed. This is source-grounded candidate guidance, not a qualified
backend recipe. Required Metal/CUDA/ROCm inference evidence remains blocked
until obtained on the matching backend, model and workload.

## Establish the working set

Read the [memory ledger](references/memory-ledger.md) before choosing a knob.
Record these inputs, keeping unknown values explicit:

- Engine revision and actual backend/build; model family, exact checkpoint,
  GGUF tensor layout and quantization; optional vision/draft weights.
- Physical RAM, available device memory, topology and available local storage.
- Context limit, prefill chunk, planned slots, active slots and request lengths.
- Resident or SSD mode, requested and effective expert-cache budget, full-layer
  reservation, and cold/preloaded state.
- Measured startup, prefill, decode, append/replay and post-release phases.

Do not infer compatibility from a `.gguf` suffix, equal bit width, successful
metadata inspection or the existence of an SSD flag. DwarfStar is deliberately
specialized; unsupported checkpoints and backend/model combinations are a stop,
not a reason to relax checks or install a different engine silently.

## Procedure

1. **Separate representations.** Identify file-backed model bytes, resident
   non-routed weights, the routed-expert cache, vision/draft components and
   per-request state. File size alone neither proves fit nor predicts bandwidth.
   A mapped file may still generate page-cache pressure and I/O.
2. **Separate capacities.** A `GB`-suffixed expert-cache request is a binary-GiB
   target; a bare integer requests expert slots. Neither is a total-memory cap.
   Record the effective startup allocation rather than copying the request into
   a result. Include non-routed weights, graph/scratch and each slot's state.
3. **Resolve the owner and lifetime.** Shared prefill scratch may be counted once
   where enabled; KV, recurrent state, history and slot views remain logically
   isolated. Do not free a shared arena with a borrowing session, or assume
   sharing implies simultaneous unsafe access is permitted. Check capacity,
   embedding tier, borrower lifetime and graph invalidation boundaries.
4. **Budget the selected topology.** Metal GLM accounts for existing and planned
   sessions when evaluating the next graph. Ordinary CUDA placement assigns
   complete layers; in-process Flash TP splits routed experts inside device
   pairs while replicating other work. Summed VRAM is not one interchangeable
   allocation, and an even GPU count is not a fit proof.
5. **Choose one discriminating change.** For context/slot pressure, reduce that
   source of state before increasing expert cache. For expert misses with spare
   capacity, vary the cache while fixing context, slot count and preload state.
   For prefill I/O, compare selected-read ordering separately from next-layer
   prefetch. Never conflate this with changed routing or weight precision.
6. **Verify on the actual path.** First confirm startup's effective placement and
   memory report; then compare cold prefill, continued prefill and short decode
   separately. Preserve output/quality controls and failed allocations. CPU
   arithmetic/bookkeeping tests cannot clear an accelerator or storage-runtime
   gate. Do not publish an improvement from a successful launch alone.

For a concrete symptom and recovery, use
[troubleshooting](references/troubleshooting.md). Session identity, disk KV and
replay ownership belong to the sibling serving-state route; sampling and physical
distributed qualification belong to the sibling qualification route.

## Output and stop conditions

Return a phase/owner table with requested versus effective bytes, shared versus
per-slot state, overlap, release boundary, observed versus inferred values and
one falsifier for the proposed cause. State the activated backend path and any
fallback. Stop at missing compatible weights, unsupported placement, insufficient
mandatory memory, missing hardware or the authorized experiment boundary.

Do not disable memory guards, change system wired-memory limits, download model
weights, launch remote peers or treat this knowledge as execution permission.
Absent native evidence remains `BLOCKED_REQUIRED_BACKEND`; neither the candidate
nor an imported catalog entry is a performance or quality acceptance.
