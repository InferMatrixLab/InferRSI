# Harness evaluation replay and original limits

`execute_attempt` accepts the saved canonical ExecutionSpec. Static schema and
field checks run first. Harness then snapshots the request and checks its
existing RunStore identity/digest before reading preparation bytes, resolving a
target, admitting a budget, binding source or starting a process.

| Existing state | Outcome |
| --- | --- |
| Finished committed attempt, same digest | Original fixed RecordRef and payload; no new binding, registration or worker |
| Same attempt, different digest | RequestConflict before artifact IO or target checks |
| Live owner, no terminal record | AttemptInProgress; attempt count unchanged |
| Owner gone or persistence failed without a record | RecoveryRequired; no implicit resume or new worker |
| No registered attempt | Validate fixed preparation/support, then atomically claim and execute |

The non-registering lookup does not replace the atomic claim. A caller can
register while another is reading the preparation; the later claim still
applies the same digest/state table. A corrupt or unavailable RunStore is an
error, never permission to start again. Lookup failures do not fabricate a
known start state.

Finished positive and refusal records both remain fixed. Repairing a missing
or mismatching source does not turn replay into a new run. The currently
configured target may be retired and the preparation reader unavailable on the
Harness replay path. The original record remains authoritative. Apps performs
its own saved-request binding before handing the ExecutionSpec to Harness; this
does not change Apps archive retention requirements.

## Identity, deadline and budget

The original request retains its attempt, request digest, target request,
deadline and complete budget. Host callbacks receive no mutable alias to the
internal request snapshot. A changed deadline, budget scope or preparation Ref
changes the digest and conflicts with an existing attempt. Reentry never
allocates a new identity, resets a deadline, reserves capacity or charges again.

Fresh evaluation requests keep the original absolute attempt deadline when
step timeout is null. Known expiry/cancellation stops before source capture.
Mid-run expiry and explicit caller cancellation use the existing process-domain
supervisor and retain process exit, cleanup and lease release as separate facts.

The initial CPU target keeps the existing free-CPU budget support boundary.
Unsupported policies, dimensions or enforcement requirements are explicitly
rejected before worker binding. Reserved/charged amounts remain unknown or
inapplicable rather than invented zeros. Actual observed usage and the original
budget admission remain in the fixed record. This slice adds no budget provider,
currency model or numeric acceptance gate.

## Verification boundary

The software tests combine real production preparation, Apps archives and the
configured source target. They cover completed/refused replay, digest conflicts,
live-owner and abandoned state, real running replay, real null-timeout expiry,
caller cancellation with a descendant, fixed cleanup facts, commit failure after
a real start, cross-process replay and registration races. Execution facts do
not provide a complete Benchmark F/C/M proof or a service-gain claim.

The [local process supervisor](../../src/inferrsi/harness/executor/local_process.py)
rechecks cancellation and the attempt deadline or step timeout after opening
logs and before starting the worker. The
[launch-boundary test](../../tests/harness/test_harness_execute.py) covers this
check. Whole CPU acceptance of this slice still requires the combined evidence
tracked in the governing Harness and Apps issues.
