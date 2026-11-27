## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| The target is Ascend and weight scales, KV replication or a multimodal adapter prevent a real-weight run. | `ascend-model-adaptation` | Get the checkpoint and feature report. Replay the first unsupported load or stage with real weights before progressing. |
| A Flux diffusion stage agrees on the first call but diverges on reuse. | `diffusers-invocation-state` | Get the wrapper/scheduler state trace. Replay with a fresh pipeline and compare the first differing timestep. |
| The request includes a support claim and some features have only source or smoke evidence. | `claim-contract` | Map observations to the declared gates. Publish the supported subset and leave the uncovered features open. |

