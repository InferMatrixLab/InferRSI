# Harness

Harness owns execution, source checks, budget accounting, recovery, and
retained run evidence. Apps assembles runtimes and ports. Benchmark defines
measurement and assessment rules.

## Entry points

- [`api.py`](api.py) exposes `Harness.allocate`, `execute`, and `read` for local
  CPU commands. [`local_process.py`](local_process.py) owns the process domain.
- [`run_store.py`](run_store.py) provides `RunStore` and `RunStoreReader` for
  namespaced records and content-addressed artifacts. Pass `record_version`
  to read a fixed record and use `open(ref)` to read retained artifact bytes.
- [`runner.py`](runner.py) owns the common AB/BA loop. It calls injected
  `execute`, `snapshot`, `assess`, and `report` ports and records the returned
  assessment. [`trials/external.py`](trials/external.py) runs and retains a
  single command trial with the supplied metric reader.
- [`optimization_session.py`](optimization_session.py) connects session
  commands to the budget and recovery logic in [`optimization.py`](optimization.py).
  [`task_protocol.py`](task_protocol.py) prepares task protocol packages and runs
  their operations in a subprocess with source hash and response checks.
- [`skill_evaluation.py`](skill_evaluation.py) executes and retains
  skill-evaluation trials. [`artifact_sandbox.py`](artifact_sandbox.py) captures
  and replays submitted artifacts. [`improvement.py`](improvement.py) advances
  search using injected assessments.

## Evaluate retained runs

With the Apps saved-request CLI, a trusted caller allocates the attempt before
execution. Use `--runtime-config` to supply the trusted runtime for `prepare`
and `execute`. The `--storage-config` file authorizes retained data access,
including the RunStore mount selected by its Harness namespace. Use
`--output-id` to publish the operation result. `execute --capture-evidence`
opts a fresh attempt into production proof capture. Assessment reads fixed
retained evidence.
See the [evaluation options and replay behavior](../../../docs/guides/apps-evaluate-cli.md),
the [iterative workflow](../../../docs/guides/optimization-workflow-unification.md),
and the [improvement workflow](../../../docs/guides/harness-improvement.md).

For extension points, see the [architecture](../../../docs/architecture.md#where-to-extend).
The [RunStore tests](../../../tests/harness/test_harness_run_store.py) and
[task protocol tests](../../../tests/benchmark/test_qwen_optimization_protocol.py) cover
the storage and execution boundaries.
