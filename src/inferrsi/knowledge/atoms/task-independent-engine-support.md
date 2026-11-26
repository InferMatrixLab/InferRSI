## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| An MLC-derived artifact, Metal dispatch or KV-capacity estimate is relevant to the proposed target. | `mlc-llm` | Obtain the pinned artifact/runtime contract and native discriminator. Verify the operator or allocation locally before using it as target evidence. |
| An Android diffusion path exhibits a process, DiT packaging, ABI or backend mismatch. | `local-dream` | Get the declared-versus-serving state trace. Run the minimal packaged path on the named Android device and verify dispatch. |
| A repeated request retains state and the design uses a llama.cpp-compatible context. | `audit-llama-runtime-state` | Obtain a state ownership ledger. Probe the earliest unmatched allocation, progress or release event on the target runtime. |
| Timings vary on a shared host and CPU affinity or accelerator contention is observable. | `os-process-placement` | Record supported placement, occupancy and thread controls. Repeat the workload under matched conditions using target-native tooling. |
| The engine runs end to end but quality, cold/warm timings or the resource envelope are undefined. | `inference-benchmark-design` | Define reference checks and a target workload. Collect quality and resource measurements on the actual device. |

