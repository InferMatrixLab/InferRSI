# Service-reuse project campaigns

Ordinary projects can explicitly choose `--evaluation-mode service_reuse`.
AB/BA remains the default, and packaged `benchmarks session` tasks keep their
existing protocol. This mode does not choose a model, workload, quality task,
profiler or numerical acceptance thresholds. The caller supplies them before
search. Local implementation does not settle pending repository-owner decisions
in issue #467 or qualify a real model.

The existing `optimization_session` entry assembles the mode inside the shared
`harness.optimization` controller. There is one campaign lock, plan and state;
Apps projects those records without writing selection decisions.

## Prepare the protocol

Use the Git checkout root and commit the declared project inputs first. The
controller extracts those files
from the recorded commit into a retained candidate; it never runs the editable
workspace as `final`. The protocol directory contains the caller's scripts and
any declared inputs. Campaign output must be outside the project and protocol.

Supply a JSON file with these fields; every threshold and workload is explicit:

| Field | Contract |
| --- | --- |
| `schema_version`, `protocol_id` | Integer 1 and a nonempty caller-owned protocol ID |
| `conditions` | `id`, `workload`, `model`, `precision`, `topology`, `runtime`, `timing_scope`, and an `effective_config` object |
| `commands` | Explicit argv arrays for `precheck`, `service`, `ready`, `warmup`, `measure`, `quality`, `profile`, `stop`; all use a retained `{protocol}` script |
| `sampling` | Positive `stage_timeout_seconds`; `baseline`, `candidate`, `final` objects each declare positive integer `repetitions` and nonnegative integer `warmups`; zero warmups also require `warmup_reason` |
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
Harness retains the receipt, checks nonempty artifacts, and associates them with
the same instance; it does not invent an integrated profiler. Performance samples
exclude profiling requests and time. `stop` returns `cleanup_complete: true`;
Harness also stops and verifies its owned process domain. Unknown cleanup blocks
further execution until investigated.

## Lifecycle

Use `campaign start --help` for shared budget/input arguments. In service mode
supply `--evaluation-config <protocol.json>` and omit the AB/BA single-metric,
quality-command and sampling flags. Mixing both parameter sets is an error.

```text
inferrsi campaign start --evaluation-mode service_reuse --evaluation-config <protocol.json> ...
inferrsi campaign baseline --session <campaign>
inferrsi campaign knowledge --session <campaign> --query <cue> --context-bytes <bytes>
inferrsi campaign round --session <campaign> --candidate <committed-project> --hypothesis <text>
inferrsi campaign status --session <campaign>
inferrsi campaign final --session <campaign> --reason <stop-reason>
```

`start` prepares records without measuring. Baseline has no profile requirement.
A candidate performs functional checks, startup/readiness, necessary warmup,
performance repetitions, quality, then profile, all on one instance. Performance
or quality rejection skips the dependent stages. Screening can schedule formal
validation for a bounded actual improvement below an estimated target; its
samples do not enter formal aggregates.

Every constrained metric must satisfy both parent-relative and initial-baseline
cumulative regression limits, and at least one designated metric must improve
strictly and reach its formal gain threshold. Values are ranked lexicographically
in their own units, with exact ties retaining the incumbent. A passing candidate
can remain unselected; acceptance and selection are recorded separately.
Relative zero-to-zero change is zero, never a gain; zero-to-nonzero relative
change is undefined and INCONCLUSIVE. Declare absolute/percentage-point gates
before search when zero-capable metrics need those transitions.

## Failure and recovery

Profile failure, interruption, invalid binding or missing output leaves the
candidate attempt INCONCLUSIVE and stops campaign execution. It cannot become a
parent or selection. Keep the completed performance/quality evidence and inspect
the exact stage and cleanup result before proceeding.

```text
inferrsi campaign recover --session <campaign>
inferrsi campaign round --session <campaign> --candidate <committed-project> \
  --hypothesis <text> --retry-of <attempt-id> --repair-reason <investigation>
```

`recover` collects existing records without launching anything. An explicit retry
creates a new attempt in the same logical round, with new service/samples and the
complete performance/quality/profile sequence. It never inherits a failed
attempt's measurements or overwrites a previous selection. Use optional
`--repair-protocol <directory>` on that retry to retain repaired execution
scripts; the numeric gates and quality declaration remain frozen. Later rounds
use the retained repair, while final uses its selected attempt's own scripts,
revision and effective configuration. Policy changes require a new approved
protocol rather than an execution-script repair.

Before committing a recovered candidate or a final verdict, Harness rechecks the
required retained profile and its attempt/service binding; final also rechecks
the selected revision and effective configuration. Missing or incompatible
evidence leaves the attempt INCONCLUSIVE and preserves the previous selection.
The execution results and any assessment made before settlement remain recorded.
These checks use structured records and artifact presence, without file fingerprints.

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
It measures the original baseline and comparison parent under the new conditions
(one run when they are the same version), retains both old/new records, and does
not collect another parent profile. This restores comparison references only.
The original baseline uses or collects compatible quality evidence as declared
by the quality protocol. A distinct parent's refresh runs performance only; it
does not consume the baseline quality cache or require another quality test.
At least one new candidate attempt must complete performance, quality and profile
and be accepted under the current conditions before final can be conclusive.
An incompatible old profile and successful reference refreshes do not satisfy
that requirement. Returning to earlier conditions also requires a fresh acceptance.

Final selects only from current-condition acceptances after a condition change.
Without them it records INCONCLUSIVE and the missing-acceptance reason without
starting a final service or collecting a profile. Otherwise it independently
retests the retained selection against its acceptance parent and initial baseline,
not against itself. If baseline remains selected without a condition change,
it validates baseline evidence without requiring a gain over itself. Final never
collects another profile and requires the selected candidate's compatible retained
profile and effective configuration.

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
reader. It records package core documents and identifies unloaded references;
checkout/store sources requiring content identity are explicitly unavailable.
Captured material proves preparation, not model consumption.

`summary.usage` covers caller-supplied round-attempt exports, including explicit
repair attempts; `other_attempt_usage` is separate. Unknown usage stays unknown,
and recovering a settled attempt never imports or counts the same usage twice.

Consecutive complete rejections/unselected candidates may trigger the declared
system-wide analysis reminder. Infrastructure/cancelled/incomplete attempts do
not count; recovery does not double-count. Advisory does not pause execution;
explicit pause is resumed with a reason.

The synthetic CPU controls are `tests/test_project_objectives.py` and
`tests/test_project_service_reuse.py`. The latter guards fingerprint helpers from
before campaign creation and uses a temporary loopback service. Run it only where
loopback sockets are authorized; it does not require GPU/NPU resources. In a
workspace forbidding fingerprints, do not run conflicting legacy tests. Run
unchanged-default AB/BA/packaged-task regression in a separately authorized
environment. CPU controls cannot establish real-model quality or service gains.
