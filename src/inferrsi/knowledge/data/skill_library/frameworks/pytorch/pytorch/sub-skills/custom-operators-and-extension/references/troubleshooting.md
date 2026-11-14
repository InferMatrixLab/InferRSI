# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| opcheck alias/schema error | Fresh-output declaration returns view/input or mutability metadata lies | Correct the implementation or intended schema; do not disable the check to obtain compilation. |
| FakeTensor stride mismatch | Fake returns right shape but wrong layout | Reproduce real output metadata including strides/device/dtype; a shape-only meta implementation is insufficient. |
| gradcheck fails while opcheck succeeds | Incorrect derivative or unsupported finite-difference domain | Check double precision/input domain and derivative formula separately from registration. |
| Compiled backward reads incorrect memory | Incoming gradient strides assumed contiguous | Handle grad strides or materialize valid contiguous storage at the kernel boundary. |
| Extension import undefined symbol | ABI mismatch or stale build artifact | Match torch/compiler/toolkit, rebuild the affected extension in its private cache; runtime wheel is not a source toolkit. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
