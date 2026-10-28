# Finite resource and namespace cleanup diagnostic

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
INCONCLUSIVE; reviewed preparation, not yet submitted.

CPU2009 demonstrated correct evaluation of four trusted handwritten cases, but
its polling did not prove aggregate limits or complete cleanup. Source inspection
also found a writable independent /dev tmpfs and unbounded SysV object creation.
This bounded follow-up makes /dev readonly while preserving its limited /dev/shm,
sets finite task/address-space/file limits, and applies a narrow ABI-checked kernel
filter to SysV calls and mq_open. It leaves POSIX semaphore operations available.
These restrictions require an actual repeat of the four-case EvalPlus API check.

Five fixed modes cover limit rejections and inheritance, synthetic evaluation,
and normal/timeout/launcher-kill cleanup of two registered live descendants,
including a setsid double-fork. The supervisor blocks payload startup until it
has bound the actual namespace PID1 to a pidfd and parent/NSpid/PID namespace
identity. Early bubblewrap user-namespace metadata is not treated as final payload
identity. The supervisor waits for actual init/known-child exits and retains errors.
No full generated-code qualification is claimed. RLIMIT_NPROC counts UID threads;
RuntimeError from thread creation is retained without assigning a kernel cause.
The 16GiB scheduler request is not an enforced aggregate memory limit.

Pre-run independent review corrected isolated-interpreter import resolution,
cleanup errors masking evidence, and lost partial status. Rejected sources remain
preserved. A local control capture conflict corrupted a JSON when stdout and the
test both wrote the same file; the damaged record is preserved and the valid
re-run agrees with independent execution. Local tooling has no psutil; isolated
import controls stub only that module, while cluster execution uses the previously
inventoried registered package. New source lint and shell syntax pass. The existing
frozen runtime style findings remain disclosed. New logic controls and the prior
18 completion / 13 benign-reference cases were independently rerun successfully.

The actual Python/evaluator dependencies and prior reference inventories are
unchanged. No heldout inputs, model-generated program, GPU or E2E run is authorized
by this preparation. Source-level and Linux-manual references are in plan.json;
the tested source identities and the original rejected attempts remain separate.
