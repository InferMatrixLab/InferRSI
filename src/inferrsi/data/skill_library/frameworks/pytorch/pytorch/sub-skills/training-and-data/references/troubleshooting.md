# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| Worker hang or pickling failure | Spawn lambda/local callable, worker exception or device allocation | Retry num_workers=0 to expose the exception; use top-level picklable callbacks/main guard and host batches. |
| Duplicate iterable samples | Each worker/rank traverses the full iterable | Shard by worker and rank identities, verify sample IDs and epoch state before throughput tuning. |
| prefetch_factor/persistent_workers rejected | Multiprocess option used with zero workers | Use prefetch_factor=None and persistent_workers=False for zero-worker correctness control. |
| AMP clipping or accumulation wrong | Scaled gradients clipped or scale changed inside window | Accumulate with constant scale, unscale once after the window, clip then step/update; account for short windows. |
| Evaluation attention still stochastic | SDPA dropout_p nonzero despite model.eval | Pass dropout_p=0.0 for eval; inspect mask True semantics and compare math backend before forcing fused kernels. |
| Checkpointed gradients differ | Recompute observes changed state/RNG/device or wrong variant | Use explicit use_reentrant=False where suitable and compare with an uncheckpointed eager control before interpreting memory benefit. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
