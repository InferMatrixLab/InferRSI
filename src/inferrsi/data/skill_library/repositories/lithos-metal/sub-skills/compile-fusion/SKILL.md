---
name: compile-fusion
description: "Audit Lithos Metal task compilation, chip-qualified fusion, normalized controls, ICB barriers and scratch lifetimes when changing a recipe or diagnosing a fused kernel."
---

# Compile and qualify a fusion region

## Trigger and evidence

Use for missing kernel coverage, a recipe rejected by shape/layout checks,
incorrect fusion, synchronization failures or apparent dispatch reductions.
Source-derived candidate; empirical validation **not_run**. Read the
[root](../../SKILL.md) for version scope and the
[source readset](../../references/source-notes.md) for exact evidence.

## Inputs and owner

Capture target/draft operation graph, packed formats/layouts, active and compiled
row bounds, context capacity, selected chip/backend/config digest, numerical
options, region recipe and emitted `Program`. Identify a model-graph change
separately from a chip schedule change. Do not add model-name conditions to a
generic compiler to bypass a failing contract.

## Decision procedure

1. Follow model lowering → typed graph checks/passes → coverage guard → emitted
   kernels/buffers/ops → backend finalization → runtime ICB. Missing bindings
   fail before execution; register an implementation or retain a supported
   route instead of suppressing `CoverageError`.
2. Establish the region boundary. Layer mixer fusion can include projection,
   mixer core/reduction, output/residual/normalization; MLP and draft/context
   work can be separate. Read [mechanisms](references/mechanisms.md) to map
   actual task roles and avoid assuming one kernel spans the model.
3. Build a dependency ledger for every buffer: producer, consumers, byte/view
   alias, role and lifetime. `meta['writes']` enables hazard reasoning;
   missing writes metadata is conservative. Check first-step and inter-step
   dependencies as well as dependencies within a region.
4. Compare original/native, normalized multi-dispatch and fused programs when
   studying fusion itself. Normalization changes loading/layout/geometry, so
   native-to-fused timing combines effects. Keep decoded weights and rounding
   mode matched. `commute_norm=False` is a separate numerical control.
5. Preserve StepState predicates, bounded worker synchronization and recurrent
   commit passes. Worker count is a logical launch parameter, not a guarantee
   of physical core placement or simultaneous residency. Do not remove a
   barrier based only on an observed launch order.
6. If scratch is reused, prove a known producer and later consumer with disjoint
   lifetimes. Keep initialized/input/output, persistent state, acceptance logs,
   ring and parameters out of unsafe aliasing. Recompute hazards after renaming.
7. Check CPU graph/barrier/arena contracts, then actual Metal equivalence and
   model continuation/state before benchmarking the complete claimed interval.
   Report unsupported shapes and unqualified chip variants separately.

## Counter-signals and outputs

A native fallback is expected when an eligible measured recipe is absent.
Fewer dispatches can lose to synchronization, normalization, occupancy or memory
cost. A shader compile success does not prove binding bounds or numerics.
`barriers='all'` is an ordering control, not a cure for unsafe cross-worker
publication inside one megakernel.

Return a bounded region/dependency ledger, chosen control, eligibility/fallback
decision and validation gaps. Read [troubleshooting](references/troubleshooting.md)
for concrete coverage, geometry, barrier and scratch failures. Changing a
recipe requires its own qualified device evidence; this skill supplies no
universal tile sizes, performance gates or measured gains.
