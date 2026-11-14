---
name: training-and-data
description: "Build or debug PyTorch modules, optimizers, data loaders, mixed precision, activation checkpointing and attention training or evaluation."
---

# Training and data

Use this route for the task named in the description. Produce a bounded training or evaluation recipe with explicit sample, state, gradient and numerical checks.
This is a source-derived **candidate**, with native backend checks separate from
source support. Read the root [provenance](../../references/repo-provenance.md)
when package, API or platform identity differs.

## Operating sequence

1. Record the concrete input contract, current behavior, desired result, package
   version and backend. Preserve a tiny eager or single-process control.
2. Read [workflows and mechanisms](references/workflows.md) and choose its
   matching branch. Check prerequisites before launching a build or device job.
3. Apply the smallest change at the first disagreeing boundary; preserve tensor
   shape, dtype, layout, device, mutation and gradient assumptions.
4. Check the predicted output and failure recovery using the linked helper or
   recipe. A software check cannot establish an unavailable device capability.
5. Return the artifact named above, checks actually run, unresolved conditions
   and the next discriminating check. Missing required backend execution stays
   **BLOCKED_REQUIRED_BACKEND**; efficacy stays **not_run** without measurements.

Read [troubleshooting](references/troubleshooting.md) when a prerequisite or
check fails. The references contain complete procedures and exact source
permalinks; the original source checkout is not a runtime prerequisite.
