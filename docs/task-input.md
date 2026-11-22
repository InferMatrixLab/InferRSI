# YAML task input (schema v1)

Write an InferRSI task once, or ask an Agent to generate it. Then use the same YAML
file from the CLI or hand it to an Agent. Both entry points read it through one
shared contract, `inferrsi.apps.cli.task_input`, so the same file gives the same
normalized task fields either way.

`inferrsi task validate` and `inferrsi task preview` are available now. They are
read-only. Using a complete task file directly with `inferrsi plan --task` and
`inferrsi run --task` is not implemented yet. Until it is, pass the previewed values
to `plan` and `run` as their existing flags (see the [field table](#fields)).

| Resource | Location | Print from an installed CLI |
| --- | --- | --- |
| JSON Schema (draft 2020-12) | `src/inferrsi/apps/cli/task-input/v1/schema.json` in the wheel | `inferrsi task schema` |
| Agent-oriented template | `src/inferrsi/apps/cli/task-input/v1/template.yaml` in the wheel | `inferrsi task template` |
| Shared conformance fixtures | [`tests/fixtures/task-input/`](../tests/fixtures/task-input/README.md) | — |

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
| `acceptance.reference` | HTTP(S) issue URL or local plan path | — | yes | — |
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

`task preview` accepts the mapped flags from the table as overrides. The effective
value of each field is:

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
   under the operation's own boundary in [operations](operations.md).

The CLI and the Agent produce the same normalized task for the same file and flags.
`tests/test_task_input.py` checks this by comparing `inferrsi task preview --json`
with the Python `task_input.preview` on the shared complete fixture.

## Compatibility with other task formats

This contract is the core v1 task format. The DSH plugin form
(`plugins/inferrsi-dsh/form.cjs`) has its own draft `schema_version: 1` task template
with the same three section names. Its fields and values differ, for example `gpu`/`npu`
backends and the camelCase budgets `maxRounds` and `maxMinutes`, so a DSH draft file
is not a core v1 file. DSH adoption is
tracked under #152. Before DSH advertises core v1 support, it must consume this
contract and match the [shared fixtures](../tests/fixtures/task-input/README.md) for
complete and partial tasks, relative paths, budget types, acceptance references and
invalid fields, and migrate incompatible draft fields explicitly.
