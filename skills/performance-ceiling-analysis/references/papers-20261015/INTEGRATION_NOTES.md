> Supplier integration proposal, preserved as historical source context (2026-10-15). The local owner review and current two matrices govern acceptance; suggested follow-ups and permission statements below do not authorize work or describe the current inventory.

# Pack A integration notes

**Candidate; empirical_validation:not_run.** Independently deliverable read-only extraction. No repository/matrix edit or empirical promotion was performed. Three candidate skills have valid metadata and skill-local evidence; the knowledge supplement and cases support merging into existing artifacts rather than inflating the inventory.

## Read first

[Mechanism summary](MECHANISMS.md) → [exact readset](READSET.md) → [source audits](references/vidur.md). Other paper audits: [InferenceBench](references/inferencebench.md), [FlashVector](references/flashvector.md), [Agentic Kernel Optimization](references/agentic-kernel.md). [Prior artifact overlap](references/prior-coverage.md) records existing skill destinations and exact earlier bundle locators without inventing current repository URLs.

## Only two matrix destinations

1. **Reference Matrix: `docs/reference-matrix.md`.** Add pinned original-source records with exact inspected scope, F/P status, unresolved source discrepancies and linked artifacts. Methodology belongs in its existing§2; do not create a third matrix or force methodology into hardware columns.
2. **SearchSpace Matrix: `docs/searchspace-matrix.md`.** Cross-link the resulting existing skill/case entries to relevant observation/diagnosis/search/verification gates. No automatic green-cell promotion from paper reading. Resource-level coverage and empirical validation remain distinct.

Role classification should preserve one source identity even where a paper has two uses:

- **Vidur:** primary systems-modeling reference; simulation dependency/memory/scheduling design can appear in§1 with scope explicitly limited to the paper. Calibration and constrained-search procedure cross-links belong in§2. It establishes no current engine implementation or target-hardware calibration.
- **InferenceBench:** evaluation/search methodology in§2. H100 is its experimental setting, not justification for filling accelerator/RAM/SSD/OS capability cells.
- **FlashVector:** cross-layer search/verification methodology in§2; optional§1 case links may record the specific server/host/graph/kernel mechanisms actually described. Keep case evidence narrow; do not infer networking from gRPC or shared memory. Same paper, not independent corroboration.
- **Agentic Kernel Optimization:** search/governance methodology in§2 and optional§1 CUDA mechanism case references. B200 profiler cases are hardware-specific evidence; no NPU or latest-runtime claim. Preserve the distinction between implemented mechanisms and author-proposed future directions.

## Candidate bundles and merge destinations

- [calibrate-serving-simulation](../../../calibrate-serving-simulation/SKILL.md) with [local evidence](../../../calibrate-serving-simulation/references/source-notes.md): extend `performance-ceiling-analysis`, `optimization-search-policy` and `inference-benchmark-design`. Increment: prediction-domain/queueing validation and joint-SLO shortlisting. Earlier `choose-prefill-decode-schedule` already covers Sarathi/DistServe trade-offs; link this calibration gate instead of re-extracting those.
- [govern-optimization-experiments](govern-optimization-experiments/procedure.md) with [local evidence](govern-optimization-experiments/references/source-notes.md): extend `optimization-search-policy`, `inference-benchmark-design`, `dense-performance-evidence`, `kernel-writing-guide`. Increment: budget fairness, measured-search breadth, quality-versus-integrity, best-seen-versus-final artifact, regime-specific correctness and stalled-direction correction.
- [redirect-cross-layer-optimization](redirect-cross-layer-optimization/procedure.md) with [local evidence](redirect-cross-layer-optimization/references/source-notes.md): extend `performance-ceiling-analysis`, host-overhead profiling/optimization and `inference-optimization-casebook`. Increment: noise/impact gates, semantic work elimination, host materialization/assembly cases, shape-regime dispatch and post-change retuning.

Each skill folder is self-contained for selective consumption; parent-pack links are optional context. Three distinct trigger/decision contracts justify these folders. Integration may merge them into existing skills and retain source references/cases rather than install all three as separate skills. No fixed skill count is an objective.

## Knowledge and cases

- [Bounds/predictions supplement](knowledge/bounds-predictions-and-decisions.md) preserves the existing analytical/empirical/Amdahl hierarchy and adds evidence labels/calibration fields. It supplies no missing NPU/B300 measurements.
- [Six decision cases](cases/decision-cases.md) exercise near-capacity error, lost final validity, fake timing boundaries, CPU redirection, an SLO-inconsistent table row and shortcut-dominated kernel averages. These are candidate review cases, not tests run against InferRSI.

## Source warnings that must survive distillation

- Vidur AppendixA includes12.65% maximum error; do not keep only the abstract's less-than9% statement. The wider simulated scheduler/PP search is not all independently fidelity-validated by default-vLLM experiments.
- InferenceBench's cross-engine grid consists of separate two-hour runs; do not compare the combined grid with one agent's two-hour search as if budgets were equal. Its ScenarioD concurrency differs between G.2 prose and the formal specification.
- FlashVector ModelB's selected p99=271ms exceeds its stated250ms SLO; compliance unresolved. Its local/full-stack acceptance descriptions also differ in strictness. No separate causal ablations establish every agent-loop component.
- Agentic Kernel's local PyTorch-relative averages differ from official FlashInfer-relative results. Main/appendix metrics conflict for MoE utilization, attention shared memory and TopK representative input. Cumulative token trajectories are not isolated ablations or a learned token-cost model.
- InferenceBench and Agentic Kernel date/month anomalies remain unresolved. Never silently replace their IDs or manufacture dates.

## Next gate: unread, optional, separate authorization/scope

Stop at the four papers in this pack. Candidate future reads are source leads only:

- Vidur§8's Habitat/Daydream: how profiling and dependency graphs bound prediction transfer; do not re-mine the already-extracted roofline hierarchy without a concrete gap.
- FlashVector reference27, Morphling: whether systematic configuration sampling can replace heuristic trial choice under bounded budget. Reference only; paper not opened.
- Agentic Kernel's FlashInfer-Bench2601.00227: exact benchmark aggregation and correctness/cache contracts behind official-vs-local denominators. Its implementation and paper remain unread here.

## Static validation boundary

Check frontmatter/name-to-folder match, local Markdown targets, self-contained skill dependencies, versioned paper links, source-cache exclusion and F/P/not_run labels. Those checks establish packaging quality only. They are not performance, implementation or hardware validation.
