---
name: audit-fixed-workload-claim
description: Audit a performance claim from supplied fixed-workload reports and an explicit measurement contract. Check aggregation, retained observations, comparability and quality evidence without launching new benchmarks.
metadata:
  inferrsi: |
    {
      "status": "candidate",
      "origin": [
        "internal"
      ],
      "tags": [
        "performance",
        "audit",
        "measurement"
      ],
      "empirical_validation": "not_run",
      "applicability": {
        "scope": "Auditing a performance claim against supplied fixed-workload reports and an explicit measurement contract: aggregation, retained observations, comparability and quality evidence",
        "input_contract": "Baseline and candidate fixed-workload reports with request observations grouped by trial and workload; the measurement contract stating metric, unit, timing boundary, improvement direction, aggregation rule and order, fixed exclusions, threshold and comparison operator; the declared quality and completion evidence; the requested output schema",
        "produced_artifact": "An audit conclusion showing baseline and candidate aggregates, the calculation, the threshold comparison and the evidence or missing information that controls the verdict; it interprets supplied evidence and does not itself establish a measured improvement",
        "failure_modes": [
          "A pooled request median silently replaces a median of per-trial means, or the reverse, reweighting trials whose request counts differ",
          "Late requests, failures or outliers are dropped, or requests move between trials, outside the exclusions the contract fixes",
          "Values are rounded before the threshold comparison",
          "A missing rule that permits different verdicts is resolved toward the favorable one",
          "A speed improvement is read as task success, or a quality pass as equivalent measured work",
          "Different workloads or incomplete observations are repaired by a favorable aggregate"
        ],
        "refusal_point": "Does not replace missing evidence with a pass, does not support a percentage claim on an undefined denominator, and does not launch a new benchmark or alter the contract to resolve an unfavorable result; a failed threshold is reported apart from an unverified comparison or missing quality evidence"
      },
      "recommendations": [
        "Recover the contract's metric, direction, aggregation order and comparison operator before reading the report's own verdict.",
        "Treat a named minimum bound as >= and a maximum bound as <= unless the contract requires a strict comparison.",
        "Keep separate regimes and metrics separate unless the contract defines their aggregation."
      ],
      "limitations": [
        "Guidance for supplied reports; no local efficacy validation or measured performance gain is established."
      ],
      "searchspace_not_applicable": "SKILL.md §§ Preserve the observation hierarchy, Check what was actually compared, and Return an auditable conclusion audit supplied measurements and verdicts; device identity is comparison metadata, not a hardware-resource mechanism."
    }
---

# Audit a Fixed-Workload Claim

Status: candidate. This procedure interprets supplied evidence; it does not
establish a measured improvement by itself.

## Recover the declared decision

Identify the metric, unit, timing boundary, improvement direction, aggregation
rule and threshold from the supplied contract. Separate these from the report's
own verdict. Use the contract's comparison operator, including how equality is
treated.
Treat a named minimum/min bound as inclusive (`>=`) and a maximum/max bound as
inclusive (`<=`), unless the contract explicitly requires a strict comparison.
If a missing rule permits different verdicts, expose the ambiguity
instead of choosing the favorable interpretation.

## Preserve the observation hierarchy

Keep request observations inside their original trials and workload groups.
Do not discard late requests, failures or outliers merely because they weaken
the claim. Apply only exclusions fixed by the measurement contract, and report
their counts and reasons. Do not move requests between trials.

Apply the declared reduction in its stated order. For example, a median of
per-trial request means first averages every included request in each trial,
then takes the median of those means. A pooled request median is a different
statistic; it weights trials differently when request counts differ. Neither
operation may silently replace the other.

Retain units and enough precision to evaluate the threshold before rounding.
For a lower-is-better metric with a positive baseline, percentage reduction is
`100 * (baseline - candidate) / baseline`. For a higher-is-better metric,
percentage improvement is `100 * (candidate - baseline) / baseline`.
An undefined denominator cannot support a percentage claim.

## Check what was actually compared

Verify the model and code revisions, device resources, input workload, request
counts, warmup, timing boundaries and load settings needed by this claim.
Missing metadata stays unknown. Different workloads or incomplete observations
cannot be repaired by a favorable aggregate. Keep separate regimes and metrics
separate unless the contract defines their aggregation.

Check the declared quality and completion evidence independently of timing.
A numerical speed improvement does not establish task success; a quality pass
does not establish equivalent measured work. Flag differences in output work,
failure accounting or execution coverage that limit the comparison.

## Return an auditable conclusion

Show the baseline and candidate aggregates, the calculation, the threshold
comparison and the evidence or missing information that controls the verdict.
Follow the requested output schema and the contract's verdict semantics.
Distinguish a failed performance threshold from an unverified comparison or
missing quality evidence. Do not replace missing evidence with a pass, and do
not launch a new benchmark or alter the contract to resolve an unfavorable result.
