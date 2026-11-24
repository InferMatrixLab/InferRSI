# Benchmark

Benchmark owns task definitions, resource preparation, measurement rules,
and independent assessment. Apps assembles task execution with Harness and
delivers Knowledge context where the workflow calls for it.

## Entry points

- [`registry.py`](registry.py) discovers and describes packaged tasks without
  loading their execution runtimes. Use `inferrsi benchmarks list`,
  `show <name>`, and `run <name> ...` through the Apps CLI.
- [`preparation.py`](preparation.py) exposes `PreparationService` to validate a
  frozen protocol and pin its resources. [`assessment.py`](assessment.py)
  exposes `AssessmentService` to assess fixed retained evidence offline.
- [`metrics.py`](metrics.py) reads and validates trial metrics. Task packages
  supply their own workload semantics and correctness rules.

## Add an engineering task

1. Create a package under [`tasks/`](tasks/) with `task.json`, `TASK.md`, and
   `benchmark.py`. Keep the baseline, inputs or input requirements, checks, and
   license with the package. Include task qualification and integration tests.
2. Add the directory name to `packages` in [`tasks/index.json`](tasks/index.json).
   Schema version 1 requires unique lowercase alphanumeric names separated by
   hyphens. The common list, show, and run commands discover it through the registry.
3. For an iterative task, supply the task's `optimization.py`. Discovery for
   `list --iterative` checks file presence without importing task code or
   probing devices.

The [Apps launcher](../../../docs/apps.md#benchmark-launcher) forwards the task's
arguments and returns its exit status. Tasks own device setup, timing, and
correctness. The MoE entry passes the injected `execute_trial` callback to
its evaluation code, then supplies its metric reader and metric key to the
executor.

See the [engineering workloads](../../../docs/benchmarks/engineering-benchmarks.md)
and [iterative workflow](../../../docs/optimization-benchmarks.md). The
[registry and launcher tests](../../../tests/test_benchmark_operations.py),
[engineering task tests](../../../tests/test_engineering_benchmarks.py), and
[assessment tests](../../../tests/test_benchmark_assessment.py) cover these seams.
