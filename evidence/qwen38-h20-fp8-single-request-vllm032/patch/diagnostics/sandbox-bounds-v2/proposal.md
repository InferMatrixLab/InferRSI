# Startup authorization and actual pidfd capability retry

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
INCONCLUSIVE; reviewed preparation, not yet submitted.

CPU2012 exposed a missing Python pidfd API and a fail-open setup pipe: EOF
released payloads, and four output hashes were captured before later writes.
This version first exercises raw Linux x86_64 LP64 pidfd syscalls with the
registered interpreter and a finite trusted child. A capability failure stops
before bubblewrap. The probe phase binds that evidence to its job, source,
Python binary and kernel. No PID-based fallback replaces the stable pidfd.

After binding namespace PID1, the supervisor must send the exact authorization
token and close its pipe. The payload rejects absent, short, wrong, oversized,
or non-terminated tokens before resource tests or evaluator work. Six startup
cases include launcher death before setup release. Five existing trusted modes
then exercise limits, four full EvalPlus synthetic cases and cleanup on normal
exit, timeout and launcher death. Final output hashes require observed namespace
init and launcher exit; incomplete cleanup stops remaining cases and marks output
digest as an unstable partial snapshot.

The policy and registered packages remain unchanged, including UID task limit16.
Earlier fork EAGAIN may have reflected overlapping late payloads; it is not a
basis for increasing that limit. A16GiB Slurm request is not an enforced aggregate
memory cap. Thread-creation RuntimeError still has no attributed kernel cause.
No heldout task, model-generated code, GPU, performance search or E2E measurement
is part of this diagnostic. Formal generated-code qualification remains pending.

Local startup controls use the real gate entry and mock only Linux-specific
supervision. They also verify wrong-job rejection, preserved errno, missing-exit
hash suppression and stopping further cases. Existing filter/identity/cleanup
and reference controls pass. The first startup-control fixture failed because it
tried to overwrite an exclusive JSON output; its original source and failure are
preserved, and the corrected separate-file fixture passes. Repository-configured
Ruff and shell syntax checks pass. Ambient global Ruff additionally flags broad
error-retention catches and AST-based test loading; these are not Linux results.

Independent review found that a live launcher could still write after init exit.
The rejected source is preserved; the repair requires both writers to exit and
stops further cases on incomplete cleanup. The launcher-timeout negative control
now rejects final output hashes. Independent review is recorded against the exact
four source hashes. The actual
runtime result must be retained regardless of outcome. No acceptance gate is
activated by this preparation, and GPU readiness accounting remains unchanged.
