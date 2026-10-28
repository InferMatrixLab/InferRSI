# Compute platform and bounded filesystem readiness

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for sandbox and campaign acceptance; both diagnostic phases completed.**

The previous CPU1996 transport probe timed out before storage work. CPU1997
isolated the missing platform/storage observations without network requests,
package changes, evaluator or model execution. Slurm reports COMPLETED0:0 in
11seconds with2CPUs actually allocated against1requested, zeroGPUs; the allocation
is released. The3-minute job bound includes startup; the120-second helper deadline
begins only after imports and output setup. The2GiB request is not a verified hard
memory limit.

The actual compute interpreter reports CPython3.12.13/Linuxx86_64/glibc2.32 and
packaging26.3. Its879 ordered supported wheel tags and hashes of packaging's
top-level Python sources are retained in the observation. This supplies a target
for wheel selection; it does not prove package installation or evaluator behavior.

The filesystem phase completed in3.898181969seconds:32 writes of256KiB followed
by fsync (8MiB total), plus128 separately opened/written/closed4KiB files.
Small files were not fsynced. Every produced synthetic byte and the exact file
inventory were checked against the reviewed generator.420 timed operations are
retained. This is one diagnostic sample, not physical storage throughput, a
repeatable extraction benchmark, or proof that all earlier installer delay came
from the network. The earlier network timeout and its unmeasured-storage scope
remain unchanged.

The executed wrapper/helper/probe match reviewed bytes in the private output
archive. Five optimized-Python mock controls cover complete execution, metadata
and filesystem failure, a late timeout and skipped work after the deadline.
Ruff and shell syntax checks passed. Raw scheduler/log/archive identities are
retained by hash; the complete public observation has no private paths or hosts.

The next proposed action is local raw-wheel prefetch using these actual tags,
the unchanged5-build/92-runtime locked package sets (96unique packages), and
the two previously reviewed local wheels. Full wheel metadata/size/digest checks
must precede any offline installation. No runtime version or package set change
is implied by a different transport route. CPU1997 itself has no measured E2E
effect and does not activate quality or performance gates. Readiness GPU usage
remains2388/7200seconds; the earlier147seconds stay separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:3ff1c617e4b6d279706e4abce9083b02636536bb2c6f12e6bc4461e3d6f97a88`; readback verified. Previous attempts retained.
