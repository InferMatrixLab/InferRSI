# Saved-request evaluation CLI

`inferrsi evaluate prepare`, `execute` and `assess` use the same Apps API and
persisted result as Python. They consume already saved requests. A trusted
Python caller or host allocates the Harness attempt before saving an execution
request; the CLI does not allocate one or automatically retry a failed call.

```bash
inferrsi evaluate prepare --request @<prepare-request.json> \
  --output-id <prepare-output-id> --workspace <absolute-authorized-workspace> \
  --storage-config <storage.json> --runtime-config <runtime.json>
inferrsi evaluate execute --request @<execute-request.json> \
  --output-id <execute-output-id> --workspace <absolute-authorized-workspace> \
  --storage-config <storage.json> --runtime-config <runtime.json>
inferrsi evaluate assess --request @<assess-request.json> \
  --output-id <assess-output-id> --workspace <absolute-authorized-workspace> \
  --storage-config <storage.json>
```

Missing `--output-id` is a parser error before any port is called. Optional
`--prepared-ref @<file>` / `--record-ref @<file>` must equal the corresponding
complete reference in the request. Optional `--scope` and `--primary-claim`
must agree with its operation/scope and selected claim. They never override
saved fields. The `@file` convention belongs to these new commands; existing
fixed-view `status`, `report`, `dashboard` and `trace` plain-path options retain
their original convention.
Checking `execute --scope` reads its fixed prepared archive before execution;
an unavailable or invalid archive fails that read-only agreement check.

Input files may be formatted JSON. Duplicate keys, non-object input, non-UTF-8,
unsafe integers, non-finite values and floating-point tokens are refused.
Decimal fields follow the existing string contract. Stored outputs and stdout
use the existing canonical result encoder.
Stdout appends a line ending after that JSON value; manifest hashes and byte
comparisons apply to the canonical `result.json` bytes without that line ending.

## Trusted local runtime configuration

The adapter is located only by explicit `--runtime-config`; it is not discovered
from the working directory, storage configuration or saved request. It grants
existing B/H capabilities and is therefore trusted host input. It accepts no
import names, factories, credentials or request-selected authorities.
`StorageConfig` retains its existing schema and independently authorizes Apps
archive/record access.

```json
{
  "schema_version": 1,
  "benchmark": {
    "protocol": "<absolute-local-frozen-ProtocolV1-file>",
    "worker_role": "worker-code",
    "resources": {
      "worker-code": "<absolute-local-worker-resource-file>",
      "input-data": "<absolute-local-input-resource-file>"
    }
  },
  "target": {
    "target_id": "<configured-target-id>",
    "config_revision": "<configured-revision>",
    "work_root": "<absolute-authorized-local-work-directory>",
    "controller_root": "<absolute-authorized-controller-directory>",
    "target_root": null,
    "module_root": "<absolute-authorized-worker-source-directory>"
  }
}
```

Only `schema_version`, `benchmark` and `target` are recognized at the top level.
The selected operation requires only its section; other sections may be absent.
All configured resource/work/source paths are absolute local paths, with no
network-path or ambient-directory fallback. Output workspace is an existing
absolute local directory without symlink traversal.

- **prepare:** `benchmark` has exactly `protocol`, `worker_role`, `resources`.
  The [existing B PreparationService](contracts/production-prepare.md) validates
  the frozen task/rules and exact byte pins. Resource paths grant read-only
  role-keyed file openers. Apps independently verifies the returned closure
  before archiving it. No target or writable Store is constructed.
- **execute:** `target` requires `target_id`, `config_revision`, `work_root`.
  `controller_root`, `target_root`, `module_root` are optional; absent/null means
  unauthorized. These configure the existing H `LocalCpuTarget`. The existing
  `harness_sqlite` mount selected by `StorageConfig.harness_namespace` configures
  the Store. The adapter opens it for writing only when the verified Apps
  binding calls H. The request cannot replace this configuration.
- **assess:** no runtime file is required or read. The existing offline B
  assessor reads only fixed retained evidence through Apps; it does not prepare
  a task, construct an execution target, launch a worker or access a network.

The [CPU smoke task](contracts/p1-cpu-smoke.md) supplies the worker and frozen
rules for the production example below.

## Opt-in production evidence

`evaluate execute --capture-evidence` composes the existing frozen P1 proof
projection with the Apps role reader and H capture lifecycle. Candidate and
report roles come from B-validated frozen metadata for its supported single
output recipe. B decides rules/proof content; H authenticates sources, retains
bytes and commits the record. Invalid UTF-8 and missing evidence retain their
existing separate claim outcomes. A source that H cannot capture keeps H's
zero-start fixed refusal and B can assess that record offline.

The switch is host assembly outside the saved request and both configuration
schemas. Without it, the existing execution path remains. Projection setup
and artifact reads happen only inside H's fresh callback. Registered replay,
conflict and in-progress requests do not invoke it. Enabling capture for an
already registered attempt returns the original facts; it cannot add proofs
to an old record or authorize another worker run. A separate new execution
requires an explicitly allocated attempt under the existing H contract.

## Outputs, errors and replay

Each invocation prints its complete `AppsResultV1` and returns its `exit_code`.
The existing publication writes `output/<output-id>/manifest.json` and
`result.json` in the authorized workspace, refusing overwrite. Consumers verify
the manifest and read fixed references; raw facts and claim verdicts remain
separate.

| Existing result / error | Exit |
| --- | --- |
| Successful prepare/execute or archived primary `PASS` | 0 |
| Argument/config/ref conflict; other non-persistence public errors | 2 |
| Committed refusal with `process_outcome=not_started` | 3 |
| `AttemptInProgress` | 4 |
| `RecoveryRequired` | 5 |
| `ExecutionPersistenceError` / `ArchivePersistenceError`, including output publication | 6 |
| Committed failed, timed out, cancelled or nonzero worker execution | 7 |
| Archived primary `FAIL` | 8 |
| Archived primary `INCONCLUSIVE` | 9 |

The [existing Apps result mapping](../src/inferrsi/apps/storage/result.py)
remains authoritative. Publication failures preserve already committed refs
in the printed result. Explicitly resubmitting the original saved execute
request uses the original attempt and digest; H returns its original fixed
record or its existing in-progress/recovery/conflict response. Repeating a
completed call with an already published output ID refuses output overwrite
even though H has replayed the same record. Use another explicit output ID
when publishing a separate receipt. The CLI never substitutes a new attempt,
extends the original deadline or retries a worker.

These checks establish software behavior, not a service/performance verdict.
