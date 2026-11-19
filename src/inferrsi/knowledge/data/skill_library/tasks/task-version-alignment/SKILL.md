---
name: task-version-alignment
description: Use for upgrades spanning inference engines, plugins, drivers or operator libraries. Isolate the incompatible boundary and qualify the requested version combination on the same workload.
---

# Validate an engine or plugin stack upgrade

## Capture the actual run

Record the hardware vendor, device SKU, backend and driver, OS, model family and
checkpoint revision, engine and plugin versions, and the exact run script and
flags. Attach the benchmark inputs, workload shape, dtype, reference or quality
oracle, and the user's acceptance criteria. Write down the current diagnosis
and its supporting observation, allowed search space, and remaining budget.
Mark missing fields as unknown and request the first one that affects a decision.

## Run the procedure

1. Inventory the known-good and requested versions of the engine, plugin, operator library, backend and driver. Include vLLM, vLLM-Omni, vLLM-Ascend and AFD Plugin where used. Keep build options, model, device and run script constant.
2. Replay the known-good and complete target stacks on the same workload. Record import/build, operator dispatch, integration and output/parity results for each supported combination.
3. Change one compatible dependency boundary at a time, or bisect a coupled pair when the components must travel together. Record unbuildable combinations explicitly. Compare effective APIs, ABI, flags and dispatch at the earliest failing step.
4. Apply the smallest in-scope pin or adapter, replay the complete target stack, and verify the rollback combination with the same script and quality/performance checks requested by the user.

## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| Several upstream revisions changed a boundary and the first incompatible change is unknown. | `repository-evolution-analysis` | Trace the history to a candidate transition. Run the same contract test immediately before and after it. |
| The changed component is vLLM-Ascend and its release, role or effective dispatch differs. | `vllm-ascend` | Get the version-specific dispatch and first failing boundary. Verify applicability against the installed stack before choosing a pin or adapter. |
| An AFD Plugin upgrade changes a CUDA P2P rank map or per-peer split. | `audit-afd-p2p-exchanges` | Compare the old and new payload ledgers. Test the first changed rank or slice with the same worker configuration. |
| A release claim spans combinations with missing hardware or parity evidence. | `claim-contract` | Map each tested combination to its gates. Publish the observed matrix and retain untested cells as unknown. |

## Acceptance and handoff

Finish when the requested target combination passes the user's original workload and gates, the changed boundary is documented, and the rollback point is verified. If only a coupled upgrade fails, state the next API or dispatch check that separates the two components.
If the allowed search space or budget is exhausted, record the blocker, the
evidence already obtained and the smallest remaining discriminating test.
