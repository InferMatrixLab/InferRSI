> Supplier integration proposal, preserved as historical source context (2026-10-15). The local owner review and current two matrices govern acceptance; suggested follow-ups and permission statements below do not authorize work or describe the current inventory.

# Pack C integration proposals

Status: candidate; empirical_validation: not_run. Independent five-paper, fulltext-derived expansion. F = source facts/models/results; P = proposed operational rules. No empirical validation, install, reproduction, framework run, hardware work, InferRSI modification, matrix edit or PR has occurred. Source PDFs/text/render caches are outside this deliverable tree and are not redistributed.

## Deliverable routes

- [Compact mechanism notes](notes/training-memory-scheduling.md): twelve mechanism cards with objective, assumptions, variables/constraints, action, benefit/cost, evidence, limits/counter-signals and candidate rule.
- [Exact readset and metric audit](references/source-readset.md): all five version pins, actual sections/equations/figures/tables read, rendered-page checks, author-reported workload/baseline/hardware/denominator and missing evidence.
- [Offload extension](knowledge/offload-delta.md): incremental ZO1–ZO3 knowledge for the existing skill.
- [Review cases](cases/paper-grounded-cases.md): hypothetical failure/decision cases, not executed evaluations.
- [plan-activation-residency](../../../plan-activation-residency/SKILL.md), [choose-parallel-training-plan](../../../choose-parallel-training-plan/SKILL.md), [assess-split-backward-schedule](../../../assess-split-backward-schedule/SKILL.md): three candidate skills, selected by distinct decision boundaries rather than one skill per paper.

P, grouping rationale: Checkmate and OLLA jointly inform retain/recompute/order/address choices and need one shared feasibility check. Alpa changes partition/mapping/resharding choices, so it remains separate from fixed-pipeline scheduling. Zero Bubble introduces an independent backward-order and optimizer-validation gate. ZeRO-Offload belongs in the earlier training-offload skill instead of duplicating its tensor-tier accounting. None is promoted or empirically validated.

## Existing artifacts inspected first

- Offload synthesis (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `notes/offload.md`)
- Offload source audit (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `notes/references/offload-source-notes.md`)
- Training-offload skill (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `diagnose-training-offload/SKILL.md`)
- Training-offload references (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `diagnose-training-offload/references/source-notes.md`)
- Previous integration notes (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `INTEGRATION_NOTES.md`)

These are semantic paths in the identified prior archive, not local hyperlinks or files bundled again. Resolve them to the approved repository inventory during integration. Existing ZeRO-Infinity coverage is retained: phase/class/tier budgets, prefetch/buffer pipelines, tiling, initialization and tied/external parameters. New evidence concerns CPU optimizer ownership/staleness, legal lifetime shortening, event-level rematerialization, static address packing, heterogeneous parallel plans and split-backward scheduling.

## P: Only the two official matrix destinations

The following are repository-relative link proposals, not local matrix edits or invented row IDs. Official paths are docs/reference-matrix.md and docs/searchspace-matrix.md. Any older matrix-path suggestion is superseded by these two official destinations. Live rows/anchors were not inspected. There is no third matrix.

For docs/reference-matrix.md:
- Add ZeRO-Offload 2101.06840v1 → ZO1–ZO3 → offload extension and readset; mark the old next-gate lead as read only when integration is approved.
- Add Checkmate 1910.02653v3 → CM1–CM2 and OLLA 2210.12924v2 → OL1–OL2 → activation-residency skill/readset. OLLA likewise advances from the earlier unread lead after approved integration.
- Add Alpa 2201.12023v3 → AL1–AL2 → parallel-plan skill/readset.
- Add Zero Bubble 2401.10241v1 → ZB1–ZB3 → split-backward skill/readset.

For docs/searchspace-matrix.md, propose semantic cross-links using existing taxonomy/row IDs after local reconciliation:
- Accelerator × Observe/Diagnose/Optimize/Verify: live ranges, per-event capacity, rematerialization, reserved-address packing, shard/mesh feasibility, pipeline passes and total device memory.
- RAM/host-compute evidence × Observe/Diagnose/Optimize/Verify: optimizer residency/update/copy and host-resource ownership, extending the existing offload entry. This is not an additional SSD technique.
- Communication/Network × Observe/Diagnose/Optimize/Verify only for actual inter-node reduce-scatter/allgather, cross-mesh resharding or pipeline transfers. Local GPU collectives remain Accelerator topology. H2D/D2H and same-host IPC do not become Network entries.
- Configure, where the existing matrix uses it, must point to a later separately authorized current-implementation gate. These paper plans do not prove current framework/NPU support. No generic OS/VM-tuning or persistent recovery-checkpoint rule follows from this pack.

## Evidence boundaries that must survive integration

- Checkmate's headline batch-capacity increase is constrained model evidence; OLLA's runtime saving is estimated over an assumed million iterations. Neither should become a measured end-to-end speed claim.
- Alpa is hierarchical and approximate in important respects: zero compute-cost simplification inside intra-op search, omitted inter-stage transfer, external microbatch count, static shapes/schedules. Do not advertise globally optimal mixed-parallel execution.
- Zero Bubble's calculated bubble rates, ideal formulas and measured throughput are distinct. Similar activation caps do not mean identical total memory. Table 6's fixed-global-batch comparison is preferable to Table 11's ambiguous/changing-batch rows.
- ZeRO-Offload DPU changes update semantics; Zero Bubble post-validation intends to preserve them through validation/rollback. Keep separate gates.
- Source inconsistencies are flagged rather than repaired: ZeRO-Offload Table 1; Alpa Wide-ResNet size rounding; Zero Bubble Table 11 microbatch labels and missing Table 9 time units.

## Unread next-gate leads

These are leads named in the five papers' references, not additional reviewed evidence. Stop the current batch at five papers.

- AutoTM (ZeRO-Offload reference 8): joint tensor movement with heterogeneous memory could address transfer decisions absent from Checkmate/OLLA; no mechanism imported here.
- Capuchin (ZeRO-Offload reference 17): a possible recomputation-plus-movement comparison; not read.
- Reducing Activation Recomputation in Large Transformer Models (Zero Bubble reference list): a possible check on Transformer-specific saved-tensor assumptions; not read.
- Piper (Alpa related work): an alternate mixed-parallel search boundary; not read.

A later gate may also review author-linked implementation at an explicit revision for compatibility. No such source inspection or validation is implied by this delivery.
