---
name: task-derived-engine
description: Use for a fork or extension that retains an upstream inference execution core, including a vLLM or vLLM-Omni derivative. Verify inherited behavior and the intended delta separately.
---

# Deliver an engine derived from a pinned parent

## Capture the actual run

Record the hardware vendor, device SKU, backend and driver, OS, model family and
checkpoint revision, engine and plugin versions, and the exact run script and
flags. Attach the benchmark inputs, workload shape, dtype, reference or quality
oracle, and the user's acceptance criteria. Write down the current diagnosis
and its supporting observation, allowed search space, and remaining budget.
Mark missing fields as unknown and request the first one that affects a decision.

## Run the procedure

1. Pin the parent repository, revision, build and known-good run. Identify inherited modules and the fork-owned seam. State what API, model behavior and state ownership must be preserved and what observable behavior should change.
2. Run the actual model, script and flags on the parent. Capture outputs, state transitions and benchmark results. Build the smallest fork slice at the chosen seam on the same target.
3. Run a matched inherited-path check with the extension disabled or bypassed where supported. Run a separate case that exercises the intended delta. At the first mismatch, replay the same input at the parent/fork boundary before extending the change.
4. Repeat end to end with the user's flags and acceptance workload. Report inherited-path regressions, delta behavior, and performance or memory trade-offs separately.

## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| The parent and fork changed the same subsystem at different revisions. | `repository-evolution-analysis` | Locate the inherited contract and divergence point in history. Test the last shared behavior and then the fork-owned change. |
| The fork compacts replay or prefill rows across a windowed-attention state boundary. | `bound-windowed-attention-replay` | Derive the retain/dependency rule. Test at the rollback and window boundaries before accepting the reduced state. |
| The fork changes speculative verification and draft acceptance varies by position. | `budget-speculative-verification` | Obtain a per-position acceptance and cost model. Test the proposed row budget against the parent at matched quality. |
| The new path changes scheduling or outputs and current benchmarks exercise only parent behavior. | `inference-benchmark-design` | Define matched controls and a delta-exercising workload. Run both on the same device before accepting the fork. |

## Acceptance and handoff

Finish when the inherited-path checks pass, the intended delta is demonstrated by a distinct test, and both are reproducible on the named target under the user's gates. If both paths regress, isolate the first common initialization or dispatch boundary before changing the extension.
If the allowed search space or budget is exhausted, record the blocker, the
evidence already obtained and the smallest remaining discriminating test.
