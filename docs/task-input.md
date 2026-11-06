# Shared YAML tasks

Use a v1 task file to give the CLI and an Agent the same input. A normal
InferRSI install includes the parser, [v1 schema](../src/inferrsi/data/task_input/schema-v1.json)
and [YAML template](../src/inferrsi/data/task_input/template-v1.yaml).

```bash
inferrsi task template > task.yaml
inferrsi task schema
inferrsi task validate task.yaml
inferrsi task preview task.yaml --json
```

An Agent can read or fill in the same template. Have it run the same validation
and JSON preview and review the effective values with you before proceeding.
A valid draft can omit any section or leave a field as null. The preview lists
missing fields by dotted path and sets `complete` when all required inputs are
present. Validation and preview read the file without invoking processes,
inspecting the runtime, or writing workspace or experiment files. Invalid input
exits with status 2.

| Section | Required for `plan` and `run` |
| --- | --- |
| `optimization` | Repository, model, framework (the CLI's repository type), workload, objective and SIAS plane |
| `environment` | Backend, baseline and candidate argv, benchmark repetitions and time budget |
| `acceptance` | Issue URL or local plan path, full baseline Git object ID, metric key, unit, direction and agreed minimum improvement percentage |

Use the schema for exact field names, types and CLI mappings. Supply any device
selectors or quality inputs the accepted plan requires. Set
`acceptance.require_quality: true` when the quality command is mandatory.
`acceptance.constraints` records additional plan requirements for review.
The existing runner evaluates its configured metric and validation command.

- Use a single UTF-8 YAML document up to 64 KiB. Use plain mappings and argv
  lists of strings. Duplicate and unknown keys, aliases, anchors and explicit
  tags are errors. Numeric inputs use decimal notation, booleans use
  `true`/`false`, and strings that resemble these values should be quoted.
- YAML filesystem paths are relative to the file. Paths in explicit CLI flags
  are relative to the caller's working directory. With a task file, the default
  output directory is `runs` next to the YAML. A bare Python executable name is
  resolved through the existing runtime lookup. Script paths and other argv
  tokens keep the existing per-checkout working-directory semantics. Model
  identifiers and HTTP(S) acceptance references stay as given.
- In preview, plan and run, explicit mapped CLI flags override YAML for
  optimization and environment inputs. Built-in defaults fill omitted optional
  fields. Acceptance settings come from YAML. A conflicting CLI acceptance
  flag is rejected. Existing flag-only commands use their usual defaults.
- Keep credentials in the existing runtime channels. Review the YAML,
  normalized preview and experiment records before sharing them.

After reviewing the exact commands and the effective values against the
accepted frozen gates, inspect the prepared environment and explicitly run
the experiment:

```bash
inferrsi plan --task task.yaml
inferrsi run --task task.yaml --confirm-acceptance
```

`plan` and `run --dry-run` use the existing environment probes, including
the configured Python interpreter. Task-file operations check the baseline
checkout's HEAD against the pinned object ID. A local acceptance reference
must point to an existing file. Pass `--confirm-acceptance` after checking
the effective values against the referenced frozen gates. InferRSI records
the confirmation and effective task. Review of the issue or plan is performed
by the caller or Agent. The [operation guide](operations.md#experiments) and
[evidence rules](contributing.md#evidence-and-claims) apply to the result.

The DSH draft format is tracked separately under
[#152](https://github.com/InferMatrixLab/InferRSI/issues/152). Check legacy
DSH files against the core schema and migrate incompatible fields before
using them with these commands. DSH integration uses the core contract and
shared fixtures when it advertises core v1 support.
