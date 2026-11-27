# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| Frequent recompilation | Guarded shape/stride/dtype or Python state changes | Read failed guards/recompiles logs; encode legitimate dynamic shapes and remove unrelated state variation; retain correctness checks. |
| fullgraph fails on data-dependent Python | Capture boundary cannot represent the control flow | Keep eager control, choose supported structured control flow or an explicit boundary; do not claim one graph after allowing breaks. |
| Missing lowering or backend compile error | Dynamo capture succeeded but target lowering/toolchain failed | Compare eager/aot_eager/target, inspect overload metadata and fake kernel; keep target BLOCKED or failed separately. |
| Export constraint violation | Example shape outside declared range or unsatisfied relation | Inspect suggested bounds, supply shared Dim/shape relations and test valid plus rejected shapes. |
| ONNX export succeeds, target fails | Opset/translation/external data/dynamic shape consumer mismatch | Install selected ONNX dependencies and verify in the real consumer with complete weight files and representative input ranges. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
