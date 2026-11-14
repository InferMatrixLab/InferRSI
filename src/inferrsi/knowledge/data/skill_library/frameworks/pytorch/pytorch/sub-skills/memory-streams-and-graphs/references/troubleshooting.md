# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| OOM while reserved memory is high | Live state, graph private pools, fragmentation or external allocations | Record allocated/reserved/peak and lifetime evidence; remove unintended live references before tuning allocator settings. |
| Cross-stream wrong values or reused storage | Missing ordering or allocator usage record | Insert consumer wait plus record_stream for lifetime; neither operation substitutes for the other. |
| Graph replay ignores new input | Python variable rebound, captured buffer unchanged | Copy new values into static input storage before replay with correct stream ordering. |
| Capture fails on synchronization or dynamic path | Capture-unsafe host/device operation | Warm eager on side stream, remove unsupported synchronization/data-dependent host path and qualify replay outputs. |
| CUDA unavailable | CPU build or missing actual device/runtime | Keep BLOCKED_REQUIRED_BACKEND; do not execute a CPU substitute for CUDA graph or allocator claims. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
