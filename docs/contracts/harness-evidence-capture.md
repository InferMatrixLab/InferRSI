# Harness evidence capture and producer sealing

`execute_attempt(..., evidence_capture=None)` accepts an optional trusted host capability
with `capture(phase, facts, *, artifacts) -> (draft_wire, proof_blobs)`. This is the
H slice accepted in [#565](https://github.com/InferMatrixLab/InferRSI/issues/565#issuecomment-7063820381)
and its [stacking/failure clarification](https://github.com/InferMatrixLab/InferRSI/issues/565#issuecomment-7064002232).
The capability is never named or instantiated by an ExecutionSpec or worker.
There are no Benchmark/Apps imports, task rules or new business wire fields in H.

## Lifecycle

Existing attempt lookup precedes all fresh preparation reads and capture calls.
Completed replay returns the original RecordRef; conflict/running/no-record
paths keep their existing errors without capture, execution or budget admission.
Ordinary mode never consults the capture configuration. `None` preserves the
existing evaluation behavior.

For a fresh evaluation, H performs its existing admission, entry/input capture
and materialization. It then calls `preparing` before the worker starts. After
the one original run, output capture and cleanup/lease observations, it calls
`finalizing` before the single record commit. Capture consumes the original
attempt window; it creates no deadline, resource reservation, charge or retry.

A valid failed or not_performed format observation is evidence rather than an
execution control: retain it and continue the one original worker under its
original limits. An illegal callback/configuration or identity/producer override
gives a registered zero-start fixed refusal. After a worker has run, rejected
capture results retain that actual execution/cleanup state and an explicit error;
they never restart it or turn it into a not_started record.

## Snapshot and read authority

`evidence_capture.CONTEXT_FIELDS` defines the closed v1 projection of existing H
facts: request/run/attempt/digest, preparation/protocol/operation/scope/candidate,
bound inputs, actual target/runtime binding, steps, started/outcome/exit code,
cleanup and leases. Preparing has no terminal observations (null fields). The
callback receives a defensive copy, not mutable spec/store/lease authority.

The read capability authorizes only exact ArtifactRef metadata from this
attempt's retained sources at the current phase. It confines regular-file opens,
bounds reads to size+1, independently verifies size/hash, closes source streams,
and returns a separate binary stream. Ref aliases, arbitrary paths and other
attempts are refused. It expires after the callback. Host code is trusted; this
is a byte-authorization interface, not process isolation from malicious plugins.

## Draft validation and sources

Draft v1 has exactly `schema_version`, `checks`, `errors`. Each check has
`check_id`, `checker_revision`, `subject`, `phase`, `artifact_schema`, `status`,
`reasons`, nullable `proof_key`, and `source`. Errors have `code`, `check_ids` and
`reason`. Proof blobs are a separate map of identifier to immutable canonical
JSON bytes; there are no supplied Refs, paths or producer overrides.

- `candidate_capture` is preparing-only. H requires the actual candidate source
  to have been read through the capability and the proof's candidate/hash/attempt
  to match its BoundInput.
- `worker_report` is finalizing-only, with a running/finalizing observation phase.
  It additionally requires an actually started input-bound step, an observed
  entry/revision/code pin matching the frozen step and a declared retained output
  read through this capability. H seals task_worker identity from that runtime.
- `cleanup_capture` is finalizing-only. A supplied confirmation must agree with
  H's cleanup/process-exit/acquired-lease facts. It cannot override unknown or
  failed cleanup.

H checks common identity and reserved producer fields without interpreting the
grader or sample rules. Supplied status must agree with a proof's status when
present. H alone seals producer kind/identity/revision, actual control domain and
capture route. A not_performed check without a proof is H's observation of the
gap; it does not impersonate a worker that produced no verified proof.

## Retention and failures

H computes proof hashes and tentative Refs from the snapshot bytes. Its existing
Claim.commit byte-source support retains all raw/derived artifacts before the
one durable record append. Valid RecordRefs are issued only after that commit.
Proof retention or append errors therefore use the existing
ExecutionPersistenceError with actual started state, partial facts and only
confirmed retained references. Uncommitted declarations are not published as
verified Refs. No Apps code writes a RunStore row.

Well-formed draft errors preserve matching not_performed checks and any
independent valid families. Structurally invalid drafts have no trustworthy
task-check descriptor: H records its own `evaluation_capture` not_performed check
and a declared error, while retaining previous valid checks and raw output facts.
Unknown host programming exceptions propagate; the unfinished attempt remains
RecoveryRequired rather than being implicitly resumed.

This supplies capture mechanics only. B's report codec/projector and the Apps
host adapter are separate. Real worker/grader/sampler semantics and resource
pins remain an explicit acceptance gate; synthetic observers and green smoke
tests do not establish complete F/C/M or whole-Issue production acceptance.
