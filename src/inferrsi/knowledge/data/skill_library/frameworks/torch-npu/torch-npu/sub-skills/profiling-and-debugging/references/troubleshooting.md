# Profiling troubleshooting

| Symptom | Check and recovery |
|---|---|
| Empty trace | Confirm active schedule reached, `prof.step()` called and activities supported. |
| CPU events only | Check actual NPU activity/runtime collector; CPU activity is not accelerator verification. |
| Memory timeline absent | Enable shapes, memory and stack or modules; inspect warnings and output path. |
| Collection exists but viewer/parser fails | Preserve raw trace; report analysis failure separately and use a compatible parser. |
| Timing changes greatly with debugging | Restore launch blocking/sanitizer settings and compare synchronized measurements. |
| Trace has missing device metrics | CANN feature/metric support can differ by stack/hardware; report unavailable counters explicitly. |
| Sanitizer reports use after free/race | Route to memory lifetime and producer/consumer ordering, then rerun the reduced case. |

A produced trace is evidence to inspect, not a PASS on throughput, convergence,
service SLO or hardware health.
