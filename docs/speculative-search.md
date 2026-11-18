# Offline candidate trees and verification plans

This is the first implementation slice of
[the SpecRSI proposal](https://github.com/InferMatrixLab/InferRSI/issues/363).
`harness/search_tree.py` provides immutable candidate and evidence transitions;
`harness/verification_plans.py` constructs bounded completion menus. Both are
pure Python control primitives with no execution, storage or model access.
The existing project and benchmark session commands retain their current behavior.

The design follows [SpecRSI v2, Section 3](https://arxiv.org/html/2610.16491v2#S3):
editing an incomplete or unsuccessful parent is allowed, while adopting a version
requires complete admissible evidence for that version. Completion bundles keep
complementary checks together. This slice supplies building blocks for the inner
search; a learned Scorer/Policy, automatic Drafter and GVO updates remain future
integration work.

## State and evidence

`Contract` freezes the search identity, verification context, required checks,
objective, direction, improver snapshot and candidate/depth/check-attempt caps.
The context identifies the plan, validator, environment, workload, original
baseline and quality reference. Checks may encode separately required repetitions.
The current selector supports a scalar objective plus hard PASS requirements;
the Skill lane's quality-first lexicographic selector needs a separate adapter.

`initialize` requires one complete, passing receipt per root check. Root receipts
count against the attempt cap. Their acquisition/reuse cost must already be in
the caller's authoritative accounting. A passing objective check carries a finite
value; other checks and rejected/inconclusive outcomes cannot supply a value.

`add_candidate` records an immutable artifact digest and edit parent, with the
frozen producer snapshot, producer revision, context/history digests and actual
generation dependencies. Callers retain and verify artifacts with the existing
`harness.candidates.retain` / `identity` helpers before admission. This core does
not authenticate digests or decide whether an edit was permitted. Parent quality
failures do not invalidate the edit lineage. Real generation-source dependencies
are inherited and must still be current; a child cannot drop them to escape an
invalidation. Rebase or composition is a new candidate with its own evidence.
This offline core predeclares dependency keys at initialization; introducing new
source authorities dynamically requires later controller integration.

`register_attempt` binds a caller-owned attempt/execution key, reservation and
lease to one candidate, check and complete verification context. Registering an
attempt grants no execution permission. Unknown work on the same check cannot be
replaced, even after dependency invalidation. Valid outcomes cannot be resampled
until they pass; an INCONCLUSIVE outcome may be retried with a fresh identity
under the caller's frozen retry rules and a new reservation.

`record_receipt` requires the entire registered binding. Identical delivery is
idempotent and conflicting delivery is rejected. History retains late results;
`evidence` admits only the latest attempt with current dependency epochs and
valid candidate provenance. FAIL is an observed outcome, whereas INCONCLUSIVE
leaves a check missing. Identical candidate bytes do not transfer evidence.

`accept` selects only fully passing candidates, preferring the root on an
objective tie and otherwise using lexicographic candidate ID order. The result is
a **development selection**. Independent final/holdout acceptance and production
promotion remain caller-owned. `verified_gain` measures this selection relative
to the root. Invalidation recomputes eligibility; invalid root evidence blocks
acceptance and further drafting/check registration, while late archival remains
available.

## Completion planning

`completion_menu(state, jobs, available_budget=..., available_jobs=...,
max_targets=..., max_jobs=...)` takes a supplied integer-cost budget view and
returns immutable `Plan` values. The caller has already accounted for planning,
generation, final reserve, in-flight obligations and unknown spend when deriving
that view. Costs must be known positive conservative bounds in the same unit.

Each `Job` names either a candidate/check pair or a shared preparation step.
Prerequisites form an acyclic graph. The solver takes each candidate's complete
missing-check set, closes its prerequisites, and enumerates unions of at most
`max_targets` candidate seeds. Every feasible singleton completion remains in
the menu. Shared jobs are charged once per plan, conflicts exclude combinations,
and available job slots and remaining check attempts bound each proposal.
`max_jobs` bounds the input graph; enumeration is intended for small offline
controls, not an unbounded production optimizer. No Scorer prediction is used
as evidence or as a substitute for a completion seed.

Plans bind the search ID and state revision and carry a deterministic topological
job order. The caller retains the full job definitions and costs with its frozen
plan; job IDs alone do not authenticate them. The adapter rebuilds job
relations from current observations at each synchronous decision boundary;
already observed checks are not silently scheduled again. An in-flight attempt,
including an invalidated one, blocks replanning until its execution is settled.
An empty menu is a valid outcome under a tight budget; the root remains available
when its evidence is valid. Feasibility says nothing about whether checks pass.

## Shared execution and persistence boundary

These modules introduce no second runner, budget ledger, holdout tracker or
storage backend. A future application adapter must:

1. Read current authoritative state and the frozen contract, settle the previous
   work block, and supply a conservative available-budget view.
2. Generate and retain permitted edits, or select an affordable check plan using
   the frozen roles. Account for generation, planning and failed work.
3. Use shared execution controls for atomic claim/reservation, absolute deadline,
   resource isolation and actual execution. Bind their identities to the tree.
4. Authenticate and assess receipts, apply a transition against the expected
   search revision, and persist it using the authoritative storage CAS/lock.
   A pure function's revision check is **not a durable or cross-worker CAS**.
   On conflict, reread and recompute; an ambiguous claim never grants a retry.
5. Persist real dependency invalidation before cancellation. Reconcile costs and
   retain leases until process cleanup is confirmed. Receipt archival itself
   neither charges again nor releases a resource.
6. Freeze the selected version for independent final acceptance, with holdout
   access and interruptions tracked separately from development feedback.

There is no production adapter in this slice. In particular, local immutable
values and revision checks do not establish crash recovery, external exactly-once,
multi-worker resource isolation, budget transactions or holdout non-reuse.

## Verification and remaining delivery

Run the CPU controls with:

```bash
python -m pytest tests/test_speculative_search.py tests/test_verification_plans.py
```

Tests cover retained file/directory artifacts for synthetic Engine/Skill shapes,
failed-parent repair, incomplete ancestors, failure versus missing evidence,
dependency/result order, identical bytes with separate attempts, stale revision
rejection, immutable role snapshots, deterministic selection, invalid roots and
bounded search. The planner is compared with an independent exhaustive job-subset
oracle across budgets and target limits, including shared preparation and conflicts.

| Issue acceptance area | This slice | Remaining evidence |
| --- | --- | --- |
| AC-01/02 | Frozen scalar contract and offline candidate tree | Production support matrix and role/execution adapters |
| AC-03/05 | Scoped evidence, epoch invalidation, development selection and revision guards | Authoritative durable state integration and restart/race tests |
| AC-04 | Bounded exact completion menu and exhaustive controls | Scorer refinement, Policy selection and scalable solver integration |
| AC-06 | Frozen snapshot identity only | GVO data collection, objectives, parameter updates and new searches |
| AC-07/08 | References to caller-owned execution identities | Actual budget/resource transactions, cancellation and independent final/holdout |
| AC-09/10 | Synthetic control fixtures | Both real adapters, model generation, training, matched experiments and lifecycle costs |

These tests do not establish model quality, engine speedup or SpecRSI efficiency.
The parent issue remains open for its full dual-loop delivery.
