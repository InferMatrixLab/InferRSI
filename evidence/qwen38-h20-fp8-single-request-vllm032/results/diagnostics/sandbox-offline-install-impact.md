# Offline installation completed before an isolation-capability stop

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for evaluator/campaign acceptance. CPU1998 ended FAILED1:0.**

The changed transport route made concrete progress: the complete96-wheel
precheck succeeded in the actual CPU allocation, all96 locked dependencies were
installed and matched the original5-build/92-runtime locks, then EvalPlus built
from the authenticated source checkout installed as0.1.0.dev1. The97-distribution
audit and UV package-compatibility check passed. This is installation evidence,
not a task-quality or E2E measurement and not a controlled performance comparison
with the earlier network-install timeouts.

The first rootfs inventory then stopped because the selected compute-node
bubblewrap help lacks at least one required isolation option. The existing error
does not identify which option; its identity and the selected binary/version need
a separate observation. Do not infer that missing flag or remove requirements to
make the check pass. Inventory did not reach its later installed-EvalPlus Python
byte comparison, complete bind-set digest, benign probe or postflight checks.
No rootfs/probe artifact or wheel postcheck exists; the96/97 package audits and
precheck do not substitute for those missing stages.

Slurm records FAILED1:0/NonZeroExitCode after100allocated seconds,4CPUs/zeroGPUs;
the allocation is released. The repaired terminal record correctly contains
completed=false, exit_code=1 and job_id1998, matching the nonzero exit marker.
The16GiB request is not claimed as a verified hard memory limit. The fresh
environment and exact executed sources/output witnesses remain retained; earlier
partial environments were not changed. No model or generated code ran.

Independent review before submission covered offline/no-index controls and the
unchanged source/package freeze. Thirteen read-only verifier controls explicitly
used mocked target tags locally; the actual1998 precheck separately confirms all
96wheels on the compute interpreter. A benign probe remains required before the
conditional synthetic evaluator diagnostic. There is no new GPU use or measured
E2E gain; readiness remains2388/7200GPU-seconds, earlier147separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:3d9b1683e3ccea24b60085e290251b9093a40f74ec5e517213d79dc0430c6ad5`; readback verified, all earlier attempts retained.
