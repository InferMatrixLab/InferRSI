# capture-pinned-queue-conflict

## User persona and coverage

Operator/developer debugging a concrete TorchNPU contract. Target: `graph-and-compile`.
This synthetic case stresses route discovery, workflow depth and failure recovery;
it is grounded in the declared native source evidence. It complements native
device tests and does not replace them.

## Expected successful behavior

Resolve the prompt using the listed bundled files. Preserve exact API/state/
ownership boundaries, give a bounded next check and explicitly retain missing
backend verification. Follow every concrete assertion in `assertions.json`.

## Failure signals

Generic advice without the requested contract, source-checkout dependency,
private paths, CPU-as-NPU substitution, hidden eager fallback, or a fabricated
runtime/performance PASS. Static content grading proves relevant statements
are present; a separate agent usability replay must judge their application.
