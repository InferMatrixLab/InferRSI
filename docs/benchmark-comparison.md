# Compare RSI optimization efficiency

Use the self-describing Apps entry when asked to use benchmarks to determine
whether RSI knowledge improves optimization efficiency. No extra skill is needed.

```bash
inferrsi benchmarks compare --help
inferrsi benchmarks compare
```

Knowledge is the default focus. Its default task set is
`qwen21-denoise-npu` and `moe-forward-npu`, each with knowledge **on/off**.
One repeat means four independent Agent optimizations, not four measurements
of a prewritten candidate. Repeated `--task` replaces the default task set.
Each execution Agent chooses changes from feedback, completes the exact round
budget, and independently retests its selected code with `session final`.

## Resolve and freeze configuration

CLI values override `.inferrsi/benchmarks.json` in the current workspace, then
built-ins. `--config` selects another non-secret JSON file. The resolved values
and their sources are frozen in `experiment.json`; each job references its
digest. Resume with the returned `--output`, never by preparing over that path.

Built-in budgets are eight rounds, one repeat, 60 campaign minutes, 1,200 seconds
per evaluation/final reserve, and 90 minutes per Agent job. These are bounded
run settings, not universal performance gates. Select a prepared execution
environment before dispatch. An unconfigured entry returns
`configuration_required` with an actionable request; it does not fabricate an
NPU host. Read task requirements with `benchmarks show`. A private profile can be:

```json
{
  "schema_version": 1,
  "environment_id": "prepared-ascend-pool",
  "evaluation_prefix": "npu run --gpus {devices} --timeout 18m --wait 1m --",
  "execution_instructions": "Use the existing authorized target. Return each complete campaign tree to its declared local workspace.",
  "rounds": 8,
  "repeats": 1,
  "policy": {
    "metrics": ["speedup", "wall_seconds"],
    "tolerances": {"speedup": 0.0, "wall_seconds": 0.0, "tokens": 0.0},
    "minimum_pairs": 1
  }
}
```

`{devices}` comes from each task: Qwen needs one NPU, MoE needs two. Default task
arguments are Qwen `--pairs 2 --samples 3 --warmups 1` and MoE
`--pairs 2 --timeout-seconds 900`. Override one with
`--evaluation-args 'TASK=ARGUMENTS'`. Keep allocator wait/run/cleanup within the
outer evaluation timeout. Optional `model` and `effort` are requests, not proof
of actual host settings. Credentials never belong in this configuration.

## Drive the host handoff

The command manages experiment records. The initiating Agent calls its actual
host tools for fresh-session creation and observation, following `next_action`.
This is the same native handoff as [Agent sessions](native-agent-sessions.md).
The CLI neither starts a hidden Agent CLI nor invents a conversation identity.

1. Prepare: `benchmarks compare --config <profile.json> --output <new-directory>`.
2. Read `next_action`; call `compare --action dispatch --output <directory>
   --trial <id>`. Only `may_create: true` permits one native creation call.
3. Send the exact returned prompt with the declared workspace, and supported
   requested model/effort. Bind the confirmed native ID using `--action bind`,
   `--host`, `--session-id`, optional `--host-id`, and `--receipt <host.json>`.
   Each trial needs a distinct session ID within the host, including across
   repeats. Report verification excludes trials that share a binding.
4. Observe that same session. Retain actual host observations with
   `--action record --observation <observation.json>`. Uncertain creation stays
   `dispatching`; inspecting the original call takes precedence over relaunch.
5. After termination and artifact return, call `--action collect --trial <id>`.
   Keep failed/incomplete results. Each attempt is collected once. Repeating
   collect for that attempt returns its first record with `already_collected:
   true`; it writes no new snapshot and changes neither its classification nor
   retry eligibility. Use `--action report` to re-verify current evidence.
   By default, trials run in declared order, with on/off order alternating
   between repeats. With sufficient devices, pass `--parallel` on dispatch for
   each trial you want to start while others are active. Keep each allocation
   separate and note concurrent execution when interpreting campaign wall time.
6. To retry an arm, call `--action retry --trial <id>` after collecting its
   terminal attempt. Retry is an explicit initiator decision. It is never
   automatic, and `next_action` never suggests it. It is refused while the
   current attempt is uncollected or not terminal, and when the collected
   attempt is an eligible completed result, so a valid result cannot be re-rolled.
   It is also refused while another trial is active, unless you pass `--parallel`.
   The retry keeps the collected attempt as evidence. It opens a fresh attempt
   with its own native job (`jobs/<id>-attempt-NNN`) and workspace
   (`<workspace>-attempt-NNN`), the same frozen runtime and the same prompt.
   Dispatch, bind, record and collect that attempt as in steps 2-5, with a new
   native session ID. Never rename, move or edit an earlier campaign to retry.
   Retry does not change how Harness classifies a failure.
7. Generate a progress or final comparison with `--action report`. Read
   `--action status` to resume. It shows each trial's current `attempt` and its
   `previous_attempts`. Reporting never executes missing rounds/finals.

New comparisons freeze the same diagnosis requirement for both arms. Before
search, each session profiles the frozen baseline or uses measurements from the
same workload and environment. It records the measured bottleneck with
`benchmarks session diagnose --session <campaign> --bottleneck '<observed-bottleneck>'
--evidence <measurement-summary.txt>`. The UTF-8 input should contain the
measured values and scope. Knowledge retrieval is optional when enabled and
follows the diagnosis. The comparison JSON includes diagnosis IDs for each round.
Collection verifies the retained summaries and the round-to-diagnosis links
against the original round observations.

All non-prepare actions require `--output`. Dispatch/bind/record/collect also
require `--trial`. Jobs are created just before dispatch so waiting for earlier
trials does not consume their host deadlines. Native deadline cancellation
still belongs to the initiating Agent and its supported host tools.

Native observation JSON uses the existing `agents record` format, plus:

```json
{
  "host": "<HOST>",
  "host_id": null,
  "session_id": "<NATIVE_SESSION_ID>",
  "state": "completed",
  "native_receipt": {"replace_with": "actual native tool response"},
  "benchmark_observation": {
    "model": "<ACTUALLY_OBSERVED_MODEL>",
    "effort": "<ACTUALLY_OBSERVED_EFFORT>",
    "environment_id": "prepared-ascend-pool",
    "environment_fingerprint": "<DIGEST_OF_NON_PRIVATE_RUNTIME_AND_DEVICE_PROFILE>",
    "knowledge_policy_violation": false
  }
}
```

These remain caller-exported observations, not authenticated host attestations.
Retain their underlying receipts. Include actual `usage_scope: session_total`
and `usage` counters when available; cached input is a subset of input. Final
host usage is never added to campaign round subtotals. Missing usage stays null.
Do not replace missing final counters with an earlier partial observation.

When the host reports when the native session started and ended, add that
interval to the terminal observation. It is the attempt's start and end for
attempt accounting:

```json
"native_session_window": {
  "session_id": "<NATIVE_SESSION_ID>",
  "started_at": 0,
  "ended_at": 0
}
```

Use Unix seconds from the host's own record of that session. The window must
name the bound session, must not end before it starts, and must contain the
campaign's start and end. Do not fill it from campaign timestamps or from the
time you recorded the receipt. Omit it when the host does not report it; the
attempt time then stays unknown, with a reason.

## Isolation and evidence

Every trial has a separate workspace and frozen runtime. Shared code and task
bytes match; on receives the pinned package corpus, off omits `knowledge/data`
and disables managed session retrieval. Both prompts exclude other skill
libraries, external knowledge tools, web research and prior trial solutions.
Public task/CLI instructions and ordinary target APIs remain available to both.
This is runtime-corpus isolation plus an instruction boundary; it is **not an OS
filesystem/network sandbox**. Report observed violations and bound conclusions
to this managed-knowledge treatment. Do not claim all latent or external
knowledge was removed. Remote trials return the exact full campaign tree;
arbitrary summaries cannot substitute for retained evidence.

Collection verifies the frozen task/protocol, budget, knowledge condition,
runtime identity, raw evidence and independent final candidate binding. Paired
actual model, effort and environment must match. Remote interpreter paths may
differ. Compute the environment fingerprint from the observed Python
implementation and version, framework and runtime versions, device model and
allocator profile. `python` selects the executable in the launch command.
Report generation verifies the campaign again to detect changes after collection.

Each round can supply `--strategy <description>` and repeated
`--knowledge-ref <delivered-context-path>` in addition to `--hypothesis`.
Harness accepts citations only to contexts already delivered in that campaign.
The trace labels these as Agent declarations; delivery does not prove use.
Unrecorded citations remain unknown, rather than treating every previous search
as knowledge used by every round.

## Read the report

The report leads with [Benchmark metrics](benchmark-metrics.md): each arm's
independent final speedup, accepted/assessed steps and token coverage, followed
by paired performance benefit and token consumption ratios. This versioned
summary preserves the existing comparison conclusion and old factor directions.

**Attempts and wall time** lists every retained attempt of each arm: the
attempt count, failed attempts with their statuses, the successful campaign wall
(the selected attempt's campaign wall, when that campaign completed) and the
total wall. Total wall runs from the first attempt's `native_session_window`
start to the last attempt's `native_session_window` end. It therefore includes
native start-up before a campaign exists, failed attempts, retries, wrap-up
after the last campaign and the gaps between them. Campaign start/end and receipt
arrival times are never used as attempt boundaries. When a needed boundary is
missing, invalid or unverifiable, total wall stays unknown. The **Unknown
reasons** column then names the attempt and the reason. Failed attempts are
terminal attempts without an eligible completed result; a pending or running
attempt is not counted as failed. Tokens across attempts are summed only when
every attempt has a complete `session_total` export. Otherwise they stay
unknown, and the observed subtotal is shown with `partial` coverage. Trials with
more than one attempt also get a per-attempt table.

A collected attempt keeps the status, eligibility and gaps it was collected
with. Failed attempts count only this recorded classification. A lost or changed
job therefore cannot turn a recorded failure into "not run", or a recorded
eligible completion into a failure. Report still re-reads every attempt. The
re-read is kept apart under `reverification`, with its own status, eligibility
and new gaps, and is shown as *current evidence not re-verified*. Current
evidence that does not re-verify withholds the successful campaign wall, and
the selected attempt's verdict is still re-verified live. Costs (tokens, attempt
window, campaign wall) come only from evidence that re-reads now. An attempt
whose evidence cannot be re-read has unknown cost, not its recorded cost.
Every operation strictly checks the frozen plan, the retained collection digests
of every attempt and each trial's current runtime copy before it acts. A changed
or lost collection record, current or archived, therefore stops retry, dispatch
(also with `--parallel`) and every other operation before a workspace is
published or state is written. Report checks an earlier attempt's own
runtime copy only for that attempt. A missing or changed copy is a re-read gap
of that attempt, and its cost is unknown. Its recorded classification and the
other results stay in the report. This
accounting is descriptive. The frozen verdict still uses each arm's selected
(latest) attempt, re-verified live, including its campaign `wall_seconds`, and
is unchanged.

Apps writes a new JSON/Markdown/offline-HTML report snapshot under `reports/`.
Start with the conclusion and per-task comparison, then inspect complete traces
(strategy, hypothesis, knowledge citations, round/best speedup, correctness and
selection), independent finals and evidence gaps. JSON digest links the two
readable documents to the same snapshot. Original campaign evidence is retained.

Benchmark rules compare paired on/off benefit factors: on/off speedup, off/on
wall time or tokens. The default efficiency basis is final optimization speedup
and actual campaign wall time; token usage is displayed separately. Add tokens
to policy.metrics only with comparable whole-session observations. Tolerances
are frozen relative neutral bands, not statistical significance tests.

Conclusions distinguish observed improvement, no gain, regression, tradeoff and
insufficient evidence. Missing/invalid declared pairs stay in denominators and
make the overall comparison insufficient. Statistics are per-task medians of
paired log ratios; unrelated task latencies are never pooled. Results are
descriptive within the declared tasks, budgets and repeats, never a general
knowledge-efficacy or model/service E2E claim. Set campaign-specific minimum
repeats and neutral tolerances before search when stronger evidence is needed.

Apps owns configuration, composition and presentation; Benchmark owns task and
comparison rules; Harness owns optimization execution and retained facts;
Knowledge owns the delivered material. No new core-to-core imports are added.
