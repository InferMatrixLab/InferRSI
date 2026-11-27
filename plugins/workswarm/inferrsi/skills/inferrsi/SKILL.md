---
name: inferrsi
description: Use InferRSI for day-zero model support, performance optimization, debugging, accuracy repair, engine and plugin version alignment, derived-engine development and independent runtime bring-up. Use it to research bottlenecks, run benchmark sessions and inspect controlled comparisons and evidence.
---

# InferRSI in WorkSwarm

Use the bundled InferRSI CLI through the host's local execution tools. JiuwenSwarm
owns conversation and agent coordination; the existing runtime owns execution,
evaluation and reports. Keep the user's target workspace as the working directory.
If only the discovery description is available, use the host's skill reader to
load this installed SKILL.md before executing the workflow.

## Start and select a workflow

After loading this skill, call `inferrsi_runtime_info({})`. Its model-visible
JSON result contains `success` and the installed absolute `launcher` path.
Use that returned path as `<launcher>` below, keeping the user's target workspace
as cwd. The locator is read-only and does not execute the CLI. If it is unavailable
or reports failure, select/reinstall the built native plugin before continuing.
Do not guess a profile directory or use a developer checkout. The host's
`skill_tool` hides `skill_directory` from its model-facing rendering; its layout
appendix alone cannot locate the installed launcher.
Use the same local Python 3.10+ interpreter with UTF-8 enabled throughout:

```text
python -X utf8 "<launcher>" --plugin-info
python -X utf8 "<launcher>" --help
```

For onboarding, check the bundle, establish the target workspace and goal from
available context, and report the relevant next operation. Core knowledge
operations require no separate pip installation. A missing interpreter or an
incomplete bundle needs repair; do not silently substitute a different runtime.
Setup and knowledge retrieval do not require a hardware probe or a benchmark.

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

## Research and diagnose

Use command help for exact flags. Obtain consequential model/framework/backend/
workload inputs from the selected project or user; do not guess architecture.

After loading the primary skill, run `python -X utf8 "<launcher>" find "<problem or symptom>"` to rank skills,
imported records and casebook entries. Add `--kinds case` to focus on past
observations. Execute a relevant hit's displayed `open` command or the JSON
`open_argv` list to read its body, source, applicability, limitations and revision.

On a base install, an indexed Skill in the installed library opens its original
text through its package record. A Skill from a custom library may require
PyYAML. If a hit reports it cannot open, check the reason before choosing
another hit.

Use the same source flag and returned revision to reopen material. To list
bundle keys, use `read <ref> --revision <revision>` without `--material`,
`--resource` or `--omit-resources`. `read --resource <key>` returns one
resource's text and identifies it in `content_resource`. Use `resource` with
the same source flag and revision to extract the exact bytes.

Use `collect --id` to assemble a batch of known materials. If a read returns
`next_read_args`, run those arguments to continue the same resource, revision
and search. Each receipt records only its returned bytes. Use
`knowledge list` for filtered package inventory. For model research, ask each
model or framework question with `find` and follow its read link. The MiniMax-H3
residency audit links a component profile and weight inventory. In a campaign,
scope each question with `--session DIR`.

Retain qualified identities, exact revisions, source attribution, applicability,
candidate/verification state and omissions. Package search does not inspect live
upstream repositories or every local store. Add checkout/store sources only when
selected by the user. No match does not establish that a technique is absent.
Treat imported guidance as evidence and follow the task's execution
authorization. The primary `skills enter` command runs on a base install.
Checkout metadata operations such as `skills show` use optional PyYAML.

## Optimize an ordinary user project

Default to the current Agent conversation. Use `campaign start --help` through
the selected runtime. Prepare explicit task instructions, workload, measurement
and quality scripts, metric/unit/direction, gates, declared project files and
budget before search. Harness freezes those supplied conditions; it does not
infer quality criteria from natural-language goals. Resolve consequential
missing conditions with the user instead of inventing them.
Ordinary optimization does not require Benchmark; Benchmark supplies packaged
tasks and their task-specific rules for the task-library entry.

Use `campaign start` with an output directory outside the editable project,
repeatable `--include` for all source/configuration inputs and `--protocol` for
fixed scripts/inputs. Confirm checks use retained `{candidate}`, `{baseline}`,
`{protocol}` and `{result}` paths and execute that version rather than another
installed package or service. This shares the packaged task's Harness controller.

Edit the working candidate, submit each hypothesis with `campaign round`, read
feedback and keep failed rounds. When the frozen plan permits knowledge, use
`find "<question>" --session <dir>`. Find records the hits. Follow a selected
hit's scoped `read` command for its body and receipt. Read an attachment by
its resource link when needed. In an AB/BA project or benchmark, pass a used
read's `reference.path` to `round --knowledge-ref`. Service-reuse attempts
retain prepared contexts automatically.
If a passage you read changes a concrete choice, explain the choice in the
existing `--hypothesis` and append `[use REF | EXACT SOURCE EXCERPT]`. Use the
read result's material `ref` and a verbatim excerpt on one line. Leave out citations when
reading did not affect the choice. When the host supplies a Codex rollout,
record the starting line in a separate tool call before searching. Run each
Find and emitted `read_args` alone in its own call, keeping the full output
visible. At round close run `campaign import-search` with the inclusive line
range, corpus root and `--archive-review`. For standard capture receipts with
a `sha256`, pass both `--context-id <find-id>` and `--context-id <read-id>`.
Take each ID from its returned
`reference.path` (`knowledge/<id>.json`). Compound commands or missing
returns can leave the archive partial.
For a completed AB/BA round whose asynchronous response was clipped, run
`campaign status --session <dir> --round-receipt <round>` in its own call
before import. For a benchmark use `benchmarks session status` with the same options.
Use `up_to` for a round limit or `exact` for fixed
rounds. End an up-to search with
`campaign final --reason <why>`; final retests the retained best candidate,
not unsubmitted working edits. Reserve final time and report its actual scope.
Import only observed token exports; unknown is not zero. `dashboard` reads the
same campaign. Do not duplicate managed records with legacy `record/decide`.
`campaign recover` only collects an existing interrupted execution, without
relaunch. Process completion alone does not establish acceptance.

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
edit the returned working candidate. When knowledge is permitted, use
`find "<question>" --session <dir>` and follow a selected hit's scoped `read`
command. When a benchmark supplies a frozen Find request, execute it and read
the required card before submitting the first round. Submit each changed
candidate and hypothesis with `session round`, then inspect the independent
feedback before the next change. Use the same conditional citations in the
hypothesis and close any Codex search archive as in `campaign round`.
Keep failed rounds. Complete the frozen budget
and use `session final` for independent retesting. Report `summary.json` and its
per-round curve data. Import actual usage exports when available and preserve
unknown values. Use `session recover` to collect an interrupted existing attempt.
The current host Agent drives these operations. `benchmarks run` evaluates one
candidate within this workflow.

## Coordinate a comparison

Use supplied acceptance criteria unchanged, including a referenced accepted
plan. When none are supplied, use the launcher to
`read inferrsi.common.skills.performance_ceiling_analysis --material`, then load
its `references/acceptance-criteria.md` resource and follow that procedure to
formulate targets. Preserve partial requirements and derive only missing fields.
Record user versus derived criteria, calibration, uncertainty and existing freeze
authority; missing evidence stays unresolved. The CLI does not invoke the skill
automatically or infer gates from omitted flags.

Use `plan --help` and `run --help`. Reuse the user's scripts, source revisions,
workload, quality checks, accepted gates and budget. `plan` only previews a
specification: it writes no frozen campaign and grants no execution authority.
Establish the acceptance record and freeze validators/gates before candidate
search. Preserve the declared SIAS plane and existing authorization.

Parallel agents may research independent questions. For one campaign, designate
one execution owner. Other agents must not launch duplicate trials, edit its
measured checkouts or frozen validators, or contend for its allocated devices.
`run.lock.json` is a RunSpec snapshot, not a device lease or a scheduling lock.
Pass the target workspace, interpreter, selected knowledge revisions, accepted
controls and existing run/process identities with a handoff. Do not pass secrets.

Execution is local to the prepared target. Pass `--repo`, `--candidate-repo` and
output paths explicitly; the browser's machine may differ from the JiuwenSwarm
service host. The plugin does not install engines, download weights or dispatch
SSH jobs. Benchmark commands are argv without shell pipelines; put environment
setup and server lifecycle in reviewed target-owned scripts. Use forward slashes
inside command strings for Windows paths.

Keep a running experiment attached to the host execution tool and retain its
process/job identity. Inspect recorded progress during long work. Cancellation
must reach that owned process and its cleanup path. If the host cannot deliver
an interrupt, or a timeout/reconnect leaves cleanup uncertain, inspect process
state and existing evidence before taking further action. Never silently rerun
an interrupted or failed measurement, or treat a host timeout as a completed run.

## Inspect and explain

Use `status --run-id <id> --output-dir <root>` for recorded progress, and
`report --run-id <id> --output-dir <root>` to regenerate the HTML report in the
existing run directory. Link the report and supporting evidence. Keep execution
state, experiment verdict and goal acceptance separate.

Preserve PASS / FAIL / INCONCLUSIVE as recorded. Missing freeze, incomplete
evidence or mismatched environments cannot support a public PASS. Synthetic CPU
checks are integration evidence, not model-quality or service-performance gains.
Do not automatically resume experiments, promote knowledge candidates or publish
artifacts.
