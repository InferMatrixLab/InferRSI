# Apps

Apps connects the CLI and host integrations to Benchmark preparation and
assessment, Harness execution, and Knowledge access. It binds the configured
ports, verifies requests and references, and publishes results. Benchmark
owns grading rules and Harness owns execution and retained run facts.

## Entry points

- [`cli/`](cli/) dispatches the `inferrsi` CLI.
- [`api.py`](api.py) exposes `prepare`, `execute`, `assess`, and
  `EvaluationPort` for Python callers. The saved-request CLI uses this API. The implementation in
  [`workflows/evaluation.py`](workflows/evaluation.py) binds the injected core
  ports and publishes their results.
- [`workflows/`](workflows/) composes application workflows. [`handoff/`](handoff/)
  contains host-facing adapters, and [`storage/`](storage/) handles application
  publication and reads.

## Benchmark launcher

[`workflows/benchmark_operations.py`](workflows/benchmark_operations.py)
resolves a registered task's `benchmark.py`, launches it through the Harness
child adapter, forwards arguments unchanged, and returns the child's status.
The child executes the task with `runpy` and supplies Harness's `execute_trial`
callback as an initial global. The task supplies workload setup, measurement,
and correctness rules. See the [Benchmark README](../benchmark/README.md)
for registration.

See the [saved-request CLI](../../../docs/apps-evaluate-cli.md), the
[publication contract](../../../docs/apps-output.md), and the
[module migration inventory](../../../docs/apps-module-migrations.json).
The [evaluation](../../../tests/test_apps_evaluate_cli.py) and
[launcher](../../../tests/test_benchmark_operations.py) tests exercise these
entry points.
