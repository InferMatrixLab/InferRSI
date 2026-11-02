# Four-device preflight plan

This scope is 4x Ascend 910B1, not eight devices or 910C. See [acceptance issue](https://github.com/InferMatrixLab/InferRSI/issues/320).

The initial 5s preflight runs two warmups and one measured request, 50 steps, seed zero. It is not a formal A/B or final acceptance. Startup is excluded from HTTP timing. The original baseline shutdown remains intact, so its known eight-device lifecycle concern must be checked here rather than silently repaired. Full 15s execution and independent paired comparisons remain pending.

Runtime wrapper adapts the existing #293 harness: device-count assertion and all parallelism flags are four; output namespace and service port are isolated. Only the dense baseline arm is enabled. Outer reservation budget is five hours, with a 280-minute command deadline and 180-second kill grace; HTTP and DLO wave timeouts are 7200 seconds. This is a bringup ceiling, not a measured latency or a final experiment budget.

The allocated physical IDs are recorded at execution. NPU scheduling is respected; no resource is claimed before allocation. Later A/B work must pin the same allocation throughout the pair and independently freeze its budget and order.
