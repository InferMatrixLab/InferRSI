## Run the procedure

1. Inventory the known-good and requested versions of the engine, plugin, operator library, backend and driver. Include vLLM, vLLM-Omni, vLLM-Ascend and AFD Plugin where used. Keep build options, model, device and run script constant.
2. Replay the known-good and complete target stacks on the same workload. Record import/build, operator dispatch, integration and output/parity results for each supported combination.
3. Change one compatible dependency boundary at a time, or bisect a coupled pair when the components must travel together. Record unbuildable combinations explicitly. Compare effective APIs, ABI, flags and dispatch at the earliest failing step.
4. Apply the smallest in-scope pin or adapter, replay the complete target stack, and verify the rollback combination with the same script and quality/performance checks requested by the user.

