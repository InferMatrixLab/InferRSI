# EPD GPU allocation from cold-stage capacity

External author-reported cold-serving observation. Formal campaign acceptance
remains INCONCLUSIVE. Source identities, inspected artifact hashes and scope
belong to the [source record](epd-cold-provisioning.json).

The original six-wave measurement and a nine-wave order follow-up completed.
Formal acceptance is INCONCLUSIVE
because the published evidence lacks a prospectively frozen acceptance
gate, an independently checked model-weight revision and complete
independently verified runtime and raw-trace artifacts. The limited repeats
also leave uncertainty about repeatability. No numerical acceptance
threshold is inferred after observing these results.

## Decision and mechanism

For disaggregated multimodal serving, let N be the available GPUs, e the
encoder GPU count, and mu_E and mu_PD the effective per-instance completion
rates for encoding and combined prefill/decode. One GPU serves each instance.
Both rates have units of completed requests per second per instance for
the same request mix and generation policy. Pool capacity and C(e) have
units of completed requests per second. The measured four-GPU feasible
encoder counts are 1, 2 and 3, with 4 - e GPUs assigned to PD.
The capacity proxy is

```text
C(e) = min(e * mu_E, (N - e) * mu_PD),  1 <= e < N
e_fractional = N * mu_PD / (mu_E + mu_PD)
```

The implementation evaluates feasible floor and ceiling neighbors of the
fractional crossing and selects the maximum. It can retain an incumbent that
ties for the maximum. Stage rates are inputs with workload-specific uncertainty.
This rule assumes useful stage capacity scales with instance count under the
deployment's routing and transfer behavior. Verify that assumption with the
complete serving path. Preprocessing, embedding transfer, shared host and
storage contention, routing imbalance and batching effects have no separate
terms in this expression. They must be reflected in matched effective rates
or investigated through a more appropriate model.
The [allocator implementation](https://github.com/Kelvin-Al/epd-provisioning/blob/3ed184e3a83229806a9fa1adb2bc75f1744c6518/planner.py)
provides the exact integer and tie behavior.

For positive constant stage rates, this minimum is increasing before the
crossing and decreasing after it. Evaluating its feasible floor and ceiling
neighbors therefore finds an integer maximizer within this model for any
integer GPU budget of at least two. The H800 comparisons provide an empirical
check of the capacity estimates and deployment assumptions on one task.

## Cold observation

The frozen sizing inputs estimated 25.10 requests/s per E and 13.71 per PD.
For four GPUs, the capacity proxy gives 25.10 for 1E:3PD, 27.43 for 2E:2PD,
and 13.71 for 3E:1PD. It therefore recommends 2E:2PD for those inputs.

The completed cold comparison ran all three splits in one allocation on
four NVIDIA H800 GPUs. The encoder counts were run in the orders
`[1, 2, 3]` and `[3, 2, 1]`. Reversal swapped the outer splits and kept
2E:2PD in the middle, leaving its effect confounded with second position.

| Round | 1E:3PD completions/s | 2E:2PD completions/s | 3E:1PD completions/s |
| --- | ---: | ---: | ---: |
| 1 | 23.17 | 25.90 | 13.14 |
| 2 | 23.25 | 26.21 | 13.45 |

2E:2PD ranked first in both rounds. Relative to second-place 1E:3PD, its
completion rate was 11.8% and 12.7% higher. Its P90 time to first token was
6.48 s and 5.69 s, compared with 9.63 s and 9.68 s for 1E:3PD.
Every wave completed all 720 requests without failures and recorded 720
visual forward calls, 720 encoded images, zero EC hits and zero resident hits.
These are descriptive observations from the
[published cold results](https://github.com/Kelvin-Al/epd-provisioning/blob/3ed184e3a83229806a9fa1adb2bc75f1744c6518/experiments/ec-cache/results/cold/results.json).

## Position-balanced cold follow-up

A [frozen follow-up plan](https://github.com/Kelvin-Al/epd-provisioning/blob/a0037f7ddc4b1af5f59fbef0a86b2a5627b69feb/experiments/ec-cache/results/cold-order-followup/plan.json)
cycled encoder counts as `[1, 2, 3]`, `[2, 3, 1]` and `[3, 1, 2]`.
All nine waves ran in one four-H800 allocation on the original node.
The cohort, seed, cold checks, target arrival rate and measurement window
were held to the original settings. Each split occupied each position once.

| Round | 2E:2PD position | 1E:3PD completions/s | 2E:2PD completions/s | 3E:1PD completions/s |
| --- | --- | ---: | ---: | ---: |
| 1 | Second | 23.59 | 26.44 | 13.00 |
| 2 | First | 23.52 | 26.04 | 13.55 |
| 3 | Third | 23.44 | 26.67 | 13.31 |

2E:2PD ranked first in all three rounds, ahead of 1E:3PD by 12.1%, 10.7%
and 13.8%, respectively. All nine waves completed 720 requests with no
failures and recorded 720 visual forwards, 720 encoded images, zero EC
hits and zero resident hits per wave. The ranking thus held when 2E:2PD
ran first, second and third under the tested conditions.
See the [complete follow-up results](https://github.com/Kelvin-Al/epd-provisioning/blob/a0037f7ddc4b1af5f59fbef0a86b2a5627b69feb/experiments/ec-cache/results/cold-order-followup/results.json).

An [interrupted follow-up attempt](https://github.com/Kelvin-Al/epd-provisioning/blob/a0037f7ddc4b1af5f59fbef0a86b2a5627b69feb/experiments/ec-cache/results/cold-order-followup/interrupted-results.json)
completed six waves before a port conflict on worker startup. The
comparison above uses only the complete rerun, with a launcher precheck
for available serving ports outside the system ephemeral range.

## Applicability and limits

The tested deployment used Qwen2.5-VL-3B-Instruct, a prepared vLLM 0.33.0
overlay, a filesystem EC connector, one GPU per worker, one encoder sequence
at a time, 1 GiB PD KV storage and 512-token PD chunks. The cohort contained
720 single-image MMMU validation questions with fixed 64-token generation.
Of the images, 700 were resized into the encoder calibration range.
The model weight revision is absent from the published plan.

Each wave started fresh workers and empty EC storage. A request-scoped
media key shared by E and PD required a new encode even for repeated images.
The target arrival rate was 34.27 requests/s. Actual seeded arrival rates
were 34.473–34.474 requests/s initially and 34.471–34.475 requests/s in
the follow-up. Completion counters use the middle 60% of
actual arrivals, about 12.5 seconds. The counts include all completed requests
after drain separately from the central-window rate.

The follow-up observes each split and position combination once. It balances
positions within this workload and leaves limited evidence about predecessor
effects and between-wave variability. The observations cover a finite
arrival window at one offered rate. Sustained saturation, service SLOs
and MMMU answer accuracy remain unqualified. The first attempt at the
original cold comparison failed because its proxy assigned inconsistent
E/PD media keys. The corrected original run supplied the six-wave comparison.

Recalibration is required when stage cost ratios, batch/concurrency limits,
hardware, model, transport or preprocessing change. This cold observation
does not establish empirical rankings for other GPU counts, non-multimodal
workloads, different cache policies or heterogeneous workers. Extra stages
and shared bottlenecks need an appropriate capacity model.

For a conclusive future campaign, first agree and freeze its acceptance
criteria, sample size and repetitions. Bind the exact model and runtime,
retain independently checkable traces and workload bytes, qualify the
specified transport/preprocessing regime, and independently review the
complete serving comparison. More repetitions alone cannot repair missing
identity or acceptance evidence.

## How to use this case

1. Freeze GPU budget, model/runtime identity, preprocessing, output length,
   routing, EC policy and the workload before selecting a configuration.
2. Estimate both stage rates independently for that workload. Check that
   observation windows and calibration conditions match the serving run.
3. Calculate the integer split and record all tied optima. For four GPUs,
   1E:3PD exceeds 2E:2PD in this capacity model when mu_E > 2 * mu_PD.
4. Compare the recommendation and feasible alternatives with the same seeded
   requests and arrival schedule. Counterbalance all positions so each split
   appears equally often in each position. Counterbalance predecessor pairs
   if carryover is a concern, and retain failures.
5. Audit actual visual work and cache decisions. Align E/PD success counters
   to the same arrival window and inspect queues alongside TTFT and TPOT.
6. If the recommendation misses, inspect stage estimates and deployment
   assumptions. Recalibrate changed conditions before applying the split.
   Retain the previous deployment as the rollback configuration.

The single E completed about 23 requests/s in this cold sweep and queued
173–175 requests at peak. With two E workers the pool kept up with about
34 requests/s, while PD completion remained about 26 requests/s.
This gives a concrete signal for distinguishing insufficient encoder
capacity from PD pressure under the tested conditions.

## Evidence access

- [Frozen cold plan](https://github.com/Kelvin-Al/epd-provisioning/blob/3ed184e3a83229806a9fa1adb2bc75f1744c6518/experiments/ec-cache/results/cold/plan.json).
- [External experiment issue](https://github.com/Kelvin-Al/epd-provisioning/issues/1).
- [Knowledge contribution scope](https://github.com/InferMatrixLab/InferRSI/issues/505).

The source record retains SHA-256 values for the fetched published files.
Both evidence snapshots are pinned. Subsequent upstream changes leave these
snapshots historical. Further changes to the case observations require
rechecking the affected evidence and applicability at a pinned revision.
The underlying worker logs, image bytes, container and model weights were
not independently replayed or verified during extraction. Stage estimates
and measured counts remain bounded by that external evidence.
