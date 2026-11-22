# Shared task-input fixtures (schema v1)

These files are the conformance cases for the YAML task contract read by
`inferrsi task validate|preview` (`src/inferrsi/apps/cli/task_input.py`, schema and
template under `src/inferrsi/apps/cli/task-input/v1/`). See
[docs/task-input.md](../../../docs/task-input.md).

| File | Case |
| --- | --- |
| `complete.yaml` | An execution-complete task with non-default backend, repetitions and threshold, relative paths and a local plan reference |
| `partial.yaml` | The partial draft from the governing issue: valid, with field-level blockers |
| `invalid-cases.json` | Rejected inputs: `yaml` text and the exact error `fields`; `schema_detects: false` marks cases that JSON Schema alone accepts or that never load as YAML: duplicate or merge keys, several documents, values the loader cannot build, NaN, integral floats such as `3.0`, numbers beyond float range, quoted-command parsing, malformed URLs (unparsable, without a host, or with an invalid port, whitespace or control characters), NUL characters in paths, the Python selector and argv items, and lone surrogates |

`tests/test_task_input.py` checks the Python contract and the packaged JSON Schema
against these files, and `tests/check_installed.py` reuses `complete.yaml` from an
installed wheel outside the checkout. `tests/test_task_plan_run.py` uses `complete.yaml`
and `partial.yaml` with `inferrsi plan --task` and `inferrsi run --task`. It checks the
expected RunSpec, the `task` block against `task preview --json`, overrides, conflicting
acceptance flags, field errors before any probe or write, and the run's baseline revision
and local reference checks.

Another entry point that reads InferRSI task files, such as the DSH plugin (#152), must
consume this contract and match these fixtures (complete and partial tasks, relative
paths, budget types, acceptance references and invalid fields) before it advertises
core v1 support.
