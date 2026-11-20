# Benchmark metrics

Benchmark reports lead with a compact metrics summary. The detailed optimization
history, independent final, evidence gaps, usage sources and original verdict
remain below it. JSON owns the derived values; Markdown and offline HTML render
that same snapshot. Ordinary project delivery and legacy verdicts are unchanged.

| Single-run metric | Meaning |
| --- | --- |
| Final speedup | The selected implementation's independently retested speedup under the frozen task objective. A verified baseline fallback is 1.0 and explicitly identified. |
| Step acceptance | Actual best promotions / assessed candidate steps, with both counts. Correctness alone does not imply acceptance. |
| Token consumption | Whole-trial input + output counters, with input/output/cached input and coverage. Cached input is already included in input. |

Candidate failures and completed no-gain evaluations count as assessed steps.
Infrastructure failures and unresolved evidence are separate counts. Pending
finals are not new candidate steps; recovery settles the original attempt once.
Incomplete evidence remains visible. A high acceptance rate does not by itself
establish a large final performance gain.
Timeouts, unknown execution states, missing return codes and signal termination
remain unresolved even when the historical assessment calls them infrastructure
failures. `step_coverage: complete` means every submitted step is classified;
confirmed infrastructure failures remain separate and do not enter the denominator.
It does not establish campaign completion or final acceptance.

Comparison reports first show the basic metrics separately for every arm and
repeat, then the paired performance benefit (on speedup / off speedup), token
consumption ratio (on tokens / off tokens) and acceptance difference in percentage
points. Performance benefit above one and token consumption below one favor on.
The existing token **benefit** factor remains off/on; it is not renamed or inverted.

Each metric has independent paired eligibility. Missing token exports do not
erase valid performance results. Positive ratios are aggregated per task using
`exp(median(log(paired_ratio)))`, not the ratio of arm medians. A valid zero token
numerator remains zero; a zero denominator is unknown. For nonnegative ratios,
the middle sorted ratio is used for odd counts and the geometric midpoint for
even counts. Percentage-point differences use the ordinary paired median.
Missing required pairs make the formal aggregate null; `observed_only`, counts
and reasons retain the available subset. The cross-task performance benefit is
an equally weighted geometric mean only when every required task is complete.

## Frozen version and unknown values

Apps injects the Benchmark metrics policy into `plan.json` at session start and
`experiment.json` at comparison preparation. Harness retains this opaque report
metadata without importing Benchmark or changing evaluation rules. Readers use
that version; unsupported or unversioned legacy plans do not silently acquire
new metrics. New metrics use JSON null plus reasons for missing observations.
`final_kind` is null whenever final speedup is unavailable. A general-purpose
score is usable as speedup only when the frozen objective explicitly defines it
as the same speedup ratio. Report generation never reruns or reselects candidates.

## Token scope and producer

Campaign round exports and an export submitted before final are observations;
they do not establish complete whole-session cost. Reports without a verified
terminal receipt preserve their observed subtotal with partial/unknown coverage,
leaving the complete total unknown. Missing counters are never estimated from
text length or filled with zero.

Apps uses the same terminal-usage verifier for standalone and comparison reports.
For comparison it reads the receipt already collected by `agents record`.
For a standalone Benchmark, the initiating Agent records the terminal observation
with `agents record`, then exports with an explicit retained native job:

```bash
inferrsi export --input <campaign> --output <new-report> --agent-job <native-job>
```

The campaign must be inside that job's declared workspace. Its coverage declaration
also needs `campaign_plan_digest`, equal to `state.json`'s retained `plan_digest`,
to distinguish campaigns sharing a workspace. The trial ID matches the frozen
campaign condition. Without the option, no native job is inferred. The export
indexes the original job request, prompt, state and receipts, and checks both
campaign and native-job snapshot stability without changing the frozen records.

In addition to `usage_scope: session_total`
and actual input/output counters, a receipt can declare `benchmark_token_coverage`:

```json
{
  "trial_id": "<DECLARED_TRIAL_ID>",
  "session_id": "<BOUND_NATIVE_SESSION_ID>",
  "scope": "trial_agent_session",
  "campaign_plan_digest": "<RETAINED_PLAN_DIGEST_FOR_STANDALONE>",
  "started_at": 0,
  "ended_at": 0,
  "includes": {
    "pre_start": true,
    "retrieval": true,
    "failures_retries": true,
    "final": true
  }
}
```

The timestamps above are placeholders, not measurement data. Apps checks the
trial/session identities and requires the declared interval to cover the retained
campaign start through settlement, and every required inclusion flag to be true.
Only that complete declared scope can produce a token ratio. Keep the underlying
host receipt: these are caller-exported observations, not authenticated proof of
all Agent behavior. Failed or restarted sessions omitted from that scope remain
a coverage gap; do not assert the flags when their costs are unknown. Shared parent
conversation work is outside this scope and remains unattributed, rather than
being described as complete system cost. Older receipts without this information
retain their existing counters and verdict, with the new complete total unknown.

Wall time, queueing and resource contention remain auxiliary observations. This
summary introduces no composite performance/cost ranking or new acceptance gate.
