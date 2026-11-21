# P1 worker-report codecs and capture drafts

`inferrsi.benchmark.proofs` owns pure `encode_report`, `decode_report`,
`validate_report`, `project`, and `ProofProjector` ports. This is the Benchmark
codec/projector slice of the accepted capture boundary in
[#565](https://github.com/InferMatrixLab/InferRSI/issues/565#issuecomment-7063820381).
It does not implement a worker, grader predicate, baseline workload, sampler,
Harness capture lifecycle or Apps adapter. Their actual behavior and resource
pins remain prerequisites for shared production acceptance.

## Closed raw report

The frozen `fixture-grader@1` output contains exactly `schema_version: 1`,
`grader` and `samples`. The latter two are required and may be null for an
incomplete family. A non-null grader contains exactly `status` (`passed` or
`failed`) and `reasons` (portable identifiers). Samples contain the four frozen
identities A1/B1/B2/A2, baseline/candidate/candidate/baseline and rounds 1/1/2/2.
Each value is a positive canonical Decimal string with unit `ms`.

No identity, Ref, producer, control domain or cleanup assertion is accepted from
the worker. JSON whitespace is allowed; duplicate keys, floating/nonfinite
numeric tokens, invalid Unicode and unsupported versions are rejected. Encoders
use the existing canonical v1 codec. Neither encoding nor validation opens files.

## Frozen configuration and runtime inputs

Construct `ProofProjector(prepared, protocol_bytes)` before attempting execution.
It snapshots the preparation and checks the existing task/grader/recipe/rule
support and complete protocol identity using the production preparation port.
Unsupported configuration raises `ProofError` with the existing portable code.

Call `project(phase, facts, *, candidate_bytes, report_bytes)` on that object, or
use the one-shot function with `prepared` and `protocol_bytes` first. The two
phases are `preparing` and `finalizing`. Bytes are supplied by a host adapter;
this module receives no filesystem, network, process, archive or store handle.
`None` means the corresponding byte input is unavailable. An unexpected host
content type raises `TypeError` rather than becoming an evidence gap.

`CONTEXT_FIELDS` specifies a closed version-1 wire projection of existing H
facts: request/run/attempt/digest, preparation/protocol/operation/scope/candidate,
actual bound inputs and target/runtime binding, steps, started/outcome/exit code,
cleanup and leases. Unavailable terminal fields are null. The host supplies a
defensive snapshot; no shared Python business DTO is introduced.

The candidate bytes must match the actual retained input's digest, size, attempt
and capture fact. Any frozen candidate expectation also applies. Worker report
families require an actually started input-bound step with the observed entry,
revision and code digest matching the frozen recipe. Allowed control domains
must match the actual target; changing a locator does not change identity.
These checks do not authenticate a caller-provided context: H owns the context,
read capability and final producer sealing.

## Draft output and refusal

The return is `(draft_wire, proof_blobs)`. Draft wire has exactly
`schema_version`, `checks` and `errors`. Each check has the frozen check identity,
revision, subject, phase and artifact schema, plus status, reasons, `proof_key`
and source. Sources are `candidate_capture`, `worker_report`, `cleanup_capture`.
`proof_key` is null when no proof was produced. The separate map associates keys
with immutable canonical proof bytes. Errors contain a portable `code`, affected
`check_ids`, and an identifier `reason`.

The preparing phase checks actual UTF-8 bytes and drafts format-proof@1. Invalid
UTF-8 gives a failed format proof, not a host error or an invented correctness
failure. This projector does not decide whether to start a worker.

The finalizing phase projects completed grader/sample families into the existing
grader-proof@1 and samples-proof@1. Attempt/candidate/hash fields come from H
facts, never report declarations. A missing or invalid family is not_performed
without a proof. A valid grader result survives invalid sample semantics, and
vice versa; invalid raw JSON or a foreign report envelope invalidates the report
itself. The cleanup proof comes only from observed cleanup and acquired-lease
release facts. Unknown or failed cleanup never becomes confirmed.

H must validate drafts, retain raw and derived bytes before its record commit,
compute Refs itself and seal actual producer/domain/route/attempt fields. A draft
is neither a trustworthy CheckObservation nor a committed Ref. Existing offline
assessment and V21/V22 rules remain unchanged. This slice alone cannot make a
real execution record contain matching proofs or establish complete F/C/M.
