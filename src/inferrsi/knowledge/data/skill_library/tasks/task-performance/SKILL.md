---
name: task-performance
description: Use when a correct inference baseline misses a latency, throughput, memory or cost target. Compare compatible changes under the user's workload and quality gate.
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
        "performance"
      ],
      "empirical_validation": "not_run",
      "searchspace_not_applicable": "The procedure selects supporting evidence and tests within the caller's declared search space.",
      "applicability": {
        "scope": "Optimization of a specified metric under fixed workload, quality and resource constraints.",
        "input_contract": "Actual hardware, model, engine, script and flags, benchmark, acceptance criteria, current diagnosis, permitted changes and budget.",
        "produced_artifact": "Paired baseline/candidate measurements, quality checks, trade-offs and final replay.",
        "refusal_point": "Record missing evidence or an exhausted search budget and identify the smallest discriminating test before declaring success."
      },
      "provenance_readsets": []
    }
---

# Optimize a measured inference bottleneck

## Capture the actual run

First evaluate a fresh `task-performance` intake record using only information the
user stated. A generic optimization request leaves the objective, metric and
quality check open, even in a repository with existing benchmarks. Before building
or measuring, run `task intake evaluate --task task-performance --record <record.json>
--json`. When questions are returned, call the host's native question-card tool now
(on Codex Desktop, `request_user_input_async` when available). Ask the user which
outcome and quality check to use. Present repository-derived options as suggestions.
Use numbered questions if the host lacks cards. Wait for an actual reply, including
after an asynchronous card is accepted for display. A new local gate file or a
source label cannot stand in for the user's selection of an acceptance reference.

Record the hardware vendor, device SKU, backend and driver, OS, model family and
checkpoint revision, engine and plugin versions, and the exact run script and
flags. Attach the benchmark inputs, workload shape, dtype, reference or quality
oracle, and the user's acceptance criteria. Write down the current diagnosis
and its supporting observation, allowed search space, and remaining budget.
Mark missing fields as unknown and open the shared intake record
(`task intake evaluate --task task-performance`); ask only the questions it
returns. A field answered `unknown` blocks its stage instead of being asked
again. Do not derive a threshold from a request such as "make it faster": the
acceptance issue or frozen plan states it.

## Read back the task brief and obtain approval

Collect the final **numeric** performance goal (absolute bound with units, or
minimum percentage improvement over the pinned baseline), performance workload
and timing boundary. Confirm the accuracy benchmark and split, metric,
comparison, numeric threshold and unit, plus the quality check and failure
policy. A candidate retention threshold alone does not specify a final target.

For a measured campaign, prepare the intended invocation **before** the final
card: run `campaign start --prepare-intake --intake <record.json>` with the
actual launch options. Resolve any reported mismatch. Include the returned
`task_brief.campaign_launch` settings in the read-back. Preparation starts no
measurements. A planning-only brief can be reviewed without a launch.

When intake returns `brief_review: awaiting_confirmation`, read back the complete
`task_brief` in the user's language, including the target and accuracy
inequalities, benchmark, pinned setup, commands, scope, comparison and budget.
Then call the native question-card tool for a **separate** approve-or-revise
decision on that brief. Wait for a new explicit reply. Use `task intake answer`
with this revision's `q:task_brief:...` ID. Record requested changes, update the
fields and read back the new brief for fresh approval. Until approval, only
read-only preparation is allowed, even if the user answered every field or
selected an existing acceptance plan. Hand the approved record to `campaign
start --intake`; apply the approved conditions to the validator and final replay.

## Run the procedure

1. Replay the supplied benchmark unchanged. Pin requests, shape/batch mix, concurrency, warmup, timing boundary, repetitions, aggregation rule and quality oracle. Capture the baseline distribution and end-to-end output on the actual engine and device.
2. Profile the stage dominating the target metric. Separate queueing, prefill, decode, transfer or modality generation where observable. Estimate how much changing that stage can move the end-to-end metric.
3. Choose one change inside the allowed search space whose mechanism matches the measured bottleneck and the installed hardware/engine. Record the predicted profile signature. Alternate unchanged baseline and candidate trials with the same workload, quality evaluation and resource conditions.
4. After each change, compare the target metric, uncertainty and quality gate. Restore the incumbent if quality fails or the benefit is indistinguishable. Re-profile when the bottleneck moves. Recheck the selected change end to end with the original script.

## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| The supplied benchmark lacks an agreed workload boundary or modality quality oracle. | `inference-benchmark-design` | Obtain a workload and parity protocol. Resolve the missing gate and measure the baseline before comparing candidates. |
| A slow stage is visible but its contribution to the requested metric is unclear. | `performance-ceiling-analysis` | Estimate stage share and achievable headroom. Profile the next limiting stage if even eliminating this one cannot meet the target. |
| Several legal changes could address the profiled limit. | `optimization-search-policy` | Obtain a ranked shortlist with mechanisms, expected signals and cost. Test one bounded candidate, then retain or revert it using the paired evidence. |
| A prior trial appears to match the bottleneck or an earlier candidate failed. | `inference-optimization-casebook` | Retrieve the prior workload, decision and retry condition. Reuse its hypothesis only after comparing target conditions and retest on this run. |

## Acceptance and handoff

Finish when the selected candidate meets the user's metric and quality criteria on an independent end-to-end replay. If trials disagree, identify a targeted control such as an unchanged repeat to separate run variance from the candidate effect. Retain the best verified baseline if budget expires.
If the allowed search space or budget is exhausted, record the blocker, the
evidence already obtained and the smallest remaining discriminating test.
