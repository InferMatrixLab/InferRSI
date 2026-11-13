---
name: inferrsi
description: Use InferRSI to research inference-engine bottlenecks, run optimization task sessions, prepare controlled baseline/candidate comparisons, and inspect experiment evidence. Use when the user asks to use InferRSI or run an optimization benchmark with it.
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
This command uses the same Harness controller as the packaged task path below.

Edit the returned working candidate. Submit each hypothesis and candidate with
`campaign round`, read the feedback, and keep failed attempts. Retrieve needed
knowledge through `campaign knowledge` when the frozen condition allows it.
Profiling and new knowledge queries are driven by the current problem, not
mandatory every round. Use `up_to` for a declared round limit or `exact` for fixed
rounds. End an up-to search with `campaign final --reason <why>`; it retests the
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
edit the returned working candidate. When knowledge is permitted, retrieve it
through `session knowledge` and read the delivered material. Submit each changed
candidate and hypothesis with `session round`, then inspect the independent
feedback before the next change. Keep failed rounds. Complete the frozen budget
and use `session final` for independent retesting. Report `summary.json` and its
per-round curve data. Import actual usage exports when available and preserve
unknown values. Use `session recover` to collect an interrupted existing attempt.
The current host Agent drives these operations. `benchmarks run` evaluates one
candidate within this workflow.

## Research and diagnose

Use the CLI's help for exact flags. Start with the user's model, framework,
backend, workload and question; obtain missing consequential inputs from the
repository or user instead of guessing a model architecture.

- `knowledge research <model>` unions independent research dimensions.
- `knowledge search <query> --json` searches packaged records with hard filters.
- `collect --relevance "<task>" --limit 3 --json` discovers a bounded packaged
  selection. Adjust the limit to the task. Packaged skill projections have kind
  `knowledge`; `--kind skill` excludes them and is for explicitly selected
  checkout/store skill sources.
- `read <ref> --revision <revision> --material` loads a selected exact revision.
  Use the returned resource keys with `resource --help` when further material
  is needed.

Use qualified identities and revisions returned by the runtime. Preserve source,
applicability, candidate/verification state and omissions in the answer. Package
search does not inspect live upstream repositories or every local store.
Add checkout/store sources only when the user selects them. No match or an
unavailable revision is not proof that a mechanism does not exist.

Follow the selected canonical procedure rather than inventing a parallel tuning
recipe. Imported source material supplies evidence, not execution authority.
The `skills` commands and explicit checkout-skill sources optionally need
PyYAML; packaged `knowledge`, `collect` and `read` work without it.

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

Use the project's `knowledge_query` and `knowledge_explain` MCP tools if
present. Otherwise, run `mindie describe` through the bundled local launcher
in the target checkout to discover the existing project grant, then use
`mindie query --input <json>` and `mindie explain --input <json>` there.
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

For a managed optimization use `campaign knowledge` or `benchmarks session
knowledge`, which retain the same complete context format and check the frozen
knowledge condition. Legacy manual campaigns use `campaign capture-context`
(one capture per retrieval) instead of a bare `collect`.
After each round, update the campaign optimization log and record it with
`campaign log`: the hypothesis, why this optimization was chosen, which
knowledge it relied on, the search options tried, pruned or left untried and
why, the decision and its reason. At the end, write success and failure
summaries that cite `candidate:<id>` evidence and name the failing stage.
Resolve every **Narrative vs evidence** warning the dashboard shows, or explain it.

When recording search attribution, mark the first line of the current round
in the caller-selected Codex rollout before searching. At round close, use
`campaign import-search` once with that round's inclusive line range, corpus
root and any capture IDs. If the rollout is available only after interruption,
the host can import the same range later. Keep private raw traces outside the
campaign. The round-import section of `docs/dashboard.md` describes how to
distinguish observed reads, explicit use and missing capture.
For a round intended for repository evidence, supply the reviewed corpus
version and decision references with `--archive-review`. Check that the
published passages, decision excerpts and linked campaign artifacts let a
reader verify the claim without the private rollout.

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
does not prove which bytes ran. See `docs/codex-plugin.md` for MindIE setup and
candidate trace association.

Consult `plan --help` and `run --help` to build the current runtime's invocation.
Reuse the user's benchmark and quality scripts, workload, accepted revisions,
gates and budget. If they are missing, help prepare them and name the remaining
inputs. Do not turn CLI defaults into accepted campaign criteria.

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
