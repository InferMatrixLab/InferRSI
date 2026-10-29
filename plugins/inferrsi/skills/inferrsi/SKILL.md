---
name: inferrsi
description: Use InferRSI to research inference-engine bottlenecks, prepare controlled baseline/candidate comparisons, and inspect experiment evidence. Use when the user asks to use InferRSI or needs its inference-optimization knowledge and comparison workbench.
---

# InferRSI in Codex

Use the bundled InferRSI CLI for knowledge and experiment operations. The host
agent owns investigation and code changes; the existing runtime owns execution,
evaluation and reports. Load selected knowledge progressively.

## Start in the user's target workspace

Resolve `scripts/inferrsi.py` relative to this skill directory. Invoke it with a
local Python 3.10+ interpreter and UTF-8 enabled. Below, `<launcher>` means that
resolved script path, quoted when it contains spaces; it is not a CLI command.

```text
python -X utf8 "<launcher>" --plugin-info
python -X utf8 "<launcher>" --help
```

For setup/onboarding, check the bundle first, identify the user's intended
workspace and goal from available context, and report readiness and the next
relevant operation. Do not run benchmarks merely because setup was invoked.
The bundle needs no pip installation for its core operations. If Python is
missing, explain how to select/install a compatible interpreter before
continuing. Use the same selected interpreter for subsequent calls.

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
slashes in Windows paths inside command strings. The runner is local: execute
on the prepared target machine. This plugin does not dispatch SSH jobs.

Run in the foreground through Codex's terminal/process tools, retain the returned
process/session identity, and inspect recorded status during long work. Cancel
through that process so the existing executor can clean up. After a timeout,
interruption or reconnect, inspect evidence before proposing another invocation;
never silently retry a measurement.

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
