## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| A fixed-workload report aggregates the quality or completion results differently between runs. | `audit-fixed-workload-claim` | Audit retained observations, declared quality evidence and comparability. Align the reports before attributing a regression to model math. |
| A Flux pipeline or FlowMatch scheduler differs only on repeated calls. | `diffusers-invocation-state` | Get the call-state and schedule trace. Compare fresh versus reused wrappers at the first differing timestep. |
| The first differing tensor is on an Ascend TorchNPU dispatch or dtype boundary. | `torch-npu` | Identify the actual dispatch path and precision behavior. Replay that operator with fixed inputs and verify on the installed device. |
| The reported tolerance passes for only a subset of requested outputs or targets. | `claim-contract` | Get the supported verdict and evidence gaps. State the covered scope and obtain the missing target result before declaring recovery. |

