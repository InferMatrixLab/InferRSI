# Service-reuse project campaigns

Ordinary projects can explicitly choose `--evaluation-mode service_reuse`.
AB/BA remains the default, and packaged `benchmarks session` tasks keep their
existing protocol. Before search, supply the model, workload, quality task and
numerical acceptance thresholds. To collect supplementary profiling evidence,
include a profiler in the same protocol.

The existing `optimization_session` entry assembles the mode inside the shared
`harness.optimization` controller. There is one campaign lock, plan and state;
Apps projects those records without writing selection decisions.

## Prepare the protocol

Use the Git checkout root and commit the declared project inputs first. The
controller records the source repository and commit, and rebuilds each execution
workspace from that commit's Git objects, including baseline, reference refresh
and final. It reads declared tree members and raw blobs directly, preserving their
executable modes while making copies read-only; archive export attributes cannot
omit or rewrite inputs. Keep those repositories and commits available throughout
the campaign.
Replacing a retained directory does not replace the executed version; an unavailable
source commit makes execution INCONCLUSIVE. Older records without a source repository
cannot establish that binding and must start a new campaign.
The protocol directory contains the caller's scripts and
any declared inputs. Campaign output must be outside the project and protocol.

Supply a JSON file with these fields; every threshold and workload is explicit:

| Field | Contract |
| --- | --- |
| `schema_version`, `protocol_id` | Integer 1 and a nonempty caller-owned protocol ID |
| `conditions` | `id`, `workload`, `model`, `precision`, `topology`, `runtime`, `timing_scope`, and an `effective_config` object |
| `commands` | Argv arrays for `precheck`, `service`, `ready`, `warmup`, `measure`, `quality` and `stop`, each using a retained `{protocol}` script. Add `profile` to enable capture |
| `sampling` | Positive `stage_timeout_seconds` and optional positive `profile_timeout_seconds`. Each of `baseline`, `candidate` and `final` declares positive integer `repetitions` and nonnegative integer `warmups`. Zero warmups require `warmup_reason` |
| `scenarios` | Objects declaring unique string `id`, `workload`, positive integer `requests`, and positive integer `required_successes` no greater than requests |
| `objectives` | Objects described below; at least one participates in gain assessment |
| `ranking` | Unique objective IDs in priority order |
| `quality` | `mode`, `dataset`, `scorer`, `key`, `direction`, positive integer `samples`, plus the corresponding quality gate |
| `stagnation` | `{"disabled": true}`, or positive integer `rounds` and `action` equal to `advisory` or `pause` |
| `screening` | Optional argv `command` and positive `estimated_gain`; the estimate never replaces a formal gate |

An objective declares `id`, `scenario`, dotted JSON `key`, `unit`, finite inclusive
`domain: {"min": ..., "max": ...}`, `direction` (`minimize`/`maximize`),
`aggregate` (`median`/`mean`), `threshold_type`, boolean `gain`, `gain_threshold`,
`parent_regression_limit`, and `cumulative_regression_limit`. Gates must be
finite and nonnegative. Threshold types are `relative_percent`, `absolute`,
and `percentage_point`; the last uses percent values and unit `%`. Use absolute
thresholds for negative-valued domains.

For quality, `absolute` requires `threshold`. `baseline_comparison` requires
nonnegative `tolerance` and compares with the compatible retained baseline score.
By default the baseline service collects the reference after its performance.
An optional `reference_path` points inside the retained protocol to a compatible
existing baseline quality result. In addition to the quality-result fields,
that result declares `revision`, `conditions`, `service_id`, and `run_id`.
Missing or incompatible reference evidence is INCONCLUSIVE.

Commands are argv, not shell fragments. Put environment setup and pipelines in
reviewed project scripts. Available replacements are `{python}`, `{protocol}`,
`{candidate}`, `{baseline}`, `{attempt_dir}`, `{effective_config}`,
`{service_receipt}`, and, for finite client commands, `{result}`. Scripts also
receive `INFERRSI_ATTEMPT_REQUEST`, identifying the retained request document.
Use runtime secret injection; do not put credentials into these records.

## Service and result interfaces

The `service` command stays in the foreground. Harness owns its process group
or Windows Job through the complete attempt. A short-lived launcher that leaves
an unowned server behind is unsupported. `--evaluation-prefix`, when supplied,
wraps this foreground service. Remote resource ownership needs its own project
adapter; a bare pre-existing endpoint is insufficient.

`precheck` writes `status: completed` and boolean `passed`. All other clients
write an object with `status: completed` and `binding` equal to the attempt's
request document. The adapter must derive the binding from the actual service,
loaded code and configuration, rather than simply echoing supplied paths.

`ready` additionally returns `ready: true`, `ownership: local_process_domain`,
`owner_pid` equal to the foreground owner PID, `loaded_root` equal to the actual
execution copy, and `loaded_revision` equal to the retained revision. The caller's
startup script can write its endpoint into `{service_receipt}` for clients.
Harness checks service liveness and binding between stages.

Each measurement result contains `scenarios[scenario_id]` with `workload`, actual
`requests`, `successes`, the declared metric fields, and `units[objective_id]`.
Every repetition covers every required scenario. Warmup results are separate.
Quality results contain `dataset`, `scorer`, `samples`, and the declared numeric
score field. An explicit `status: candidate_failure` from precheck/quality is a
rejection; crashes, absent evidence and incompatible results are INCONCLUSIVE.

A candidate profile returns `validated: true`, nonempty attempt-relative
`artifacts`, and numeric host-clock `capture_started_at`/`capture_ended_at` within
the profile stage. Its project script owns actual profiling and validation.
Harness retains the full receipt in `execution/profile/result.json` and checks
that the listed artifacts exist and are nonempty. Round records store the receipt
path, binding, capture interval and artifact locations. Collector-specific payloads
stay in the receipt. The capture interval and artifact locations share a 32 KiB
limit on their encoded JSON size. Exceeding it reports a profiling error and the
evaluation keeps its performance and quality verdict.
Performance samples exclude profiling requests and time. `stop` returns `cleanup_complete: true`;
Harness also stops and verifies its owned process domain. Unknown cleanup blocks
further execution until investigated.

Cleanup has a separate bounded window of `sampling.stage_timeout_seconds`, starting
when `stop` is invoked even if the evaluation deadline was exhausted. This window
is additional to the evaluation/campaign budget and is recorded as
`cleanup_timeout_seconds` with `cleanup_budget_scope: separate_from_evaluation`.
It applies per service, including each service in a reference refresh. Owned process
termination still runs afterward. A successful cleanup does not change a timed-out
evaluation's INCONCLUSIVE verdict.

## Lifecycle

Use `campaign start --help` for shared budget/input arguments. In service mode
supply `--evaluation-config <protocol.json>` and omit the AB/BA single-metric,
quality-command and sampling flags. Mixing both parameter sets is an error.

```text
inferrsi campaign start --evaluation-mode service_reuse --evaluation-config <protocol.json> ...
inferrsi campaign baseline --session <campaign>
inferrsi campaign diagnose --session <campaign> --bottleneck <description> --evidence <summary.txt>
inferrsi campaign knowledge --session <campaign> --query <cue> --context-bytes <bytes>
inferrsi campaign round --session <campaign> --candidate <committed-project> --hypothesis <text>
inferrsi campaign profile --session <campaign> --round <round-number>
inferrsi campaign status --session <campaign>
inferrsi campaign final --session <campaign> --reason <stop-reason>
```

`start` prepares the campaign records. The baseline establishes reference
measurements. Record measured bottleneck evidence before knowledge retrieval
or candidate search, and again after a reference refresh. This summary can use
existing measurements. Managed profiling remains optional.

A candidate first passes functional checks and service readiness,
then completes its warmup. While that service remains usable and evaluation time
remains, the harness runs all formal scenarios and repetitions, including after
a screening rejection or screening command error. Only formal performance
samples enter the aggregates.

| Formal performance | Quality | Candidate verdict | Inline capture on the same service |
| --- | --- | --- | --- |
| Failed | Skipped | FAIL | Attempt when configured |
| Passed | Passed | PASS | Attempt when configured |
| Passed | Failed | FAIL | Skipped |
| Missing, invalid or interrupted | Skipped | INCONCLUSIVE | Skipped |
| Passed | Missing, invalid or interrupted | INCONCLUSIVE | Skipped |

Every constrained metric must satisfy both parent-relative and initial-baseline
cumulative regression limits, and at least one designated metric must improve
strictly and reach its formal gain threshold. Values are ranked lexicographically
in their own units, with exact ties retaining the incumbent. A passing candidate
can remain unselected; acceptance and selection are recorded separately.
Relative zero-to-zero change is zero, never a gain; zero-to-nonzero relative
change is undefined and INCONCLUSIVE. Declare absolute/percentage-point gates
before search when zero-capable metrics need those transitions.

## Failure and recovery

Before inline capture, the harness saves the candidate's formal evidence, quality
result or skip, gate assessment and attempt binding. A failed capture returns a
diagnostic to the agent with its stage, available error details and log location
when recorded. Round acceptance, ranking, progression and final eligibility
follow the required evaluation evidence.

```text
inferrsi campaign recover --session <campaign>
inferrsi campaign round --session <campaign> --candidate <committed-project> \
  --hypothesis <text> --retry-of <attempt-id> --repair-reason <investigation>
```

`recover` collects existing records. After verified cleanup, it settles a
checkpointed PASS or FAIL without rerunning performance or quality. A crash
during capture makes the recorded diagnostic available on recovery. An explicit
retry of an inconclusive round starts a fresh evaluation in the same logical
round. Use optional `--repair-protocol <directory>` on that retry to retain
repaired execution scripts. Later rounds use the retained repair, while final
uses its selected attempt's scripts, revision and effective configuration.
Changes to the numeric gates or quality declaration require a new protocol.

Inline capture has its own `sampling.profile_timeout_seconds`, which defaults
to `sampling.stage_timeout_seconds`. The campaign lock remains held during
capture. The campaign clock credits proven profiling-only time once per capture,
and uses the adjusted time for status, evaluation deadlines, admission and
final. The configured final reserve stays fixed. If capture was interrupted,
a durable end or progress record establishes the credit. A start record alone
earns zero seconds, and downtime before recovery counts against the campaign.
Round `elapsed_seconds` and campaign `wall_elapsed_seconds` show actual wall
time. External job and agent deadlines still apply.

After an interrupted process with unverified cleanup, `recover`, `resume` or an
explicit retry can take `--cleanup-receipt <inspection.json>`. The receipt names
`attempt_id`, positive numeric `observed_at`, `reason`, `cleanup_complete: true`,
and `services`, covering each recorded owner with `service_id`, `pid`, and
`domain_empty: true`. Harness checks recorded POSIX groups are empty as well.
This is explicit investigation evidence; no automatic cleanup or measurement
retry is inferred. `resume --reason <text>` records an advisory-pause or explicit
abandonment decision; it does not make an incomplete attempt pass or satisfy an
exact-round policy.

If conditions change, use `refresh-references --conditions <json> --reason <text>`.
This requires room for a new candidate round; when the round budget is exhausted,
the command rejects the refresh before changing conditions or starting a service.
It measures the original baseline and comparison parent under the new conditions
(one run when they are the same version), retains both old/new records, and does
not collect another parent profile. This restores comparison references only.
The original baseline uses or collects compatible quality evidence as declared
by the quality protocol. A distinct parent's refresh runs performance only; it
does not consume the baseline quality cache or require another quality test.
Final requires a new candidate to pass performance and quality under the current
conditions. This also applies when returning to earlier conditions. Captures from
earlier rounds remain associated with their original conditions.

Final selects only from current-condition acceptances after a condition change.
Without them it records INCONCLUSIVE and the missing-acceptance reason without
starting a final service or collecting a profile. Otherwise it independently
retests the retained selection against its acceptance parent and initial baseline,
not against itself. If baseline remains selected without a condition change,
it validates baseline evidence without requiring a gain over itself. Final
rechecks the selected revision and effective configuration. It verifies the
required warmup and measurement receipts for the selection and its reference
runs under the applicable conditions, then collects performance and quality on
its own service.

## Profiling a settled round

Run `inferrsi campaign profile --session <campaign> --round <round-number>` to
capture the last settled PASS or FAIL attempt of that round. This also works
after the evaluation deadline or a completed final. The retained revision,
protocol, effective configuration and conditions must be reproducible, the
protocol must include a profiler, and prior cleanup must be verified. A busy
campaign lock makes the command return immediately.

The command starts a fresh service with its own service ID and run ID. Startup,
readiness, required warmup and capture share the profiling timeout. Cleanup
uses its separate bounded window. Each capture has its own directory linked
to the original attempt. After validation and verified cleanup, the harness
publishes the new paths through the attempt's backfill index. Earlier evidence,
including the inline receipt, remains available. A failed backfill keeps the
previous usable capture in the round summary. The campaign credits time spent
validating and publishing the backfill as well as time spent collecting it.
Recovery credits recorded progress and the work performed during recovery
under the same capture ID. Time spent offline remains on the campaign clock.

The command exits with 0 for a newly published capture, 2 for ineligible input,
busy or unresolved cleanup, or capture failure (including timeout), and 130 for
operator interruption after cleanup is attempted. Failure details appear in the
command diagnostic and capture logs. An interruption before index publication
preserves the previous capture. Once the new index entry is durable it remains
available, including if the caller is interrupted before receiving the result.
Large errors have a bounded summary.
When available, `details_path` locates the full error or stage receipt relative
to the campaign directory.

The `rounds` list in `campaign status` shows the latest recorded attempt of every
round, including after finalization. The CLI and dashboard show `"profiling": {"available": false}` for a round
without a usable capture. When available, `result` and `artifacts` contain
campaign-relative paths. The latest usable backfill takes precedence over inline
evidence in this field. Selection records identify the original attempt.
The CLI's `best.profile` and the summary's `selected_candidate.profile` show
the inline profile recorded at selection time. Older records use the same
availability validation at read time and retain their original verdict.
For previously settled rounds with oversized embedded profiler
output, the reader verifies the observation against the campaign control record.
New snapshots of these attempts display the old capture's receipt path.
Oversized collector errors display a short diagnostic.
A different runtime can display these records. In an active
campaign, `status` reports `can_finalize: false` and
`final_block_reason: runtime_version_mismatch` until the operator uses the
version shown in `recorded_runtime_version`.

## Records, compatibility and validation

Plan schema 3/state schema 2 are specific to service reuse. Missing mode means
legacy AB/BA; old plans are not converted. Legacy sessions still require their recorded runtime for resume. This mode stores commit records,
configuration values, ownership/run IDs and raw evidence without calculating,
verifying or displaying file/content fingerprints. Runtime checks cover the
recorded installed package version; this is not a source-byte integrity claim.
Readonly retained inputs and value/identity checks do not provide cryptographic
tamper detection. Old AB/BA and other APIs retain their default checks.

`dashboard --input <campaign>` displays separate objective units, stage results,
selection, repair history, reference epoch, reminders and final prerequisites.
There is no summed multi-objective speedup. Service-mode knowledge capture retains
source text and existing commit attribution without the old content-identity
reader. It uses Find ranking over the package catalog and records core documents
and unloaded references. Checkout and store sources require content identity
and are unavailable in this mode.
Captured material proves preparation, not model consumption.

`summary.usage` covers caller-supplied round-attempt exports, including explicit
repair attempts; `other_attempt_usage` is separate. Unknown usage stays unknown,
and recovering a settled attempt never imports or counts the same usage twice.

Consecutive complete rejections may trigger the declared system-wide analysis
reminder. Every accepted gain resets the streak, even when ranking leaves the
candidate unselected. A new reference epoch resets the streak and notification
flag while retaining earlier events. Infrastructure/cancelled/incomplete attempts
do not count; recovery does not double-count. Advisory does not pause execution;
explicit pause is resumed with a reason.

The synthetic CPU controls are `tests/harness/test_project_objectives.py`,
`tests/apps/test_project_service_reuse.py` and `tests/harness/test_service_backfill_recovery.py`.
The service tests use temporary loopback services and guard fingerprint helpers
from before campaign creation. Run them where loopback sockets are available.
They require only CPU resources. In a workspace forbidding fingerprints, run
unchanged-default AB/BA and packaged-task regressions in a separately authorized
environment. CPU controls cannot establish real-model quality or service gains.
