# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| No accelerator activity | Unavailable profiler activity/CUPTI or wrong recording window | Check supported_activities and actual device execution; retain missing device trace as unverified. |
| Trace empty or unexpectedly partial | Missing prof.step, invalid schedule, unfinished cycle or postprocessing limit | Use finite valid schedule, step once per workload iteration and export at on_trace_ready; mark partial outputs. |
| Profiled workload uses more memory | Shape/stack tracing holds references and adds instrumentation | Disable unneeded instrumentation for final measurement and compare a minimally instrumented control. |
| Huge speedup from host timer | Asynchronous enqueue or mismatched warmup/cache/thread count | Synchronize the measured boundary, match state and use replicated timing; keep cold compilation separate. |
| NaN/Inf appears only in one mode | Precision/reduction/backend or invalid-domain sensitivity | Find first nonfinite intermediate and compare higher precision/eager controls with defined tolerances; a seed is insufficient. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
