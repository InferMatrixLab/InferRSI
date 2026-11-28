---
name: task-accuracy
description: Use when inference completes but tokens, audio, frames, tensors or a quality metric diverge from a reference. Trace the first divergence and verify end-to-end tolerance.
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
        "accuracy"
      ],
      "empirical_validation": "not_run",
      "searchspace_not_applicable": "The procedure selects supporting evidence and tests within the caller's declared search space.",
      "applicability": {
        "scope": "Modality-specific reference parity and accuracy regression repair.",
        "input_contract": "Actual hardware, model, engine, script and flags, benchmark, acceptance criteria, current diagnosis, permitted changes and budget.",
        "produced_artifact": "First-divergence trace, before/after oracle results and held-out end-to-end quality checks.",
        "refusal_point": "Record missing evidence or an exhausted search budget and identify the smallest discriminating test before declaring success."
      },
      "provenance_readsets": []
    }
---

# Repair a numerical or output-quality regression

## Capture the actual run

Record the hardware vendor, device SKU, backend and driver, OS, model family and
checkpoint revision, engine and plugin versions, and the exact run script and
flags. Attach the benchmark inputs, workload shape, dtype, reference or quality
oracle, and the user's acceptance criteria. Write down the current diagnosis
and its supporting observation, allowed search space, and remaining budget.
Mark missing fields as unknown and request the first one that affects a decision.

## Run the procedure

1. Freeze the model revision, reference outputs, inputs, seeds, preprocessing, dtype and sampling flags. Define the user's end-to-end tolerance and how the oracle handles ordinary variation. Replay both the reference and failing target with the supplied script.
2. Compare aligned stage outputs, then the first divergent token, frame or tensor. For TTS, distinguish text normalization, codec tokens and decoded audio. Feed a saved reference intermediate to the target stage to distinguish an upstream handoff error from a local math error.
3. If quality changed after an upgrade, replay the last-good and current combinations on identical inputs. Add version alignment as a secondary task if only the target combination fails. If both fail, continue tracing the divergence against the reference.
4. Change one in-scope implementation or configuration. Re-run the original and held-out inputs, including the complete postprocessing path, and report any latency or resource trade-off.

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

## Acceptance and handoff

Finish when the first divergence is explained, the original and held-out end-to-end outputs meet the user's tolerance on the actual target, and trade-offs are reported. If only an analogue exists (for example Ascend evidence for Windows TTS), identify the missing target sample and the smallest stage replay that tests transfer.
If the allowed search space or budget is exhausted, record the blocker, the
evidence already obtained and the smallest remaining discriminating test.
