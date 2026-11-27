# Paper-grounded review cases

Status: candidate; empirical_validation: not_run. All scenarios and proposed decisions below are P, hypothetical review cases. Their F evidence is historical and linked. These were not executed as tests and are not claims about an actual user workload.

## C1. OOM with low live-byte demand but high reserved memory

Signal: a stable graph's phase-aligned live tensor total is well below the allocator peak, and the requested large allocation cannot fit an available range.

Decision: distinguish reserved-byte fragmentation from unavoidable live data. Consider legal address reuse after lifetime proof before buying transfer/recomputation overhead. Keep size/alignment/workspace and asynchronous overlap in the accounting. Do not assume a reserved/live difference alone proves external fragmentation; cached free blocks and unaccounted workspaces must be resolved.

F basis: OLLA §§3.3–3.5, §5.4/Fig. 8. Its fragmentation percentage is (reserved−resident)/reserved at the reserved-memory peak, not a universal multiplier. Acceptance idea: later evidence shows the same graph's peak reserved memory falls without illegal overlapping aliases or a latency regression. Stop if shapes/lifetimes are unstable. [OL2](../notes/training-memory-scheduling.md)

## C2. Large forward activations remain live across a nearly linear graph

Signal: activations dominate at large batch, few independent operators can be reordered, and CPU offload would expose transfer waits.

Decision: propose selective retain/recompute alternatives with event-level peak memory, adding recompute cost to the same critical-path ledger. Do not expect OLLA's small-batch gradient-order savings to carry over. Do not change global batch merely because more input could fit.

F basis: OLLA §5.3 limits; Checkmate §4/Eqs. 1–9 and Fig. 5. Acceptance idea: same-model/batch/precision proposal preserves dependencies, fits worst-case memory including output-before-release, and has a justified step-time benefit versus supplied offload costs. Missing transfer/operator timing leaves the performance choice unresolved. [CM1/OL1](../notes/training-memory-scheduling.md)

## C3. Approximate rematerialization has low objective cost but exceeds memory

Signal: rounded retention plan has dependency-valid recomputations and a favorable FLOP estimate, yet its replayed lifetime ledger exceeds the actual budget.

Decision: reject feasibility, regardless of closeness to an LP/ILP objective. Record dependency validity and capacity violation separately. A different margin, policy or exact incumbent may be considered on paper; a solver timeout does not establish no feasible plan exists.

F basis: Checkmate §5.3 explicitly does not preserve capacity under rounding; Table 2 averages ratios only across feasible budgets. Acceptance idea: an actual feasible schedule/capacity proof under the chosen accounting, not a 1.06 mean-cost claim. [CM2](../notes/training-memory-scheduling.md)

## C4. One pipeline stage is weight-heavy while earlier stages are activation-heavy

Signal: uniform layer counts create per-rank OOM or a bottleneck despite spare memory elsewhere; the cluster has fast local links and slower inter-node links.

Decision: compare uneven stages/mesh sizes and varying operator shard axes. Include layout conversion and in-flight activations; prefer a simple uniform fallback if the model is homogeneous or planning cannot amortize. Do not substitute weak-scaling PFLOP/s for fixed-work speed.

F basis: Alpa §5/Eqs. 2–5, §8.3, §8.6/Fig. 12; 16-GPU Wide-ResNet uses 4/4/8-GPU stages. Acceptance idea: same global batch and total hardware, actual cross-node transfer included, all rank peaks feasible, and useful whole-step improvement. [AL1/AL2](../notes/training-memory-scheduling.md)

## C5. Lower modeled pipeline bubbles require smaller microbatches

Signal: a larger activation cap allows ZB-2p-like scheduling only by reducing microbatch size; small kernels lose utilization.

Decision: compare 1F1B, capped split backward, V placement and b/2 plus 2m at fixed global batch and similar total memory. Choose useful throughput, not zero-idle theory. Do not splice Table 4's different memory budgets with Table 11's changing global batches.

F basis: Zero Bubble §6.1/Table 6; 6.2B favors ZB-2p* over V while 28.3B's listed base b2,m96 favors V slightly. Table 7 demonstrates microbatch sensitivity but changes global batch. Acceptance idea: matched-workload latency/throughput, per-pass timing and actual peaks; computed bubble rate is supporting model evidence only. [ZB1/ZB2](../notes/training-memory-scheduling.md)

## C6. "Overlap the optimizer" hides two different semantic choices

Signal: a plan proposes overlapping next-step forward work with optimizer processing and labels the change a harmless schedule optimization.

Decision: ask which mechanism is intended. ZeRO-Offload DPU deliberately accepts one-step stale updates; Zero Bubble post-validation intends synchronous semantics with complete global validation and rollback/redo. Neither permits dropping clipping/NaN decisions. Keep ordinary synchronized execution as the fallback until the selected mechanism's semantics and implementation evidence are explicit.

F basis: ZeRO-Offload §5.2/§6.2.4 versus Zero Bubble §4/Appendix C and Table 10. Acceptance idea: DPU requires separately approved training-semantics/quality criteria; post-validation requires numerical rollback, validation and dependent-work coverage. Historical BERT F1 or fixed-seed loss matching is insufficient for universal approval. [ZO3/ZB3](../notes/training-memory-scheduling.md)
