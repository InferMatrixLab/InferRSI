# Establish acceptance criteria before search

Use this procedure when preparing an inference-optimization task. The agent
resolves criteria and writes the campaign contract; the CLI does not invoke a
skill or infer thresholds when a flag is omitted.

## Select the source

1. Read the user's request and any referenced acceptance issue or frozen plan.
   **Use supplied criteria unchanged:** retain metrics, units, timing boundaries,
   statistics, workload coverage, thresholds and quality/resource constraints.
   An estimate may flag an infeasible target but must not replace or relax it.
   Conflicting requests and frozen records need resolution by their authorized
   owner; do not choose whichever target is easier to pass.
2. If criteria are absent, use [performance-ceiling-analysis](../SKILL.md) to
   formulate workload-specific acceptance criteria before candidate search.
   Retain partial requirements: derive only missing performance targets and
   measurement details, labelling each derived field separately. An unspecified
   primary objective that cannot be resolved from task context is a missing
   input, not permission to optimize a different objective.
3. Reuse the target's existing correctness/quality contract and retain baseline
   semantics. Hardware ceilings cannot determine quality tolerances, an
   application SLO or permission to change precision, steps or useful work.
   Resolve missing quality requirements from the task and reference validators;
   if still unknown, record the gap rather than invent a tolerance.

Do not add a confirmation round when the user has already delegated goal
formulation and campaign preparation. Use the existing freeze authority; record
agent-derived targets as such, never as user-supplied or user-confirmed numbers.

## Derive a target when none was supplied

1. Establish the model, exact hardware/resources, workload, objective and timing
   boundary. Measure a comparable baseline and its variation; keep profiler runs
   separate from acceptance timing. Collect only within the authorized budget.
2. Apply the skill's analytical, empirical-component and end-to-end levels as
   needed. Preserve sources, scope, assumptions and unknowns. These ceiling
   levels are distinct from the repository's L0–L4 validation ladder. A pure L1
   Roofline result is a conditional bound, not an attainable service target.
3. Estimate an attainable range using matching component measurements and
   exposed critical-path costs. For a serial latency decomposition with
   nonoverlapping fractions `f_i` and supported stage speedups `s_i`, compute
   `S = 1 / sum(f_i / s_i)` across the uncertainty range. Include unchanged
   stages with `s_i = 1`. Overlap, queueing and bottleneck migration require the
   corresponding critical-path/capacity analysis instead of summing durations.
4. Choose a conservative target supported by that attainable range and separated
   from measured baseline noise. Explain the selected point and any margin in
   terms of calibration evidence and the task budget; no universal fraction of
   peak or fixed improvement percentage applies. For baseline latency `T0` and
   a justified target speedup `S_target`, the absolute target is
   `T0 / S_target`, and the relative reduction is `100 * (1 - 1 / S_target)`.
   State whether the contract requires an absolute target, a relative gain or
   both. A throughput target needs evidence for its own workload and load regime;
   do not infer it by inverting service latency.
5. Define the per-workload combination rule, quality checks, guard metrics,
   repetitions/statistics and stopping conditions. If no positive target can be
   distinguished from noise, retain the incumbent and identify the next useful
   calibration or report insufficient headroom. Do not turn that into PASS.

Missing inputs required by the selected analysis or acceptance contract remain
`INSUFFICIENT_EVIDENCE` in the analysis and `INCONCLUSIVE` for campaign acceptance.
For example, analytical work/traffic bounds need model counts; a supported
empirical stage estimate need not. Comparable baseline, calibration, uncertainty
and quality coverage are still needed for a derived acceptance target. List the
missing measurements and their bounded cost.
Continue authorized preparation/calibration, but do not freeze a made-up number
or start candidate search under unresolved gates. Never use a similar SKU, the
CLI's default threshold, a theoretical maximum or a later candidate result to
fill the gap.

## Record and freeze the contract

Write the result into the existing acceptance issue and campaign plan, not a
second goal registry. Record:

- source per criterion: `user` or `ceiling-derived`, with the request/plan
  reference; use `mixed` for a contract retaining both;
- metric, unit, direction, statistic, timing boundary and each workload target;
- baseline identity and samples, analysis/skill revision, input sources,
  attainable range, uncertainty and the reason for the selected target;
- quality/resource constraints, required validation coverage, evidence gaps,
  budget/stop conditions and who has authority to freeze the contract.

Freeze the resolved contract and validator/input hashes before candidate search.
Existing frozen campaigns retain their criteria. Changing a frozen goal follows
the campaign's revision policy and preserves prior evidence; it cannot
retroactively qualify an earlier result.

Map a resolved relative primary-metric target to `--metric-key`, `--metric-unit`,
`--direction`, `--comparison-scope` and `--min-improvement-pct`. Put quality and
additional campaign gates in the appropriate validators; the generic evaluator
does not automatically enforce absolute targets or a multi-workload contract.
`plan` is a preview, not a freeze or a full campaign acceptance check. Only
complete measured evidence satisfying the frozen gates can establish PASS.
