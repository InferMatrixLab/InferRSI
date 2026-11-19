# Explicit generation evidence records

The bundled [auditor](../scripts/audit_generation_evidence.py) validates and
summarizes **caller declarations**, not Swift concurrency, GPU state or elapsed
time. API: `audit(plan) -> dict`, `example() -> dict`; invalid schema raises
`EvidenceError` (a ValueError). `--example` emits synthetic input. A regular JSON
file or `-`/omitted stdin emits an audit; valid schema returns exit 0 even with
evidence gaps/conflicts, invalid input returns exit 2 with a fixed diagnostic.

## Top-level schema

Exactly these keys are required:

| Field | Required declaration |
| --- | --- |
| `schema_version` | Integer 1, not boolean |
| `source_repository` | Exact `ml-explore/mlx-swift-lm` |
| `source_commit` | Lowercase 40-hex full commit; a different revision becomes an explicit reviewed-contract gap, not presumed compatible |
| `resolved_mlx_commit` | Lowercase 40-hex full resolved dependency commit, or null if unrecorded; a package version range is not a commit |
| `declared_backend` | `metal`, `cpu`, `unknown` or `not_run`; never authenticated by the helper |
| `records` | 1..128 records, unique opaque generation IDs |

The known contract is source revision
`3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac`. Comparing its string to a supplied
commit is only a provenance consistency check, not checkout authentication.
Input is capped at 64 KiB and must be finite UTF-8 JSON without duplicate keys.
Unknown/missing keys, booleans as counts, malformed types, overly deep/malformed
JSON and nonregular files are rejected. Use anonymized opaque IDs, not prompts,
token content, paths or secrets. The helper writes only stdout/stderr and uses
no network, subprocess, Swift/MLX imports, task execution or GPU access.

## Per-record schema

Exactly these keys are required:

| Field | Meaning |
| --- | --- |
| `generation_id` | Unique 1..80-character ASCII ID matching letters/digits/underscore/dot/hyphen |
| `api` | `generateTask`, `generateLoopTask`, `generateTokensTask`, `generateTokenTask`, `generate` or `ModelContainer.generate` |
| `consumer_end` | `exhausted`, `early_break`, `consumer_cancelled` or `not_observed` |
| `producer_task_retained` | true/false/null: whether an owner retained the **producer** task handle; not the consumer's separate Task |
| `producer_task_join` | `completed`, `not_observed` or `unknown`: completed means that handle's awaited value actually returned |
| `final_info` | null if not observed, or exactly `{"stop_reason":"stop|length|cancelled","generation_token_count":0}` with a nonnegative signed 64-bit integer count |
| `mlx_default_stream_sync` | `observed`, `not_observed` or `unknown`: a separate observation of the source's MLX default-stream synchronization, not every GPU stream |

`generate` means the inspected async **stream-returning** overload, not the
deprecated synchronous callback API. `ModelContainer.generate` also returns
only a stream. `generateLoopTask` identifies the public Handler wrapper at
source line 2695, not its private Handler/Collector implementation at line 2715.
Package-only `generateProtocolTokensTask` is excluded from this schema.
Claiming either stream-only API directly exposed a producer task is an API/
ownership conflict. Completed join without a retained producer handle is also
inconsistent under this record's definition. A separate application's wrapper
task or a consumer task is not the framework's producer handle.

## Interpretation and deliberate uncertainty

The audit retains final-info counts and reasons as declared; it does not
recalculate generated tokens from chunks or raw collector results. Consumer
cancellation does not force the reported stop reason to be cancelled without
causal ordering. Missing final info after consumer cancellation is not itself
failure: the producer may have attempted a yield after its consumer ended.

Rows with a retained handle from a task-returning API and an observed completed
join, without ownership conflicts, are labeled `caller_declared_join_only`.
Other rows have `cleanup_evidence=unresolved`. Summary counts distinguish
declared completed joins, unresolved rows, conflict rows and uncertainty rows.
Even the joined label does not certify native cleanup, numeric parity, physical
fit or safe reuse of another mutable object. Synchronization observations alone
do not replace producer completion/ticket-scope ownership.

Every output preserves `native_verification=not_run`,
`engine_execution=not_run_by_helper`, `evidence_authentication=not_verified` and
`performance_claim=not_assessed`. No elapsed-time or speedup calculation and no
`PASS` verdict exists. Unknown source/dependency/backend identity stays visible
in `identity_gaps`; source mismatch is not silently removed by a joined record.

For native ground truth, use [the evidence boundary](native-evidence.md), not
synthetic records as a substitute. Original source test fixtures and execution
commands are deliberately not bundled with this portable runtime procedure.
