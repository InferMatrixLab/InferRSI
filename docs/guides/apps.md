# Apps

Apps connects the CLI and host integrations to Benchmark preparation and
assessment, Harness execution, and Knowledge access. It binds the configured
ports, verifies requests and references, and publishes results. Benchmark
owns grading rules and Harness owns execution and retained run facts.

## Entry points

- [`cli/`](../../src/inferrsi/apps/cli/) dispatches the `inferrsi` CLI.
- [`api.py`](../../src/inferrsi/apps/api.py) exposes `prepare`, `execute`, `assess`, and
  `EvaluationPort` for Python callers. The saved-request CLI uses this API. The implementation in
  [`workflows/evaluation.py`](../../src/inferrsi/apps/workflows/evaluation.py) binds the injected core
  ports and publishes their results.
- [`workflows/`](../../src/inferrsi/apps/workflows/) composes application workflows. [`handoff/`](../../src/inferrsi/apps/handoff/)
  contains host-facing adapters, and [`storage/`](../../src/inferrsi/apps/storage/) handles application
  publication and reads.
- [`workflows/speculative_search.py`](../../src/inferrsi/apps/workflows/speculative_search.py) connects
  the Engine search CLI to Harness. [`search_benchmarks.py`](../../src/inferrsi/apps/workflows/search_benchmarks.py)
  supplies Engine and Skill evaluators, and [`search_roles.py`](../../src/inferrsi/apps/workflows/search_roles.py)
  implements the trainable CPU roles.

## Benchmark launcher

[`workflows/benchmark_operations.py`](../../src/inferrsi/apps/workflows/benchmark_operations.py)
resolves a registered task's `benchmark.py`, launches it through the Harness
child adapter, forwards arguments unchanged, and returns the child's status.
The child executes the task with `runpy` and supplies Harness's `execute_trial`
callback as an initial global. The task supplies workload setup, measurement,
and correctness rules. See the [Benchmark README](../../src/inferrsi/benchmark/README.md)
for registration.

See the [saved-request CLI](apps-evaluate-cli.md), the
[publication contract](apps-output.md), and the
[module migration inventory](../apps-module-migrations.json).
The [evaluation](../../tests/apps/test_apps_evaluate_cli.py) and
[launcher](../../tests/benchmark/test_benchmark_operations.py) tests exercise these
entry points.
