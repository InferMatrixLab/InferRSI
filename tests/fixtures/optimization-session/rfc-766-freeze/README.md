# Harness #766 migration baseline

The samples were created outside the source tree with the normal wheel from
`5d6f1f40aa3fe96170faf6afa92ac41ad99d3c0a` on Windows with Python 3.12.14.
The wheel is `inferrsi-0.3.5.dev23+g5d6f1f40a-py3-none-any.whl` with SHA-256
`4e5d9d6a8a3071c16ccd536ccc48c97bc852af6103ffb3d14326d923d909db98`.
Keep `samples.zip` read-only and use a fresh copy for each check. `manifest.json` pins
the archive and every member. The original receipt paths identify the run that produced
the evidence. To rerun the baseline at a new location, use the capture commands below.

| Sample | Old-wheel behavior | Evidence |
| --- | --- | --- |
| `ordinary-pending` | A real `arguments → benchmark → assess` workflow was interrupted after the candidate subprocess completed. Recovery settles the saved result with score `2`. The candidate runs once. | [Ordinary receipt](ordinary-receipt.json) |
| `service-blocked-no-pending` | The real local HTTP service reaches the formal performance gate. A missing metric produces a blocked state without a pending attempt and leaves the saved state unchanged on recovery. | [Service receipt](service-receipt.json) |
| `service-blocked-pending` | An explicit retry is interrupted after checkpointing a formal performance `FAIL`. Quality is skipped. Recovery refuses absent proof, another real attempt's proof, a wrong attempt ID, and a wrong service identity. All four refusals preserve the files. Matching proof settles the original `FAIL` once. Replay preserves launches, the verdict, the observation, and budget. | [Service receipt](service-receipt.json) and `cleanup-proofs/` in the archive |
| Two-process allocation and execution | The first process allocates an `AttemptContext` with no child or store writes. The second executes a single CPU child, confirms cleanup, and reads identical latest and pinned records. Replay returns the same record. Changing the spec raises `RequestConflict`. | [Allocation](two-process-allocate.json), [execution](two-process-execute.json), [RunSpec](two-process-run-spec.json), [record](two-process-execution-record.json) |

The ordinary plan and state use schemas 2 and 1. Service plan and state use schemas 3 and 2.
See the paired-wheel checks in the [fixture index](../README.md) for historical runtime identity
refusals. These samples establish old-wheel behavior and the expected parity checks for later slices.

## Entry points and writes at the frozen commit

[`inventory.json`](inventory.json) lists all tracked files under `src/inferrsi/harness` by mode
and Git blob, package `__all__` exports, and AST import locations in tracked `src`, `tests`,
`examples`, and `tools`. The following entry points cover runtime dispatch and persistence in
addition to those static imports. Paths are relative to `src/inferrsi`.

| Contract | Entry points and writes |
| --- | --- |
| Managed optimization session | `apps/cli/arguments.py::_optimization_actions` registers the common start, status, diagnose, round, final, recovery, and knowledge actions. Service-only baseline, reference refresh, resume, and profile act on the persisted `evaluation_mode` (`abba` or `service_reuse`). `harness/manager/_state.py` persists the plan and session state. Manager owns pending, recovery, observations, and budget settlement in both flows. |
| Ordinary execution | `harness/executor/_ordinary.py` and `_benchmark_child.py` dispatch project `arguments`, `benchmark`, and `assess`. The child protocol writes stage artifacts and the execution receipt. |
| Serving execution | `harness/executor/serving/_server.py` launches and stops the service. `serving/_attempt.py` saves attempt checkpoints. Manager validates cleanup proof before settlement. |
| Single execution | `apps/cli/evaluate.py` invokes `Harness.execute(spec)`. The public `harness.api.Harness` also provides independent `allocate` and `read` operations. `harness/executor/_execution.py::execute` runs against the configured target and store. `harness/records/_run_store.py` owns allocation and versioned commits. `harness/executor/local_process.py`, `confinement.py`, and `artifact_sandbox.py` cover the local child, cleanup, and artifact isolation. |

The published path is documented in `docs/guides/operations.md` and
`docs/contracts/harness-evidence-capture.md`. S5 will move independent allocation to the Records
package, execution to Executor, and reads to `records.RunStoreReader`. The same migration will
update Apps and the published docs, then retire `harness.api`.

## Reproduce outside the checkout

Install the frozen wheel into an isolated environment. Install `pytest` there for the capture
script, and use its Python executable from a scratch directory outside the checkout. Use new
output paths. The two allocation and execution commands share one scratch working directory and
must run as separate Python processes.

```text
python -I <fixture-dir>/capture.py --site <installed-site-packages> --source <checkout> --out <new-output-dir>
python -I <fixture-dir>/allocate_execute.py allocate <installed-site-packages> <wheel> <source-commit>
python -I <fixture-dir>/allocate_execute.py execute <installed-site-packages> <wheel> <source-commit>
```

In the first command, use a checkout of the frozen commit for the test helpers passed through
`--source` and use this directory for the driver passed as `<fixture-dir>`. The capture script
verifies that `inferrsi` resolves to the installed wheel. The two-process driver preserves the
original `RunSpec` and `AttemptContext` so the second process can check their binding directly.
The local HTTP run covers service behavior and recovery on CPU. S3 tracks real-backend reuse and
reset separately.
