---
name: task-day-0
description: Use for Day-0 onboarding of a new checkpoint or architecture to a named inference engine. Produce a reproducible target run, stage parity evidence and a regression fixture.
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
        "day-0"
      ],
      "empirical_validation": "not_run",
      "searchspace_not_applicable": "The procedure selects supporting evidence and tests within the caller's declared search space.",
      "applicability": {
        "scope": "New model support in an existing inference engine.",
        "input_contract": "Actual hardware, model, engine, script and flags, benchmark, acceptance criteria, current diagnosis, permitted changes and budget.",
        "produced_artifact": "Per-stage parity report, supported-feature matrix, end-to-end output and replayable regression fixture.",
        "refusal_point": "Record missing evidence or an exhausted search budget and identify the smallest discriminating test before declaring success."
      },
      "provenance_readsets": []
    }
---

# Bring up a new model in an existing engine

## Confirm the Day-0 inputs

Start a fresh intake record in the target workspace before preparing a device
run. Use the same launcher that loaded this skill.

```text
inferrsi task intake evaluate --task task-day-0 --record <record.json> --json
```

Supply facts the user already gave with `--source prompt`. If the intake returns
questions, ask the first batch in the current conversation and wait for the
answers. Record each answer with `task intake answer --record <record.json>
--question <id> --value <value>` or `--unknown`, then re-evaluate. Preserve
missing conditions and use `task intake summary` to report the confirmed inputs
and blockers. Keep the Day-0 record with the handoff.

While a `device_execution` blocker remains, use the available inputs for read-only
preparation. After resolving the blockers, obtain device execution authorization
before starting a target run.

## Capture the actual run

Record the hardware vendor, device SKU, backend and driver, OS, model family and
checkpoint revision, engine and plugin versions, and the exact run script and
flags. Attach the benchmark inputs, workload shape, dtype, reference or quality
oracle, and the user's acceptance criteria. Write down the current diagnosis
and its supporting observation, allowed search space, and remaining budget.
Mark any additional unknowns that affect a comparison or execution decision.

## Run the procedure

1. Pin the upstream reference implementation, model revision, weights, tokenizer/processor, input and decoding settings. Save the exact reference command and expected output for each requested modality. Record any stochastic comparison rule before changing the adapter.
2. Map the checkpoint and I/O contract onto the engine's loader, preprocessing, stage boundaries, operators and postprocessing. On the target device, start with the smallest real-weight input. Compare each stage against the pinned reference in execution order.
3. At the first failing stage, replay its saved reference inputs through the target stage alone. If those pass, inspect the previous stage's handoff. Otherwise inspect the implementation or weights at that stage. Change one allowed adaptation at a time.
4. Run the complete user script with the agreed features and flags. Save inputs, revisions, stage checks, output and tolerance as a replayable regression fixture. State which features and devices the fixture covers.

## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| The target is Ascend and weight scales, KV replication or a multimodal adapter prevent a real-weight run. | `ascend-model-adaptation` | Get the checkpoint and feature report. Replay the first unsupported load or stage with real weights before progressing. |
| A Flux diffusion stage agrees on the first call but diverges on reuse. | `diffusers-invocation-state` | Get the wrapper/scheduler state trace. Replay with a fresh pipeline and compare the first differing timestep. |
| The request includes a support claim and some features have only source or smoke evidence. | `claim-contract` | Map observations to the declared gates. Publish the supported subset and leave the uncovered features open. |

## Acceptance and handoff

Finish when each requested stage meets its reference check, the full model returns the accepted result on the specified target, and the saved fixture reproduces it. If a stage still fails, name its first mismatching input/output pair and the single replay that separates a loader error from an operator error.
If the allowed search space or budget is exhausted, record the blocker, the
evidence already obtained and the smallest remaining discriminating test.
