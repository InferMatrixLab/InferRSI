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

