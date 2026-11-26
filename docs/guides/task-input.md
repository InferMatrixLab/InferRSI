# YAML task input (schema v1)

Write an InferRSI task once, or ask an Agent to generate it. Then use the same YAML
file from the CLI or hand it to an Agent. Both entry points read it through one
shared contract, `inferrsi.apps.cli.task_input`, so the same file gives the same
normalized task fields either way.

`inferrsi task validate` and `inferrsi task preview` check a draft or complete file
without side effects. `inferrsi plan --task` and `inferrsi run --task` use a complete
file with the existing plan and run operations (see
[use with plan and run](#use-with-plan-and-run)).

| Resource | Location | Print from an installed CLI |
| --- | --- | --- |
| JSON Schema (draft 2020-12) | `src/inferrsi/apps/cli/task-input/v1/schema.json` in the wheel | `inferrsi task schema` |
| Agent-oriented template | `src/inferrsi/apps/cli/task-input/v1/template.yaml` in the wheel | `inferrsi task template` |
| Shared conformance fixtures | [`tests/fixtures/task-input/`](../../tests/fixtures/task-input/README.md) | — |

PyYAML is a core dependency, so an ordinary install without extras reads task files.
The `skills` extra remains as a compatibility alias.

## File rules

- `schema_version: 1` is required, as an integer. A string `'1'`, a boolean or
  another version is an error.
- The file has three sections: `optimization` (optimization target), `environment`
  (test environment) and `acceptance` (acceptance criteria). Any section may be
  omitted in a draft. A section that is present must be a mapping.
- `null` counts as missing. A valid draft may still be incomplete. Preview lists
  what a full plan or run still needs.
- Unknown keys, duplicate keys, YAML merge keys (`<<`), non-string keys and type or
  range errors are rejected with their field path, for example
  `environment.repetitions`.
- The file is one UTF-8 YAML document of at most 64 KiB. It is read with PyYAML's
  safe loader. A value the loader cannot build, such as the unquoted impossible date
  `2024-02-30`, is a document-level error.
- Do not put credentials in a task file. Supply them through the existing runtime
  channels.

## Fields

"Plan/run" marks the fields a full plan or run needs. "Default" is the built-in value
used when both the file and the flag omit an optional field.

| Field | Type | Flag | Plan/run | Default |
| --- | --- | --- | --- | --- |
| `optimization.repository` | path | `--repo` | yes | — |
| `optimization.candidate_repository` | path | `--candidate-repo` | — | — |
| `optimization.model` | string | `--model` | yes | — |
| `optimization.model_revision` | quoted string | `--model-revision` | — | — |
| `optimization.framework` | `vllm`, `vllm_omni`, `afd_plugin`, `vllm_rlt`, `strata`, `sglang`, `sglang_omni` | `--repo-type` | yes | — |
| `optimization.workload` | string | `--workload-id` | yes | — |
| `optimization.scenario` | string | `--scenario` | — | `external_benchmark` |
| `optimization.mode` | `config`, `code`, `semantic` | `--mode` | — | `config` |
| `optimization.objective` | string | — | yes | — |
| `optimization.plane` | `harness`, `model`, `infra` | — | yes | — |
| `environment.backend` | `cpu`, `cuda`, `rocm`, `ascend`, `mlx` | `--backend` | yes | — |
| `environment.device_ids` | list of quoted, unique IDs | `--device-ids` (comma-separated) | — | none |
| `environment.device_model` | string | `--device-model` | — | — |
| `environment.python` | prepared Python; a path or a command name | `--python` | — | — |
| `environment.baseline_command` | quoted argv string or list of strings | `--baseline-command` | yes | — |
| `environment.candidate_command` | quoted argv string or list of strings | `--candidate-command` | yes | — |
| `environment.quality_command` | quoted argv string or list of strings | `--validation-command` | when required by the operation or plan | — |
| `environment.repetitions` | positive integer | `--repetitions` | yes | — |
| `environment.max_minutes` | positive finite number, at most 10080 (seven days) | `--max-minutes` | yes | — |
| `environment.rounds` | positive integer (optimization search rounds) | — | — | — |
| `acceptance.reference` | HTTP(S) issue URL or local plan path; `run` needs a local [frozen gate record](#frozen-gate-record) | — | yes | — |
| `acceptance.baseline_revision` | quoted string | — | yes | — |
| `acceptance.metric_key` | flat or dotted JSON key | `--metric-key` (must match) | yes | — |
| `acceptance.direction` | `minimize`, `maximize` | `--direction` (must match) | yes | — |
| `acceptance.metric_unit` | string | `--metric-unit` (must match) | yes | — |
| `acceptance.min_improvement_pct` | nonnegative finite number | `--min-improvement-pct` (must match) | yes | — |
| `acceptance.comparison_scope` | string | `--comparison-scope` (must match) | — | `external_command` |
| `acceptance.required_trial_checks` | list of unique dotted keys | `--require-trial-check`, repeatable (must match) | — | none |
| `acceptance.constraints` | string | — | — | — |

Preview leaves an omitted `candidate_repository` or `python` null; `plan` and `run`
then use the baseline checkout and the interpreter running InferRSI.

Quote revisions and device IDs. YAML reads an unquoted `1234567` as a number, and
`[0, 1]` as numbers, and the contract rejects both. `environment.rounds` is the
optimization search budget. It is separate from benchmark repetitions and has no
`plan`/`run` flag.

The values above are the ones the existing CLI accepts. The acceptance threshold and
metric are agreed in the acceptance issue or plan; the contract carries them and does
not invent them.

## Merge order

`task preview`, `plan --task` and `run --task` accept the mapped flags from the table
as overrides. The effective value of each field is:

1. an explicit CLI flag, then
2. the YAML value, then
3. the built-in default, for optional fields only.

Only flags the caller actually supplies take part. An omitted flag never replaces a
YAML value. For example, the `plan` parser default `--backend cpu` does not replace
`backend: cuda` from the file.

argparse rejects a flag with the wrong type or choice, such as `--repetitions 3.5`
or `--backend gpu`, before the file is read (exit 2). Preview then checks each
override like a YAML value, for example `--repetitions 0`, and reports it with source
`cli`. An invalid YAML field stays an error even when a flag overrides it. Acceptance
fields come from the file. An acceptance flag must equal the field's effective value:
the YAML value, or the built-in default when the file omits an optional field. Any
other value is rejected as a conflict at the acceptance field path. That includes a
flag that tries to supply a required acceptance value the file lacks. Preview
reports each field's source as `yaml`, `cli`, `default`, `missing` or `invalid`.

## Paths and commands

- YAML paths resolve against the directory that contains the task file, wherever the
  caller runs: `optimization.repository`, `optimization.candidate_repository`, a local
  `acceptance.reference`, and `environment.python` when it contains a path
  separator. A bare `environment.python` such as `python3` is kept as written.
- Paths given as CLI flags resolve against the caller's working directory.
- Resolution is lexical (`os.path.normpath`). It does not check that a path exists,
  follow symlinks or expand `~`.
- An `acceptance.reference` that starts with `http://` or `https://` is kept
  verbatim when it names a host, any port is decimal digits for a value from 1 to
  65535 (leading zeroes allowed), and it has no whitespace or control characters. A
  URL such as `https://:443`, `https://example.com:notaport` or one with an overlong
  port is an error at `acceptance.reference`. Another
  `scheme://` value is an error. Any other value is a local plan path.
- Paths, `environment.python`, a local `acceptance.reference` and every argv item
  must not contain a NUL character. A YAML value or an explicit override with one is
  rejected at its field before normalization.
- Commands follow the existing argv contract. A string is split like a shell argv
  with `shlex`, and a list is taken as the argv. Paths inside commands are not
  rewritten; commands still run in the repository working directory under the
  existing `plan`/`run` contract.

## Read-only boundary

`task validate`, `task preview`, `task schema` and `task template` read at most the
task file and the packaged resources, and write only to stdout. They start no
subprocess, run no probe or task script, install nothing, and create no workspace,
plan, run or evidence file. A `complete` preview only reports that every needed input
is present. It does not authorize execution. Running an experiment still requires an
explicit `run` under the existing acceptance, frozen-gate and evidence rules
(see [operations](operations.md#validatepreview-a-task-file--task-validate-task-preview)).

## Use with plan and run

`plan` and `run` take a complete task file with `--task`:

```bash
inferrsi plan --task task.yaml                   # preview the RunSpec and the task
inferrsi plan --task task.yaml --repetitions 7   # explicit override
inferrsi run --task task.yaml                    # explicit execution
```

- **Merge order.** `--task` uses the [merge order](#merge-order) of `task preview`.
  `plan` and `run` keep their parser defaults, such as `--backend cpu` and
  `--repetitions 3`, for flag-only use. In task mode only the mapped flags you supply
  are overrides, and a supplied flag wins even when its value equals the parser
  default. An acceptance flag must equal the file's value. Flags with no task field,
  such as `--agent`, `--output-dir` and `--dry-run`, keep their existing meaning.
- **Field errors first.** `plan` and `run` need a valid, complete task. Errors and
  blockers print to stderr, one line per field, for example
  `error acceptance.metric_key (cli): ...` or
  `blocker environment.repetitions: missing; required for plan/run`. The command
  then exits with 2 before any environment probe, task command or file write.
  The RunSpec's local directory/path checks also run before environment probes,
  including the optional candidate checkout.
- **Defaults for omitted optional fields.** An omitted `environment.python` uses the
  interpreter running InferRSI. An omitted `optimization.candidate_repository` uses
  the baseline checkout. An omitted `environment.quality_command` leaves the run
  without quality evidence, which gives the existing `INCONCLUSIVE` outcome.
- **`plan` and `run --dry-run`.** They inspect the environment and print the RunSpec
  built from the task, as in flag-only use. Their output adds a `task` block, the
  same object that `task preview --json` prints for the same file and flags, and a
  `frozen_gate` block, the [frozen gate](#frozen-gate-record) result. They report a
  `mismatch` or `unverified` gate without failing. Without `--task` the output is
  unchanged.
- **`run`.** Execution checks that the task's content is consistent with the local
  record it names and with the baseline checkout. It does not authenticate where the
  record came from (see [frozen gate record](#frozen-gate-record)).
  The input, gate and inspection checks fail with exit 2 before any benchmark
  command starts or any run directory is written.
  - Before the environment probe, the task's acceptance fields must agree with the
    [frozen gate record](#frozen-gate-record) that `acceptance.reference` names.
    A `mismatch` or `unverified` gate prints each problem by field to stderr.
  - After inspection, the baseline checkout's `HEAD` must equal
    `acceptance.baseline_revision`. A hexadecimal prefix of at least 7 characters is
    also accepted.
  - The declared baseline is also carried in the existing `RunSpec.revision` field.
    The source identity observed during inspection binds `RunSpec.snapshot_id`,
    including tracked/untracked changes and submodules. Harness checks both pins
    against the initial execution snapshot and each fresh snapshot of the baseline
    source before a trial. A checkout or working tree changed after inspection
    cannot run from a mismatching snapshot. This later refusal retains a failed
    diagnostic run with `INCONCLUSIVE`; it does not discard already recorded facts.

  The run directory then holds `task.json`, the task preview, and `frozen_gate.json`,
  the gate result with the record's SHA-256, next to `args.json`. `args.json` records
  the effective values and the absolute `task_file`.

RunSpec carries the experiment fields, including the frozen baseline revision.
`optimization.objective`,
`optimization.plane`, `environment.rounds`, `acceptance.reference`,
and `acceptance.constraints` have no RunSpec field.
They are recorded in the `task` block and in `task.json`. Without `--task`,
`--baseline-command` and `--candidate-command` remain required, with the same
argparse error and exit 2.

### Frozen gate record

Freeze the agreed gate before candidate search as a local file, for example in the
campaign's `plan/` segment, and point `acceptance.reference` at it. The record is a
schema v1 document with `schema_version: 1` and an `acceptance` section. It is read
and validated like a task file, and other sections are allowed, so a frozen copy of
the reviewed task also works. Its own `acceptance.reference` may cite the acceptance
issue URL; that field is not compared.

```yaml
schema_version: 1
acceptance:
  reference: "<acceptance-issue-url>"
  baseline_revision: "<baseline_sha>"
  metric_key: metrics.latency_ms
  direction: minimize
  metric_unit: ms
  min_improvement_pct: 2.5
  required_trial_checks: [checks.warm]
  constraints: "<AGREED_CRITERIA>"
```

`frozen_gate` reports one of three statuses, with field-level `problems`:

- **`agrees`.** The record states `baseline_revision`, `metric_key`, `direction`,
  `metric_unit` and `min_improvement_pct`, and every acceptance field except
  `reference` equals the task's effective value. Omitted `comparison_scope` and
  `required_trial_checks` take their built-in defaults on both sides, and the order
  of `required_trial_checks` does not matter. `baseline_revision` must be the same
  text.
- **`mismatch`.** The record is readable and complete, and at least one field
  differs, for example `acceptance.min_improvement_pct: is 1.0 in the task but 2.5
  in the frozen gate record <path>`.
- **`unverified`.** The gate cannot be checked: the reference is an HTTP(S) URL
  (InferRSI does not fetch it), the file is missing or is the task file itself, it
  is not a valid schema v1 document (a Markdown plan, for example), it has no
  `acceptance` section, or it omits a required gate field.

`agrees` means content agreement only. The check compares the record the caller
points at with the task. It does not establish that the record is the accepted one,
and InferRSI takes no expected digest to compare it with. A task and record replaced
together with matching values still give `agrees`. Authenticating the record's
provenance, for example confirming that it is the frozen plan the acceptance issue
cites, is a caller/host precondition before `run --task`. `frozen_gate.json` keeps the
record's `sha256` so the acceptance issue can cite it and a reviewer can compare it
with the accepted record. A `run --task` that passes this check still follows the
existing acceptance, frozen-gate and evidence rules.

## CLI workflow

```bash
inferrsi task template > task.yaml        # fill in the known fields
inferrsi task validate task.yaml          # format and value errors by field
inferrsi task preview task.yaml --json    # effective values, sources, blockers
inferrsi task preview task.yaml --json --repetitions 7   # explicit override
```

`validate` and `preview` exit with 0 for a valid file, even an incomplete draft, and
with 1 for an invalid file or a rejected override. A malformed flag is an argparse
error (exit 2). Without `--json` they
print one line per error, value and blocker.

`preview --json` returns:

```json
{
  "schema_version": 1,
  "task_file": "<absolute path to task.yaml>",
  "valid": true,
  "complete": false,
  "task": {"optimization": {"...": "..."}, "environment": {}, "acceptance": {}},
  "sources": {"environment.backend": "yaml", "optimization.scenario": "default"},
  "blockers": [{"field": "acceptance.metric_key", "message": "missing; required for plan/run"}],
  "errors": [],
  "execution": "not started"
}
```

`task` lists every field, with `null` for a missing value. Each error has `field`,
`message` and `source` (`yaml` or `cli`). A document-level error, such as a YAML
syntax error, uses the field `$`. `validate --json` returns `schema_version`,
`task_file`, `valid` and `errors`.

## Agent workflow

An Agent uses the same installed CLI and the same machine-readable preview:

1. Read the template (`inferrsi task template`) and, when needed, the schema
   (`inferrsi task schema`).
2. Write the task file from what the user supplied. Leave unknown fields `null`.
   Do not invent acceptance thresholds, metrics or revisions. Take them from the
   acceptance issue or plan.
3. Run `inferrsi task preview <task.yaml> --json`. Fix each reported error at its
   field path.
4. Review the effective values, their sources and the remaining blockers with the
   user. Ask for the blocking fields instead of guessing them.
5. Use the reviewed task with the existing InferRSI operation the user authorizes,
   under the operation's own boundary in [operations](operations.md). For example,
   run `inferrsi plan --task <task.yaml>`, then `inferrsi run --task <task.yaml>`
   only after explicit authorization. Before `run`, confirm with the user or the
   acceptance issue that `acceptance.reference` names the accepted frozen gate
   record. InferRSI checks only that the two agree in content.

The CLI and the Agent produce the same normalized task for the same file and flags.
`tests/apps/test_task_input.py` checks this by comparing `inferrsi task preview --json`
with the Python `task_input.preview` on the shared complete fixture.
`tests/apps/test_task_plan_run.py` checks that `plan --task` gives the same `task` block,
and the expected RunSpec, for that fixture. An Agent checks a task's content against
its frozen gate record with the Python `task_input.frozen_gate`, the same check
`run --task` applies.

## Compatibility with other task formats

This contract is the core v1 task format. The DSH plugin form
(`plugins/inferrsi-dsh/form.cjs`) has its own draft `schema_version: 1` task template
with the same three section names. Its fields and values differ, for example `gpu`/`npu`
backends and the camelCase budgets `maxRounds` and `maxMinutes`, so a DSH draft file
is not a core v1 file. DSH adoption is
tracked under #152. Before DSH advertises core v1 support, it must consume this
contract and match the [shared fixtures](../../tests/fixtures/task-input/README.md) for
complete and partial tasks, relative paths, budget types, acceptance references and
invalid fields, and migrate incompatible draft fields explicitly.
