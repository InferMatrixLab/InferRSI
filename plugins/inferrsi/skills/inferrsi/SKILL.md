---
name: inferrsi
description: Use InferRSI to research inference-engine bottlenecks, prepare controlled baseline/candidate comparisons, and inspect experiment evidence. Use when the user asks to use InferRSI or needs its inference-optimization knowledge and comparison workbench.
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

For a campaign, retrieve knowledge through `campaign capture-context` (one
capture per retrieval) instead of a bare `collect`, so the exact context is kept.
After each round, update the campaign optimization log and record it with
`campaign log`: the hypothesis, why this optimization was chosen, which
knowledge it relied on, the search options tried, pruned or left untried and
why, the decision and its reason. At the end, write success and failure
summaries that cite `candidate:<id>` evidence and name the failing stage.
Resolve every **Narrative vs evidence** warning the dashboard shows, or explain it.

For a bilingual dashboard, prepare and review a translation overlay for the
recorded narrative, including the knowledge context, search space, decisions,
benchmark and quality descriptions. Supply it to `dashboard --translations` as
documented in `docs/dashboard.md`. Keep the recorded context, commands and
identifiers intact; a translation is not the original evidence. Explicitly leave
unsupported or unavailable translations in their original language.

## Decide whether to consult MindIE before editing the candidate

After inspecting the baseline, target device, shapes, dtype and evaluation
requirements, identify any open implementation decision that Ascend knowledge
could resolve. Record whether to consult MindIE and the reason before writing
the candidate. Continue with the available evidence when it already answers
the question.

When a gap remains, use the project's `knowledge_query` and
`knowledge_explain` MCP tools if present. The bundled local launcher also
discovers the same project grant via `mindie describe`. Run it in the target
checkout, then use `mindie query --input <json>` and
`mindie explain --input <json>` there. The operator enables a synced domain once
per checkout. If discovery reports unavailable, record that reason and continue
the optimization with the evidence available to you.

Form the query from the open decision and actual task conditions. Select relevant
exact versioned refs from the returned cards. Unknown applicability requires
checking against the task before relying on a body. If no applicable card is
found, record the search outcome and continue. Read selected bodies and their
delivered prerequisites via explain. Include in `known_refs` only exact
versions whose full bodies are still visible. Record the outcome of a failed
read and continue with evidence already available.

Use the same agent for the read and the edit. Record which delivered versioned
ref informed a concrete implementation choice, with the resulting file or
change. Keep the query and explain receipt directories outside the source
checkout. For campaign evidence, pass each receipt's `input.json`,
`result.json` and exit code to `campaign import-mindie`. Review the delivered
bodies and the per-candidate trace, then use `campaign assemble-trace` and
`campaign record` to associate the trace with the round, frozen candidate and
independent run. InferRSI owns execution and evaluation. A knowledge read
authorizes only the approved local knowledge operation.

Retain a separate candidate source snapshot before evaluating it. Commands must
run that snapshot, even after the generation workspace changes. Inspect actual
run source hashes and quality/timing evidence; a candidate ID or agent narrative
does not prove which bytes ran. See `docs/codex-plugin.md` for MindIE setup and
candidate trace association.

## Prepare and run a comparison

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

Preserve explicit campaign round/candidate associations through `campaign record`
and the recorded optimization log. Missing history or context needs its source
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
