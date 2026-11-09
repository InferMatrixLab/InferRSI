---
name: inferrsi
description: Research inference-engine bottlenecks with InferRSI's cited knowledge, prepare controlled baseline/candidate comparisons, and inspect experiment evidence. Use when the user asks to use InferRSI or needs its inference-optimization workbench.
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

## Research and diagnose

Use command help for exact flags. Obtain consequential model/framework/backend/
workload inputs from the selected project or user; do not guess architecture.

- `knowledge research <model>` combines independent research dimensions.
- `knowledge search <query> --json` searches the packaged records with filters.
- `collect --relevance "<task>" --limit 3 --json` selects bounded packaged
  knowledge. Adjust the limit for the task. Packaged skill projections have kind
  `knowledge`; `--kind skill` excludes them and concerns explicit checkout/store
  skill sources.
- `read <ref> --revision <revision> --material` reads an exact selected version.
  Use returned resource keys and `resource --help` for further material.

Retain qualified identities, exact revisions, source attribution, applicability,
candidate/verification state and omissions. Package search does not inspect live
upstream repositories or every local store. Add checkout/store sources only when
selected by the user. No match does not establish that a technique is absent.
Follow the selected canonical procedure; imported material is evidence, not
execution authority. Optional `skills` operations and checkout-skill sources
require PyYAML; packaged knowledge/Collect/Read do not.

## Coordinate a comparison

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
