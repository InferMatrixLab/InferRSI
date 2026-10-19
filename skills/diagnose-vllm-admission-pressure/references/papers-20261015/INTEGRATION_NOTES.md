> Supplier integration proposal, preserved as historical source context (2026-10-15). The local owner review and current two matrices govern acceptance; suggested follow-ups and permission statements below do not authorize work or describe the current inventory.

# Pack B integration proposal: admission, batching, preemption, migration, elasticity

Status: candidate. Empirical validation: not_run. Scope completed: **four papers only**. This directory contains newly authored synthesis/proposals, not source-paper caches or a framework change. Nothing is installed, deployed, reproduced, submitted as a PR, or edited in InferRSI.

## Deliverables and why they exist

- [Orca notes](notes/orca.md) and [exact readset](references/orca-readset.md): original iteration-level eligibility, selective batching, FCFS/reservation and static TP/PP baseline.
- [FastServe notes](notes/fastserve.md) and [exact readset](references/fastserve-readset.md): service-priority preemption, starvation mitigation, predicted host-state residency, distributed coordination and same-engine attribution.
- [Llumnix notes](notes/llumnix.md) and [exact readset](references/llumnix-readset.md): request relocation, virtual load/headroom, normal-class cost, drain/fill and evaluated-artifact limitations.
- [LoongServe notes](notes/loongserve.md) and [exact readset](references/loongserve-readset.md): ESP state placement, paid/unpaid migration boundaries, admission/opportunity costs, batching/DoP predictor and historical baseline limitations.
- [Assess serving preemption](../../../assess-serving-preemption/SKILL.md): one candidate justified by the coupled service-order/suspended-KV problem. It is not one generic skill per paper.
- [Evaluate elastic serving placement](../../../evaluate-elastic-serving-placement/SKILL.md): one branched candidate justified by the choice between moving request ownership and changing execution groups. It separates state-copy and ongoing attention communication rather than treating both as free migration.
- Three **hypothetical, unexecuted candidate cases**: [preemption under KV pressure](cases/preemption-under-kv-pressure.md), [cross-instance fragmentation](cases/migration-is-not-free-memory.md), [elastic group changes](cases/parallelism-change-with-state-cost.md). They test different decision traps; they are not observed incidents or benchmark results.
- One [knowledge brief](knowledge/scheduling-state-boundaries.md) connects the new mechanisms to prior work and preserves metric/fairness/state boundaries. It is not a new resource-operation matrix.

Every candidate instruction is P. F facts remain in notes/readsets with source context. Skill folder names match YAML `name`; metadata declares `status: candidate` and `empirical_validation: not_run`. Each skill includes its own `references/source-notes.md` with its two source branches and exact readsets so either folder can be consumed independently; the shared notes remain useful for pack-level review. Source caches are outside this deliverable tree. No author-linked implementation needed inspection.

## Incremental links to the completed artifacts

The existing artifacts were inspected before extraction; their six completed papers were not re-extracted or overwritten. Prior-artifact references below are semantic paths in `omnirsi-paper-intelligence-2026-10-15.zip`, not links to files bundled in this independent pack.

- Prior scheduling synthesis (`notes/scheduling.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`), prior scheduling skill (`choose-prefill-decode-schedule/SKILL.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`), its exact source notes (`choose-prefill-decode-schedule/references/source-notes.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`): retain Sarathi/DistServe's phase/interference/placement focus. New preemption skill answers the distinct service-order/unfinished-state question. The previously unread FastServe lead is completed here.
- Prior KV synthesis (`notes/kv.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`), KV block skill (`diagnose-kv-block-efficiency/SKILL.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`), PagedAttention evidence (`diagnose-kv-block-efficiency/references/source-notes.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`): retain physical-block/granularity/sharing/recovery decisions. Orca's original source clarifies that paper-era baseline; it does not replace PagedAttention's own reimplementation evidence. The unread Orca lead is completed.
- Prior KV transfer skill (`evaluate-kv-cache-transfer-gates/SKILL.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`), Mooncake evidence (`evaluate-kv-cache-transfer-gates/references/source-notes.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`): retain remote prefix reuse, phase-pool transfer and projected decode-load admission. Llumnix adds runtime request migration; LoongServe adds sequence-group changes. The prior unread LoongServe lead is completed, without claiming a measured ESP-versus-Mooncake CPP comparison.
- Prior integration notes (`INTEGRATION_NOTES.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`): preserve offload-related artifacts unchanged. Their historical matrix filename uncertainty is superseded for this proposal by the two official paths below; no legacy matrix file is edited.

## Matrix proposal 1: `docs/reference-matrix.md`

**P, proposed links only.** Add the four pinned original sources and the compact notes/exact readsets above. Associate them with the corresponding candidate skills and cases, keeping source version, actual-read locators, objective/assumptions, resource costs, evaluation denominator and unreported limitations available through those links. Use the official path `docs/reference-matrix.md`; do not add `repo-source-matrix.md`, another reference matrix, or unverified live anchors.

Recommended entry distinctions:
- Orca: iteration eligibility versus FCFS/reservation; engine/harness confounds; median normalized latency.
- FastServe: priority/preemption versus state recovery; same-engine evidence; aggregate-tail versus fairness gap.
- Llumnix: virtual load versus physical reservation; total transfer versus downtime; normal-class penalties; evaluated artifact lacks fault tolerance.
- LoongServe: fixed model partition versus dynamic sequence group; no-extra-migration versus normal collectives; paid decode contraction; configuration-specific normalized SLO and P90 evidence.

## Matrix proposal 2: `docs/searchspace-matrix.md`

**P, proposed semantic links only.** Use the official existing `docs/searchspace-matrix.md` with no invented anchors or additional matrix.

- **Accelerator × Observe/Diagnose:** queue/phase/service boundaries, batch composition, live/reserved/suspended KV, HBM admission, preemption/recompute, migration source/destination peaks, TP/PP versus ESP, local attention and intra-node GPU-link costs. Link both candidate skills.
- **Accelerator × Configure/Optimize/Verify:** proposed service-order/state-residency and elastic-group decisions, explicit progress/fairness/SLO checks, profiled group/batch choices and matched-resource verification. These cells link candidate decision plans, not validated knobs or permission to mutate systems.
- **RAM × Observe/Diagnose/Configure/Optimize/Verify:** FastServe's host-swapped state and Llumnix's host staging; host capacity/bandwidth, prefetched/suspended bytes, local copy overlap and pressure. LoongServe's distributed KV pool is device memory; do not map that pool to RAM merely because it is global.
- **Network × Observe/Diagnose/Configure/Optimize/Verify:** only actual cross-node request-state copies, SP/TP/PP traffic, contention/catch-up and topology-aware transfer choices. Include actual placement and measured transport. Same-host IPC and H2D/D2H are excluded; intra-node GPU links are Accelerator topology annotations.
- **OS:** no primary mechanism from these papers. CPU control overhead and OS analogies do not justify OS tuning. **SSD:** no evaluated tier or primary SSD mechanism in this four-paper pack.

No matrix edits have been performed. “Configure/Optimize” denotes a candidate future decision domain, not empirical promotion.

## Unread next gate and stop

The only selected unread literature lead is *Fairness in Serving Large Language Models* (VTC), found in FastServe §7/[52] and Llumnix §7/[55]. Its full text was not opened, and no findings from it were extracted. A later scope may examine service fairness; this pack makes no guarantee from that lead.

Stop after these four papers. Current-code capability, NPU portability, real execution, reproduction, heavier A/B work, scheduler implementation and framework integration remain unperformed separate gates. The next work here is review/integration of the supplied candidate artifacts, not automatic deployment.
