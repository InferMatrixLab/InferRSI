---
name: assess-split-backward-schedule
description: Evaluate memory-capped split-backward and V-shaped pipeline scheduling proposals, preserving synchronous update, global-batch and optimizer-validation semantics.
metadata:
  inferrsi: |
    {
      "status": "candidate",
      "empirical_validation": "not_run",
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "applicability": {
        "scope": "Assessing memory-capped split-backward and V-shaped pipeline schedule proposals when a pipeline trace suggests input-gradient propagation waits behind deferrable weight-gradient work or an optimizer barrier, while preserving synchronous update, global-batch and optimizer-validation semantics",
        "prerequisites": "The packaged evidence notes are read before citing the paper; installing or running frameworks, benchmarking schedules, changing training semantics, configuring hardware or modifying repositories needs separate authorization",
        "input_contract": "Stage and microbatch counts, microbatch and global batch, precision, optimizer and clipping/NaN behavior; F, input-gradient B, weight-gradient W and transfer timings; per-pass retained and released bytes; total device peak and margin; collective ordering; kernel-splitting support; calculated bubble rate kept apart from measured idle time and useful samples/s",
        "produced_artifact": "A candidate schedule and fallback with per-pass order rationale, peak-memory and transfer costs, unchanged semantic requirements, counter-signals and a future verification proposal; a reviewable plan, not an enabled schedule",
        "failure_modes": [
          "Completion of B is equated with releasing all activations, so W inputs retained by deferral go uncounted",
          "The equal-time zero-bubble construction replaces observed F/B/W and transfer times, or kernel-splitting and synchronization overhead is left out",
          "The schedule is chosen by minimum modeled bubble rate instead of whole-step throughput under the memory and quality constraint",
          "pMB activation capacity is read as total memory, hiding HBM, workspace, buffers or per-rank imbalance",
          "Removing the optimizer barrier drops global norm, clipping or NaN decisions, rollback and re-update, or the correctness of work that depends on a tentative update",
          "Optimizer post-validation is conflated with accepting stale-gradient delayed updates"
        ],
        "refusal_point": "Withholds an enablement recommendation under frequent clipping/NaNs, small available memory, strongly unequal passes, unsupported split kernels, hidden collectives or dynamic shapes, and retains the synchronized fallback while optimizer reversibility and rollback coverage are unverified"
      },
      "recommendations": [
        "Compare ordinary 1F1B with a memory-capped split schedule first; add V-shaped two-chunk placement only when memory permits, and at matched global batch also try smaller microbatches with more microbatches.",
        "Decide optimizer post-validation separately from the schedule change.",
        "In a later authorized comparison, hold model, global batch and precision fixed and compare real with calculated idle intervals."
      ],
      "limitations": [
        "Source-derived candidate; no local efficacy validation.",
        "Original typed source inventory is not normalized; retain source identities and limits in the procedure/readsets."
      ],
      "provenance_readsets": [
        "references/source-notes.md"
      ],
      "consumption_mode": "packaged"
    }
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
