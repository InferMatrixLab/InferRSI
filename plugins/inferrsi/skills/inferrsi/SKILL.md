---
name: inferrsi
description: Use InferRSI for day-zero model support, performance optimization, debugging, accuracy repair, engine and plugin version alignment, derived-engine development and independent runtime bring-up. Use it to research bottlenecks, run benchmark sessions and inspect controlled comparisons and evidence.
---

# InferRSI

Use the bundled InferRSI CLI for knowledge and experiment operations. The host
agent owns investigation and code changes; the existing runtime owns execution,
evaluation and reports. Load selected knowledge progressively.

## Start in the user's target workspace

Choose the task's execution location first. In DSH remote mode, use
`inferrsi_remote` with the form's tested `remote.connectionId` and operation
`cli`; pass CLI arguments such as `["--version"]` or `["--help"]` in `args`.
The bridge runs the bundled runtime with Python on the prepared remote machine.
Do not pass a local launcher path to the remote machine.

For local execution, resolve `scripts/inferrsi.py` relative to this skill
directory. Invoke it with Python 3.10+ and UTF-8 enabled. Below, `<launcher>`
means that resolved local script path, quoted when it contains spaces; it is not
a CLI command. The command examples below describe this local invocation;
remote mode passes canonical CLI arguments through the tool instead. The
launcher's `--plugin-info` is local-only; remote startup checks use `--version`
and `--help`.

```text
python -X utf8 "<launcher>" --plugin-info
python -X utf8 "<launcher>" --help
```

For setup/onboarding, check the runtime through the selected path, identify the
user's intended workspace and goal from available context, and report readiness and the next
relevant operation. Do not run benchmarks merely because setup was invoked.
The bundle needs no pip installation for its core operations. If Python is
missing on the execution machine, explain how to select/install a compatible
interpreter before continuing. Use that interpreter for subsequent calls.

Keep the current directory in the target workspace. Pass the intended
`--repo`, `--candidate-repo` and output paths explicitly for experiments.
Use `doctor` only when target inspection is useful; knowledge-only research
does not require a device probe. A detected backend is not model qualification.

## Load the primary inference task

For every inference task, select the row matching the user's requested deliverable.
All seven primary skills ship with this entrypoint. Run the selected command
through the same launcher and **read its returned `instructions` before the first
evidence search**. If it fails, stop and report the unavailable primary. When two
goals overlap, use the requested acceptance result to pick one. For example, a
quality regression following an upgrade starts with accuracy when the goal is
restored output, and with version alignment when the goal is a compatible stack.

| Requested deliverable | First knowledge command |
| --- | --- |
| Support a new model on day zero | `skills enter task-day-0` |
| Meet a performance target on a working baseline | `skills enter task-performance` |
| Diagnose a crash, hang or execution failure | `skills enter task-debug` |
| Repair an accuracy or output-quality regression | `skills enter task-accuracy` |
| Align engine, framework or plugin versions | `skills enter task-version-alignment` |
| Build a fork retaining the parent engine's execution core | `skills enter task-derived-engine` |
| Bring up an independently owned runtime on a target device and OS | `skills enter task-independent-engine` |

Use the actual vendor, device, backend, OS, model and engine versions, run
script and flags, benchmark, acceptance criteria, diagnosis and allowed search
space. The primary tells you which observation warrants a supporting skill,
what evidence to retain and which check follows. Open a secondary task only
when the run requires it. During a frozen evaluation use the assigned entry
and knowledge condition; keep the knowledge-off arm isolated. Setup, dashboard
inspection and explicit evidence-ID lookups can use their own operations.

## Confirm the task-performance inputs

Immediately after entering the primary, run the following in the target workspace.
Start a fresh record for this request. Include only values the user actually supplied
with `--source prompt`. For a request such as “optimize performance”, omit `--set`
and evaluate before building, profiling, measuring or choosing a workload and gates.

```text
python -X utf8 "<launcher>" task intake evaluate --task task-performance --record <record.json> --json
```

When the result has `needs_user_input: true`, send the first unresolved decisions to
the user now. In Codex Desktop call the available native question tool
(`request_user_input_async`, or `request_user_input` in Plan mode). Group related
fields into a small batch of concrete choices in the user's language. For example,
ask whether the user wants lower latency on one request or higher throughput at a
fixed load, and how to judge output quality. Offer relevant repository findings as
suggestions and allow a custom or unknown answer. Use numbered text only if the host
has no native question tool. End the turn waiting for the reply. An asynchronous
tool acknowledgement, a preselected option and elapsed time leave the questions open.

Only after the user's reply, record its values using `task intake answer --record
<record.json> --question <id> --value <value>` (or `--unknown`). Re-evaluate before
proceeding. Use `--source repo_inspection` for facts observed in the workspace.
A benchmark, previous run or agent-written gate may suggest conditions. The user
must identify the acceptance issue or frozen plan, directly or in an answer.
Use `--frozen <user-selected-file>` for its acceptance values. Preserve unresolved
conditions and never run a campaign without its intake to bypass open questions.
Collect a numeric final performance goal (metric, direction, absolute bound and
unit or minimum percent improvement over the baseline). Ask which benchmark,
version/split, workload and concurrency to replay. Confirm the quality metric,
comparison, numeric tolerance and unit. A script name, "faster", "no quality
loss", and a per-candidate retention default leave decisions open. A selected
plan can supply explicit criteria; show them to the user in the brief.

For a measured campaign, prepare the intended invocation **before** the final
card: run `campaign start --prepare-intake --intake <record.json>` with the
actual launch options. Resolve any reported mismatch. Include the returned
`task_brief.campaign_launch` settings in the read-back. Preparation starts no
measurements. A planning-only brief can be reviewed without a launch.

When `brief_review` becomes `awaiting_confirmation`, read back the **complete
task brief** in the user's language. Include the performance and accuracy
inequalities, both benchmark inputs, baseline, model/device, timing and
comparison, commands, change scope, failure policy and budget from
`task_brief.conditions`. Then send a **separate native card** asking the user
to approve this exact brief or request changes. Wait for a fresh explicit reply.
Record it with `task intake answer` using the returned `q:task_brief:...` ID and
`approve` or `revise`. For revisions, apply the corrections and present the
entire updated brief on a fresh card. This final review also applies to a fully
specified initial prompt. Until approval, allow only read-only preparation.
Pass the approved record to `campaign start --intake <record.json>` and use its
criteria in the frozen protocol and final evaluation.

## Optimize an ordinary user project

Default to the current Agent conversation. Read `campaign start --help` through
the selected runtime. Before search, prepare explicit task instructions, workload,
quality and measurement scripts, metric/unit/direction, gates, declared source
files/directories and budget. Reuse project checks where suitable. Harness
freezes those supplied conditions and reads their results; it does not infer
quality criteria from a request such as "increase throughput without quality loss".
Ordinary optimization does not require Benchmark; Benchmark supplies packaged
tasks and their task-specific rules for the task-library entry.
If consequential conditions are missing, resolve them with the user before search.

Use `campaign start` with an output directory outside the editable project.
Declare every execution input with repeatable `--include`; freeze scripts and
inputs through `--protocol`. Checks must use the retained `{candidate}`,
`{baseline}`, `{protocol}` and output `{result}` paths as appropriate. Confirm
they execute the submitted code, not an unrelated installed package or service.
For AB/BA, pass the approved dataset version and split as `--quality-benchmark`.
For a scored result, the quality script self-reports the corpus it evaluated in
the top-level `dataset` field. Harness checks the reported label against the
approved identity. Include the score's `unit` on numeric quality receipts for
both AB/BA and service reuse. Show the approved score scale and, for a service
baseline tolerance on percent scores, the allowed difference in percentage points.
This command uses the same Harness controller as the packaged task path below.

Record the measured bottleneck with `campaign diagnose`. Before editing each
candidate, inspect `candidate_find` in the diagnosis or preceding round
response when knowledge is enabled. P1 has already searched the local corpus
with the diagnosed bottleneck. Choose a relevant hit and execute its
`read_args` for the pinned body and receipt. If the first results leave a
question open, save `candidate_search` as JSON, add your selections and a
targeted follow-up to `queries`, then run
`inferrsi knowledge round REQUEST.json --session DIR`. Use the latest observation
to frame the follow-up. The first query reuses its receipt. A read-only
`status` returns the request if the handoff was interrupted.
Edit the working candidate and submit the hypothesis with `campaign round`.
Read the feedback and keep failed attempts. Use a pinned `read --resource` for a particular attachment.
If a read returns `next_read_args`, run those arguments to continue the same
resource, revision and search. Read all needed pages before treating a file as
fully received; each receipt records only its returned bytes.
When a passage you read changes the candidate or check you choose, explain
that choice in the existing `--hypothesis` and append
`[use REF | EXACT SOURCE EXCERPT]`. Use the read result's material `ref`
and a verbatim passage on one line. Leave the reason without a citation
when reading did not affect it.
For a Codex rollout, record the line boundary in its own tool call before
retrieval. Run each Find and each emitted `read_args` as a simple command in
its own tool call. Keep the full output visible. At round close, import both
receipts and the round response as described under search attribution below.
If a submitted AB/BA round finished asynchronously and its response was clipped,
run `campaign status --session <dir> --round-receipt <round>` after completion
and include its short return in the same import window. A benchmark uses
`benchmarks session status` with the same options.
Choose additional queries and profiling based on the outstanding question.
Use `up_to` for a declared round limit or `exact` for fixed rounds. End an up-to search with `campaign final --reason <why>`; it retests the
retained best candidate, not unsubmitted working edits. Reserve final time.
Report the result scope, gaps and summary; `dashboard` reads the same campaign.
Actual usage exports are optional; unknown tokens are never zero.

Do not write legacy `campaign record/decide` into a managed campaign. Use
`campaign recover` only to collect an existing interrupted execution without
relaunch. A process completing is not evidence of acceptance.

## Complete an optimization task benchmark

Benchmark requests default to a fresh conversation on the current host, unless
the user requests the current conversation. The initiator first resolves the
task with `benchmarks list/show` and writes a self-contained prompt specifying
the task/runtime revision, entry skill and launcher, knowledge condition,
round/time budgets, sampling, prepared environment and expected result paths.
Do not include parent conversation history, prior solutions or optimization hints.
Use `agents prepare --prompt-file ...` to retain that request; do not call
`benchmarks session start` in the initiating conversation. Use `agents dispatch`;
only `may_create: true` permits one host new-session call. Discover
the current host's native creation tool (for example Codex `create_thread`),
select the requested workspace, and send the exact returned prompt in a fresh
conversation. Do not fork history, silently change host/model, or replace an
uncertain creation with another session. Bind the confirmed native session ID
and the exported creation receipt with `agents bind`. Observe through the host's
native wait/read tools, then use `agents record` to retain actual observations
and deliverables. Missing usage stays unknown. Native deadlines are recorded,
not automatically enforced; monitor the host and use its supported cancellation.
The execution Agent owns start, all rounds, independent final and its report.
The initiator collects its summary, selected code, final evidence and available
usage, and reports those results. Host completion alone is not task acceptance.
If native creation is unavailable, report unsupported. DSH native launch is not
connected in this phase. An Agent receiving a delegated task executes the
following full lifecycle itself and never delegates the task again.

In the execution conversation, use `benchmarks session --help` through
the selected runtime. The first iterative task is `qwen21-denoise-npu`.
Start a new session with the user's round/time budget, condition label,
evaluation prefix and sampling arguments. Read its returned frozen TASK.md and
record the measured bottleneck with `session diagnose`. Before each candidate
edit, use the returned `candidate_find` and continue `candidate_search`
as described for project campaigns when knowledge is permitted. When the
benchmark supplies a required delivery, run its frozen Find request and read
the named card before submitting the first round. Submit each changed
candidate and hypothesis with `session round`, then inspect the independent
feedback before the next change. Use the same conditional `[use REF | EXACT SOURCE EXCERPT]`
in the hypothesis and close the Codex search archive as in `campaign round`.
Keep failed rounds. Complete the frozen budget
and use `session final` for independent retesting. Report `summary.json` and its
per-round curve data. Import actual usage exports when available and preserve
unknown values. Use `session recover` to collect an interrupted existing attempt.
The current host Agent drives these operations. `benchmarks run` evaluates one
candidate within this workflow.

## Research and diagnose

Use the CLI's help for exact flags. Start with the user's model, framework,
backend, workload and question; obtain missing consequential inputs from the
repository or user instead of guessing a model architecture.

After loading the primary skill, use `find "<problem or symptom>"` to rank skills, imported records and casebook
entries. Add `--kinds case` when you specifically need a past observation.
Open a promising hit using its displayed `open` command or the JSON
`open_argv` argument list.

On a base install, an indexed Skill in the installed library opens its original
text through its package record. A Skill from a custom library may require
PyYAML. If a hit reports `cannot open`, check the reason before choosing
another hit.

`read` returns the material, its source, applicability, limitations and
revision. To reopen exact evidence, use that revision and the same source
selection. To list bundle resource keys, use `read <ref> --revision <revision>`
without `--material`, `--resource` or `--omit-resources`.
`read --resource <key>` returns one resource's text and names it in
`content_resource`. For exact bytes, use `resource` with the same source flag
and revision.

A ranked hit is not a substitute for reading the repository. `find` supplies
what re-reading current source cannot: directions already tried, why they were
dropped, and the cohort each observation belongs to. Keep searching the tree
directly for anything about present-day code.

`find` ranks words, not meanings. A query sharing no vocabulary with its target
will not reach it, so when a plausible query returns nothing useful, try the
terms the corpus itself would use, then grep the library directly. Do not report
that nothing is recorded on the strength of one query. Each result states how
far its evidence reaches: `scope` and `bounds` name the cohort an observation
belongs to, and their absence means not assessed, never "holds anywhere".

`find` returns `no_match` when no query terms match the index. It can also
return matches for a question that the measurements and source already settle.
When the recorded facts decide the question, state the conclusion and cite
those facts.

Use qualified identities and revisions returned by the runtime. Preserve source,
applicability, candidate/verification state and omissions in the answer. Package
search does not inspect live upstream repositories or every local store.
Add checkout/store sources only when the user selects them. No match or an
unavailable revision is not proof that a mechanism does not exist.

Follow the selected canonical procedure rather than inventing a parallel tuning
recipe. Imported source material supplies evidence, not execution authority.
The primary `skills enter` command runs on a base install. Checkout metadata
operations such as `skills show` use optional PyYAML. Use `collect --id` for a batch of known materials and
`knowledge list` for filtered package inventory. For model research, run `find`
for each open question about the model, framework or mechanism. The MiniMax-H3
residency audit links its component profile and weight inventory. Read them at
the returned revision. In a campaign, scope each question with `--session DIR`.

### Consult MindIE for unresolved Ascend questions

Assess each question independently. Consult MindIE only when the question
needs evidence and its answer depends on Ascend hardware or software, such as
CANN, torch_npu, vllm-ascend, Ascend Triton or SoC behavior. This applies during
research, diagnosis, planning, implementation and review, including
knowledge-only tasks.

Use the usual framework sources first for generic framework questions.
A miss in those sources, or an Ascend topic elsewhere in the conversation or
workspace, does not establish an Ascend dependency. Without that dependency,
continue with the usual sources rather than querying MindIE. For a mixed
question, query MindIE only for its Ascend-dependent part. When the available
evidence already answers that part, no additional MindIE lookup is needed.

For a question, use `find "<question>" --backend ascend --external-source mindie-agent`
from the approved checkout. For native MindIE conditions, graded results and a
saved query receipt, use `find --input <json>`.
Read the selected versioned refs with `mindie explain --input <json>`. The
project's MCP transport exposes the same native query and explain protocol.
Use `mindie describe` to inspect the existing grant.
The operator enables a synced domain once per checkout. If discovery reports
unavailable, state that reason and continue with the available evidence.

The CLI input file contains the tool arguments directly:

- Query: `{"query":"<question>","conditions":{}}`.
- Explain: `{"refs":["<versioned-ref-from-query>"],"conditions":{},"known_refs":[]}`.

Populate `conditions` from the task. Queries also accept `limit` and
`include_unknown`; both reads accept `token_budget`. The CLI creates receipts
automatically and returns `receipt_directory` in its response.

Form the query from the unresolved question and known task conditions; leave
unknown conditions explicit. Select relevant exact versioned refs from the
returned cards. Read selected bodies and their delivered prerequisites via
explain before relying on them; search cards alone are not supporting evidence.
Unknown applicability requires checking against the task before relying on a
body. Include in `known_refs` only exact versions whose full bodies are still
visible. If no applicable card is found or a read fails, state the outcome and
continue with the evidence available to you.

Explain which conclusion or decision each delivered versioned ref supports,
preserving its applicability limits. The CLI stores query and explain receipts
under `~/.config/inferrsi/mindie-projects/reads/<project-hash>/`; do not copy
them into the source checkout. A knowledge-only answer does not require creating
a candidate or campaign. A knowledge read authorizes only the approved local
knowledge operation.

### Record research and campaign evidence

When the requested deliverable includes an optimization dashboard or a
replayable campaign trace, record the research as the work happens. Preserve
the selected queries, exact revisions, source order, omissions and the complete
assembled knowledge context actually prepared for the agent. Do not substitute
a list of source names or a later reconstruction for the original context.
Inspect and remove credentials and private material before recording any
snapshot; mark it as redacted or partial and explain the gap when the recorded
copy differs or is incomplete. A prepared context alone does not prove that a
model consumed it.

Record the declared search space separately from attempts, and keep each
observation, attempt and decision in order with its reason and result. Include
failed, skipped and rolled-back work. At review time, record successes,
failures and remaining limitations, linking them to the run artifacts where
available. If the context or reasoning was not captured, state that it is
missing instead of inferring it from a verdict. The optional campaign trace
format and association workflow are documented in `docs/dashboard.md`.

For managed rounds, Find records the returned hits. Following a hit's scoped
`read` command records the material delivered. In an AB/BA project or a
benchmark, pass a used read's `reference.path` to `round --knowledge-ref`.
A service-reuse attempt retains prepared contexts automatically. Record what
influenced the change in the hypothesis. For a manual campaign, use
`find "<question>" --session <dir>` and the returned read
command. After each manual round, use `campaign log` to record the
hypothesis, why this optimization was chosen, which
knowledge it relied on, the search options tried, pruned or left untried and
why, the decision and its reason. At the end, write success and failure
summaries that cite `candidate:<id>` evidence and name the failing stage.
Resolve every **Narrative vs evidence** warning the dashboard shows, or explain it.

When recording search attribution, keep line counting, Find and each read in
separate tool calls. Pipes, redirections and compound shell commands can leave
the archive partial. After the round response, run `campaign import-search`
with the inclusive line range and corpus root. For standard capture receipts
with a `sha256`, pass
`--context-id <find-id> --context-id <read-id>`, repeating the flag for each
additional receipt. A returned `reference.path` of `knowledge/<id>.json`
supplies the ID between the slash and the suffix.
If the rollout is available only after interruption,
the host can import the same range later. Keep private raw traces outside the
campaign. The round-import section of `docs/dashboard.md` describes how to
distinguish observed reads, explicit use and missing capture.
Supply the reviewed corpus version with `--archive-review`. Managed round
citations resolve from the submitted hypothesis and tool returns. In a manual
campaign, state the cited reason while deciding and retain it in the log.
Check the saved passages and decision excerpts before sharing.

For a bilingual dashboard, prepare and review a translation overlay for the
recorded narrative, including the knowledge context, search space, decisions,
benchmark and quality descriptions. Supply it to `dashboard --translations` as
documented in `docs/dashboard.md`. Keep the recorded context, commands and
identifiers intact; a translation is not the original evidence. Explicitly leave
unsupported or unavailable translations in their original language.

## Prepare and run a comparison

Before editing a candidate, record whether to consult MindIE and the reason
under the research guidance above. Use the same agent for the read and the
edit. Record which delivered versioned ref informed a concrete implementation
choice, with the resulting file or change. For campaign evidence, pass each
receipt's `input.json`, `result.json` and exit code to `campaign import-mindie`.
Review the delivered bodies and the per-candidate trace, then use
`campaign assemble-trace` and
`campaign record` to associate the trace with the round, frozen candidate and
independent run. InferRSI owns execution and evaluation.

Retain a separate candidate source snapshot before evaluating it. Commands must
run that snapshot, even after the generation workspace changes. Inspect actual
run source hashes and quality/timing evidence; a candidate ID or agent narrative
does not prove which bytes ran. The [MindIE setup guide](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/guides/plugins/codex-plugin.md#mindie-knowledge)
explains how to associate a candidate with its trace.

Consult `plan --help` and `run --help` to build the current runtime's invocation.
Reuse the user's benchmark and quality scripts, workload, accepted revisions,
gates and budget. If they are missing, help prepare them and name the remaining
inputs. Do not turn CLI defaults into accepted campaign criteria.

Use supplied acceptance criteria unchanged, including a referenced accepted
plan. When none are supplied, read
`inferrsi.common.skills.performance_ceiling_analysis` with `--material` through
the selected CLI path, then load its `references/acceptance-criteria.md` resource
and follow that procedure to formulate targets. Preserve partial requirements
and derive only missing fields. Record user versus derived criteria, calibration,
uncertainty and existing freeze authority; missing evidence stays unresolved.
The CLI does not invoke the skill automatically or infer gates from omitted flags.

Use `plan` for a command/specification preview. It persists no frozen campaign
and grants no execution authority. Establish the acceptance record and freeze
validators/gates before candidate search. Preserve the declared SIAS plane.
Execute `run` only within the user's existing scope and resource authority;
do not add a second approval step when that authority is already sufficient.

Benchmark commands are parsed as argv, without a shell. Put environment setup,
pipelines and service lifecycle in reviewed target-owned scripts. Use forward
slashes in Windows paths inside command strings. The runner executes on the
prepared target machine. For local execution, use the host's terminal/process
tools. In DSH remote mode, use `inferrsi_remote` with the form's tested
`remote.connectionId`: `cli` invokes the bundled runtime in the selected remote
repository, and `run_script` invokes the user-designated benchmark or quality
script. Supply `maxMinutes` from the task's remaining time budget for
`run_script` and long CLI operations; it does not grant additional execution
authority. Other hosts without this tool require their existing authorized
target-execution mechanism.

Run in the foreground through the selected host tool, retain the returned
process/session identity, and inspect recorded status during long work. Cancel
through that tool so the existing executor can clean up. After a timeout,
interruption or reconnect, inspect evidence before proposing another invocation;
never silently retry a measurement.

## Open the optimization dashboard

When the user asks to monitor optimization progress, rounds or history, use the
bundled dashboard. Select the campaign directory already associated with the
task to show its recorded rounds and candidates. For a single-run view, select
that existing run directory. Resolve the input from the user's task and known
artifacts; ask for the directory when its identity is ambiguous.

In DSH remote mode, call `inferrsi_remote` with operation `dashboard`, the tested
connection ID and `path` set to the campaign/run directory. Use its returned
Host loopback URL. For local execution, start the command below through the
host's terminal/process tools.

```text
python -X utf8 "<launcher>" dashboard --input "<campaign-or-run-directory>" --live --port 0
```

Retain the connection or process/session identity for the chosen path. In
remote mode, open or link the tool's returned `url`; locally, wait for startup
JSON and use its exact `dashboard` URL. The dashboard refreshes recorded progress
about every three seconds. If an owned server for the same input is already
running, reuse its URL. Stop a local server through the retained process. In
DSH remote mode, `close` releases the connection and its dashboard together,
including other active operations on that connection. Keep it open while an
authorized measurement is running, and close it when the task is finished or
the user requests that full connection close.

The server listens on the machine where the launcher runs. In DSH remote mode,
use `inferrsi_remote` with operation `dashboard`, the tested connection ID and
the campaign/run path; it returns the Host loopback URL through its SSH tunnel.
If the browser is on another machine, forward that Host loopback port to the
browser machine. Other remote hosts require their existing authorized
port-forwarding setup. The dashboard's headers require a separate browser page. To export an
offline snapshot, omit `--live --port 0` and supply `--output "<output.html>"`.

Managed optimization operations preserve round/candidate associations themselves.
Use `campaign record` only for legacy manual campaigns, and keep the optimization
log for the declared reasoning. Missing history or context needs its source
record; an open dashboard alone creates no experiment or campaign evidence.

## Inspect and explain

Use `status --run-id <id> --output-dir <root>` for recorded progress and
`report --run-id <id> --output-dir <root>` to regenerate HTML. The latter writes
into the existing run directory. Link the report and the evidence supporting
the conclusion. Distinguish process state, experiment verdict and goal acceptance.

Retain PASS / FAIL / INCONCLUSIVE exactly as recorded. Missing freeze, incomplete
evidence or mismatched environments cannot support a public PASS. CPU/synthetic
checks do not establish model quality or service gains; those require their
campaign's validation levels. Do not automatically promote knowledge candidates,
publish artifacts or resume an interrupted run.
