# Govern optimization experiments

Use when an agent must model, shortlist, measure and redirect a finite optimization search. Merge the incremental gates into existing `optimization-search-policy`, `inference-benchmark-design`, `dense-performance-evidence` and `kernel-writing-guide` rather than deploying duplicate policies. All steps below are P proposals; empirical_validation: not_run.

Read [InferenceBench](references/source-notes.md), [Agentic Kernel Optimization](references/source-notes.md), and [evidence distinctions](references/source-notes.md).

## Procedure (P)

1. Freeze valid work: model weights, allowed approximations, output shape/length, quality limits, true timing boundaries and forbidden shortcuts. Record workload hashes and developer-versus-held-out evaluation split. Do not interpret an accuracy pass as proof that the timing path performed the required work.
2. Establish a valid incumbent and its complete restartable artifact: code/config hashes, launcher, compatible dependencies, initialization/cache state, measurements, correctness evidence and runtime health. Retain the prior incumbent untouched while exploring.
3. Make a bounded candidate list across distinct mechanisms supported by current evidence. Record expected bottleneck effect, assumptions, uncertainty, setup/compile/evaluation costs and abort/rollback criteria. A recalled recipe is a hypothesis. An extra installation or alternative stack still needs authorization.
4. Prefer controlled contrasts for attribution. Where interactions are plausible, schedule a small explicit interaction design after single-factor gates; label coupled changes instead of attributing the combined gain to one knob. Count distinct measured configurations separately from restarts or repeated probes.
5. Separate fast screening from full validation. Preserve failed, invalid and inconclusive results. Repeated identical recovery attempts should trigger diagnosis or restoration rather than inflate exploration counts. Redirect on evidence, not only because more time remains.
6. Audit suspicious timing against event semantics, token/work counts, actual artifact behavior and conditional physical feasibility. Inspect quality and integrity independently. Never implement a benchmark bypass as an optimization.
7. Compare optimization methods with matched total resources and wall-clock costs. Separate search cost/API cost from steady-state serving cost. A per-engine multi-run grid is not a single equal-budget engine-selection result.
8. Reserve time based on observed clean restart, warmup and full verification duration. Restore the best fully valid incumbent, restart through the canonical artifact and verify that exact state. Report best-seen and delivered results separately.

## Output and stop

Return an experiment decision log with candidate rationale, variables, input/evaluator identities, results and uncertainty, integrity/quality verdict, total resource cost, redirect/reject reason and incumbent identity. Stop when the authorized budget/goal is reached or the next useful action needs new authority. No victory from a last successful probe if the shipped artifact differs or is broken.

Paper-specific two-hour budgets,15-minute validation reserves,95% quality thresholds and named-model rankings are evidence contexts, not default policy. Broader exploration and preservation improve different failure modes; neither paper proves one universal optimizer.

## Resource contract

This procedure and its local `references/source-notes.md` are sufficient for selective consumption. The rest of Pack A supplies optional comparisons and integration notes; no parent-folder file is required to interpret the procedure or its source limits. Existing InferRSI skill names above are reconciliation targets, not runtime dependencies.
