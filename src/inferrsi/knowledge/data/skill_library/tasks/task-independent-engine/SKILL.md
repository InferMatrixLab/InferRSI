---
name: task-independent-engine
description: Use when the deliverable owns its execution, memory and device integration on a target OS and hardware stack. Prove a native end-to-end path and measure its resource use.
---

# Bring up an independent inference engine

## Capture the actual run

Record the hardware vendor, device SKU, backend and driver, OS, model family and
checkpoint revision, engine and plugin versions, and the exact run script and
flags. Attach the benchmark inputs, workload shape, dtype, reference or quality
oracle, and the user's acceptance criteria. Write down the current diagnosis
and its supporting observation, allowed search space, and remaining budget.
Mark missing fields as unknown and request the first one that affects a decision.

## Run the procedure

1. Pin model format, reference inputs and outputs, target OS/ABI, device/driver, available runtime APIs and resource limits. Map required operators, dtypes, layouts and memory lifetimes to target capabilities. Mark fallback, missing implementations and unverified capabilities.
2. On the actual target, load the model and run one reference-checked operator with a dispatch trace. Extend to the shortest connected path that produces an output. Test the first missing operator or allocation boundary before expanding coverage.
3. Run the complete input through preprocessing, execution and postprocessing. Verify device placement or any explicitly permitted fallback. Exercise repeated requests and teardown to expose ownership or retained-memory errors.
4. Replay the user's script on the target OS/device. Check end-to-end output, resident or peak memory, cold/warm behavior and the user-specified resource gates. Record unsupported operators and model features.

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

## Acceptance and handoff

Finish when a target-native end-to-end run meets the agreed correctness and resource gates, with native dispatch or permitted fallback accounted for. If a backend or device is unavailable, record the missing access and propose the first on-target operator or allocation check that can resolve the blocker.
If the allowed search space or budget is exhausted, record the blocker, the
evidence already obtained and the smallest remaining discriminating test.
