# Keep bounds, predictions and observations distinct

Status: candidate; empirical_validation: not_run. This is a **P** integration supplement to the existing `performance-ceiling-analysis` three levels (analytical, empirical, Amdahl), not a fourth ceiling or a replacement. Existing lineage is recorded in the supplied Reference Matrix at revision4d61d2c: LLM-Viewer1893e4b, ERT0771fa9 and TensorRT-LLMf33e0e5fd. Those underlying artifacts were not re-mined here.

## Four evidence labels, without changing the existing ceiling hierarchy

1. **Conditional physical lower bound / capacity bound.** State workload, required FLOPs/bytes, datatype, resource, topology and assumptions. A roofline-style runtime floor max(required FLOPs/peak FLOP/s, required bytes/peak bytes/s) is conditional on those counts and peak definitions. It does not predict queueing, launch overhead, synchronization or realized utilization. Changing semantics, caching, sparsity or mandatory traffic changes the bound itself. Do not add compute and transfer floors when their overlap is unknown; do not call an observed bandwidth peak a universal physical limit.
2. **Empirical attainable envelope.** A measured roofline or best known kernel is hardware/software/workload-specific evidence. It may be useful for headroom, but a microbenchmark envelope is neither a proof of global optimality nor a guaranteed application target. Nothing in this pack supplies missing B300 or NPU peak/bandwidth measurements.
3. **Conditional whole-system impact.** For an unchanged serial decomposition with fraction f accelerated s-fold, Amdahl's expression1/((1−f)+f/s) translates local improvement into conditional end-to-end speedup. The maximum removable fraction f is useful for triage. Concurrent traces, queueing, batching and bottleneck migration violate a naive additive-time interpretation; identify exposed critical-path time before applying it.
4. **Empirical prediction or search heuristic.** Vidur's learned latency estimates, its equivalent-prefill reduction, FlashVector's time-share×expected-gain ranking, and an agent's extrapolated benefit are predictions/heuristics. They are not additional physical ceilings. Preserve calibration domain, uncertainty and observed validation errors beside every predicted shortlist rank.

These labels answer different questions: impossible under the stated work/resource contract; attained by a matching measurement; possible whole-system impact under a decomposition; predicted candidate worth measuring. A candidate may have all four records, but one never substitutes for another.

## Incremental requirements from this pack

- **[Vidur V1–V3](../references/vidur.md):** attach phase/dependency signatures, request-state/queueing regime, interpolation versus extrapolation, and calibration residuals. A low operator error cannot certify near-capacity SLOs.
- **[InferenceBench I1–I3](../references/inferencebench.md):** final deployment validity, evaluation integrity and equal optimization budgets matter independently of peak speed. An impossible-looking measurement triggers an audit; it is not itself sufficient evidence of cheating.
- **[FlashVector F1–F4](../references/flashvector.md):** local time share, measurable noise and full-stack behavior gate promotion. Re-profile after changes; include host preprocessing and retune instance/batch settings when the bottleneck moves.
- **[Agentic Kernel Optimization](../references/agentic-kernel.md):** shape/regime-specific paths and empirical profile evidence can redirect search. Vendor-kernel comparisons and PyTorch comparisons require separate denominators.

## P: minimal candidate decision record

Record objective and absolute constraints; valid-work/quality contract; exact input/model/hardware/software identities; physical feasibility assumptions; empirical envelope provenance; predicted effect plus domain/uncertainty; measured exposed time share; candidate family and changed variables; setup/compile/measurement/finalization cost; rollback artifact; source locator; status.

Use statuses `unmodeled`, `predicted`, `measured-invalid`, `measured-inconclusive`, `measured-valid`, `final-artifact-verified` only as proposed local vocabulary. Pack contents remain candidate/not_run and do not instantiate any of those measured states. No new workflow engine or tracker is proposed.

## P: stopping and redirection rules

- Stop claiming a rank when predicted differences are smaller than known error or when either candidate lies outside calibration coverage. Request the next discriminating observation.
- If even the conditional removable fraction is below the locally established detection threshold, park that target and inspect a larger exposed component. Keep setup cost and uncertainty explicit.
- If measurements reverse the predicted bottleneck, revise the model rather than tuning the same family harder by default. Do not discard a whole technique because one incompatible configuration fails.
- If an experiment regresses quality, semantics or final validity, restore the last valid artifact. A small fast probe is not final acceptance.
- If improvement disappears in a matched full-stack workload, report a local gain and reject service-level promotion. An honest null result is useful knowledge.
