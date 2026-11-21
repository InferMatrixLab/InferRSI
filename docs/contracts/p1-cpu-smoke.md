# P1 CPU handoff/evidence smoke task

The accepted [task specification](https://github.com/InferMatrixLab/InferRSI/issues/565#issuecomment-7064895332)
defines `p1-cpu-smoke@1` with `p1-cpu-smoke-rules@1`. This is a software
handoff/evidence task, not a model-quality, speedup or service benchmark.
The historical `p1-fixture@1 / p1-rules@1` behavior and vectors are unchanged.

## Frozen operations and evidence

The standalone `benchmark/workers/fixture_worker.py` contains the fixed public
`INPUT_BYTES`. Reference A sums those bytes and returns canonical ASCII decimal
plus one LF. Candidate B reads the actual candidate file's answer bytes. The
worker compares them exactly: equality gives C passed, otherwise C failed with
`response_mismatch`. A missing candidate read gives no C proof rather than a
mathematical failure. Candidate text cannot supply grader status or provenance.

M measures four real operations A1/B1/B2/A2 (AB, BA), using monotonic nanoseconds
converted by integer arithmetic to canonical Decimal milliseconds. Sampling runs
regardless of C's result. There is no fill, clamp, minimum, warmup, retry or
re-measurement. A failed/non-positive/missing sample makes that family incomplete.
The initial C comparison is outside the four timed operations. Values are
evidence, with no numeric performance threshold or comparison/gain claim.

F remains the separate H-owned capture of actual UTF-8 candidate bytes. Cleanup
and acquired-lease release remain H facts. The existing P1 F/C/M decision rules,
closed worker-report format, evidence matching, conflict handling and empty
metrics/comparison arrays are reused. A failed C does not overwrite M or skip its
sampling; an M PASS is measurement validity only.

## Explicit configuration and resource closure

`benchmark.cpu_smoke.worker_source()` explicitly reads the packaged owned worker.
`protocol(worker_bytes, *, control_domain)` is pure and requires the host's
declared actual domain. `prepare_service(control_domain=...)` snapshots that
resource and configures the existing production PreparationService. Its resource
capability serves immutable bytes for worker-code and baseline-code. The latter
is Protocol.baseline and identifies the same full source, including A and the
embedded input. No network, external input, device, model or undeclared script is
part of the task. The label/decimal parameters retain their encoding-only role.

`default_request()` provides the supported task request. The host archives its
preparation, configures the B ProofProjector and Apps EvidenceCapture, and supplies
H with a trusted module_root containing those exact `fixture_worker.py` bytes.
The frozen argv remains candidate path and report path. H imports no B module.

## Acceptance sequence and limits

Record exact worker/source/input pins in the PR before running acceptance cases,
as required by the owner. Never retune them after results. Test the real correct
answer, valid UTF-8 wrong answer and invalid UTF-8 independently; verify actual
timing validity/order without value thresholds. Retain missing, rejected,
conflicting and failed cases and original-attempt replay outcomes.

PR readiness is separate from shared production acceptance. The stacked codec,
capture, adapter and launcher prerequisites must reach main, branches must sync,
and final-head checks/two independent reviews must pass before integration. The
shared D023/t108-v4 matrix then runs on merged source. Tests on a development
stack do not establish that final acceptance or any service-performance claim.
