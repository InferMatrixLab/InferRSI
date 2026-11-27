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

## Collect the measured task inputs

Open an intake record before preparing measurements. Start from the user's
stated objective and label facts by their source. A repository benchmark can
suggest a workload or metric. The user selects the outcome, the quality check
and the acceptance issue or frozen plan that supplies the gate.

```text
inferrsi task intake evaluate --task task-performance --record <record.json> --json
```

Ask the questions the command returns. Use the host's native question-card
tool, such as `request_user_input_async` on Codex Desktop, or use numbered
questions when cards are unavailable. Wait for the user's reply and record
it with `inferrsi task intake answer --record <record.json> --question <issued-id>`
and either `--value <value>` or `--unknown`. Record an explicit unknown once
and keep the dependent stage blocked until new information arrives. If a
question changes, show the reissued question and use its new ID for the reply.

Record the exact run script and flags, model and checkpoint revision, engine
and plugin versions, OS, device SKU, backend, driver, dtype, workload shape
and benchmark inputs. Include the reference outputs, observed diagnosis,
allowed search space and budget. The acceptance issue or frozen plan supplies
confirmed acceptance values. A newly created gate file still needs the user's
selection.

## Review the executable brief

Record two different performance decisions. The search needs a per-candidate
retention threshold. The independent final needs an absolute metric bound
with a unit or a minimum percentage gain over the pinned baseline. Also record
the measurement boundary, benchmark version or split, quality metric, comparison,
numeric limit, unit, evaluation command and candidate rejection policy.

Prepare the campaign using the intended launch options with
`inferrsi campaign start --prepare-intake --intake <record.json> ...`. This
stages inputs for comparison with the intake without starting measurements.
Resolve any mismatch and include the effective `task_brief.campaign_launch`
in the read-back. For service reuse, the prepared configuration supplies the
quality inequality and identifies the retained baseline if the limit is relative.

When the prepared brief reports `brief_review` as `awaiting_confirmation`, show
the full brief in the user's language. Include the metric and quality conditions,
pinned setup, commands, scope, comparison protocol and time budget. Ask for a
separate approve-or-revise decision and wait for a new explicit answer. Submit it
against the issued `q:task_brief:...` ID. Re-evaluate and show a new card if the
user revises the brief or the effective launch changes.

Use read-only preparation while approval is pending. Once the executable brief is
approved, run `inferrsi campaign start ... --intake <record.json>` with the same
options. The campaign checks the approval and retains its intake receipt for
replay. Device and service actions continue to require their own authorization.

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
