# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| grad is None | Nonleaf, detached history, disabled grad mode or unused parameter | Inspect is_leaf/grad_fn/requires_grad, retain_grad only for needed intermediates, and restore a recorded differentiable path. |
| Modified by an inplace operation | Saved tensor version changed through a view or detached alias | Locate earliest mutation and preserve saved values; do not bypass version checks with .data. |
| No kernel for backend/layout or FakeTensor | Wrong dispatch overload, layout or missing registration | Record schema and key context, reproduce plain eager, then add transforms; route registration repair to custom operators. |
| Ragged j2/j3 structure mismatch | Distinct offsets constituents | Construct compatible jagged tensors sharing the intended offsets; equal element counts alone do not satisfy this contract. |
| Sparse result grows or mismatches | Uncoalesced duplicates, unsupported layout/gradient or densification | Coalesce where semantics require; validate indices, output layout and exact operator support before performance work. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
