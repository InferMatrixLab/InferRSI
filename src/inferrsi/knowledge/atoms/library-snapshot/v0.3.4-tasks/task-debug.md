---
name: task-debug
description: Use for inference crashes, hangs, out-of-memory failures or execution-path errors. Localize the first failing boundary and verify recovery with the original reproducer.
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "profile": "local-skill-v1",
      "kind": "skill",
      "discovery_role": "task-entry",
      "status": "candidate",
      "origin": [
        "first-party"
      ],
      "consumption_mode": "packaged",
      "tags": [
        "inference-task",
        "primary-task",
        "debug"
      ],
      "empirical_validation": "not_run",
      "searchspace_not_applicable": "The procedure selects supporting evidence and tests within the caller's declared search space.",
      "applicability": {
        "scope": "Run-specific failure reproduction, fault isolation and regression verification.",
        "input_contract": "Actual hardware, model, engine, script and flags, benchmark, acceptance criteria, current diagnosis, permitted changes and budget.",
        "produced_artifact": "Minimal reproducer, passing control, localized cause and verified original-script replay.",
        "refusal_point": "Record missing evidence or an exhausted search budget and identify the smallest discriminating test before declaring success."
      },
      "provenance_readsets": []
    }
---

# Isolate and repair an execution failure

## Capture the actual run

Record the hardware vendor, device SKU, backend and driver, OS, model family and
checkpoint revision, engine and plugin versions, and the exact run script and
flags. Attach the benchmark inputs, workload shape, dtype, reference or quality
oracle, and the user's acceptance criteria. Write down the current diagnosis
and its supporting observation, allowed search space, and remaining budget.
Mark missing fields as unknown and request the first one that affects a decision.

## Run the procedure

1. Replay the supplied script with its original flags and capture the first observable error, stage, device, rank and timestamps. Keep a last-working revision or configuration as a control. For a hang, capture progress at each boundary before attributing a cause.
2. Minimize the input or configuration one variable at a time. Preserve the original signature and a closely matched passing control. Follow ownership across stages to locate the earliest difference.
3. State two explanations that predict different observations. Probe the smallest boundary that distinguishes them, such as a recorded handoff with a known-good producer or consumer. Apply one in-scope fix only when the observation implicates that boundary.
4. Repeat the minimal reproducer, then the original unmodified script and an unaffected control. Retain logs tying the original failure and recovery to the same boundary and save a regression check.

## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| The failure resembles a prior trial or appears only with a particular optimization. | `inference-optimization-casebook` | Get the prior failure conditions and retry rule. Test whether the same switch reproduces the signature on this target. |
| Ascend timing or device behavior changed after a killed job or card-group change. | `ascend-device-health` | Collect device health, occupancy and timing checks. Establish a clean matched control before blaming the engine. |
| A vLLM V1 request stalls during asynchronous KV transfer, preemption or block reuse. | `audit-vllm-kv-lifetimes` | Build the scheduler/connector ownership trace. Probe the earliest missing completion or block-release edge. |
| A CUDA AFD dense FFN P2P exchange hangs or returns the wrong slice. | `audit-afd-p2p-exchanges` | Build the rank and per-peer payload ledger. Check the first mismatched assignment against caller traces before testing transport. |

## Acceptance and handoff

Finish when the original failure is reproducible before the fix, its earliest implicated boundary is supported by evidence, and both the original script and the unaffected control pass after the fix. For an intermittent failure, record the attempted repeats and propose the narrowest additional trace that can distinguish the remaining causes.
If the allowed search space or budget is exhausted, record the blocker, the
evidence already obtained and the smallest remaining discriminating test.
