---
name: training-and-precision
description: "Migrate a bounded TorchNPU training step, select autocast and gradient-scaling behavior, compare optimizer/checkpoint state and diagnose precision failures."
---

# Validate training and precision

Use for a first NPU training step, autocast/GradScaler, gradient clipping,
overflow, fused optimizer migration or numerical mismatch. Read [the precision procedure](references/training.md)
and [failure recovery](references/troubleshooting.md).

Inputs: model/loss/optimizer, input dtype/layout, gradient accumulation, scaler,
distributed mode, expected tolerances and exact stack. Output: one-step
correctness/overflow/state comparison with a named validation scope.

1. Establish FP32 eager forward/backward and optimizer behavior.
2. Introduce autocast and scaling deliberately; check finite gradients and
   skipped steps separately from loss values.
3. Unscale before clipping, and update the scale only at the optimizer boundary.
4. Run [the bundled AMP case](../../scripts/runtime_smoke.py) with
   `--case amp --run` on an NPU; preserve disabled-scaler and overflow observations.
5. Test optimizer/checkpoint changes separately, then add distributed or graph
   execution through their owning routes.

A finite one-step loss is not convergence, numerical-quality, throughput or
service evidence. Custom-op gradients belong to [operator development](../operator-development/SKILL.md).
