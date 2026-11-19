---
name: assess-split-backward-schedule
description: Evaluate memory-capped split-backward and V-shaped pipeline scheduling proposals, preserving synchronous update, global-batch and optimizer-validation semantics.
---

# Assess a split-backward schedule

Use when a pipeline trace suggests input-gradient propagation waits behind deferrable parameter-gradient work or an optimizer barrier. This is a candidate paper-derived assessment, not permission to change a training runtime. Read [evidence](references/source-notes.md).

## Required evidence

Obtain stage/microbatch counts, microbatch/global batch, precision, optimizer and clipping/NaN behavior; F, input-gradient B, weight-gradient W and transfer timings; per-pass retained/released bytes; total device peak/margin; collective ordering; and kernel-splitting support. Separate calculated bubble rate from measured idle time and useful samples/s.

## Proposal

- Identify the critical B dependencies and work W that can legally move after its corresponding B. Account for W inputs retained by deferral; do not equate completion of B with releasing all activations.
- Compare ordinary 1F1B with a memory-capped split schedule. Use observed F/B/W times and transfer costs rather than the equal-time zero-bubble construction. Include kernel-splitting and synchronization overhead.
- When memory permits, compare a larger activation cap with V-shaped two-chunk placement. At matched global batch also consider smaller microbatches with more microbatches. Keep total HBM, workspace, buffers and per-rank imbalance explicit; pMB denotes activation capacity, not total memory.
- Choose whole-step throughput under the memory/quality constraint, not minimum modeled bubble rate. Larger microbatches may beat lower bubbles because kernels use hardware better; more chunks can add communication.
- Keep optimizer post-validation separate. Removing a barrier must preserve global norm/clipping/NaN decisions, rollback/re-update, and correctness of work dependent on a tentative update. If actual optimizer reversibility and rollback coverage are unverified, retain the synchronized fallback. This mechanism is distinct from accepting stale-gradient delayed updates.

## Output, checks and stopping point

Return a candidate/fallback with per-pass order rationale, peak-memory and transfer costs, unchanged semantic requirements, counter-signals and a future verification proposal. A later authorized comparison should hold model, global batch and precision fixed and inspect numerical equivalence, full-step time, total peak bytes, exposed communication, rollback frequency/cost and real versus calculated idle intervals.

Frequent clipping/NaNs, small available memory, strongly unequal passes, unsupported split kernels, hidden collectives or dynamic shapes are reasons to withhold an enablement recommendation. A paper's fixed-seed loss match is not universal convergence or rollback-stress validation. Stop at the reviewable plan; do not install/run frameworks, benchmark schedules, change training semantics, configure hardware or modify repositories without separate authorization. No current/NPU compatibility is established.
