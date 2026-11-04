# Slow cluster HTTP reads isolated from payload writes

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — a partial transport diagnosis, not sandbox or model acceptance.**

CPU1996 ended FAILED1:0 after300allocated seconds:1CPU requested,2CPUs actually
allocated, zeroGPUs, allocation released. The reviewed helper deadline stopped
the network phase after approximately299seconds with5242880bytes received from
the fixed official wheel URL. The requested8388608-byte prefix was incomplete;
filesystem work was explicitly skipped because the overall deadline was exhausted.
The helper preserved partial byte counts, operation durations and TimeoutError,
then returned1. It did not misclassify this partial run as completion.

The same helper's operator-recorded local control read8388608bytes in about
0.699seconds, without writing payload bytes. Its retained report identifies the
local platform, source/policy hashes and60-second bound; the execution context is
not an independent invocation receipt. Both observed prefixes were subsequently
matched against the complete, authenticated local wheel bytes. Different hosts
and runtime/network paths remain a limitation. This is a diagnostic of this
HTTP read path, not a UV benchmark or controlled physical network throughput test.

The slow cluster read occurred without payload disk writes. It therefore provides
evidence of a slow download path independent of extraction/writes for this sample.
It does not identify the responsible network hop or prove all installer delay has
that cause. Because the filesystem phase never ran, storage latency remains
unmeasured. A future retry should address transport while retaining those limits.

Two complete wheels were subsequently prefetched locally, without installation,
import or upload: pyarrow26.0.0 LinuxCPython3.12 and google-api-python-client2.201.0.
Each exact URL, byte count and SHA256 matches official PyPI metadata and the
retained92-package dependency lock. Their manifest is retained. Only these full,
authenticated artifacts may be considered for a later separately reviewed local
installation path; the incomplete prefix is never treated as an installable wheel.
No package set or model runtime has changed.

Independent review before execution rejected two helper revisions: one lost
partial observations and could mark a skipped phase complete; the next had a
late-timeout completion-state edge. The final helper clears completion on all
caught failures and requires both phases. Thirteen synthetic controls, Ruff and
shell checks passed. Rejected implementations and all control records remain in
the KnowledgeStore. An initial read-only status query used a nonmatching job ID;
it was excluded and corrected against the actual submission receipt. No work or
process operation was performed under that unrelated allocation.

The complete executed helper/wrapper/policy and control are retained together in
patch/diagnostics/sandbox-transport-v1; raw scheduler/log/output archives are
private and hash-bound in the report. No generated code, evaluator, model or GPU
ran. This changes neither E2E service evidence nor quality acceptance. GPU
readiness remains2388/7200seconds, with the earlier147seconds separate. Full
sandbox qualification and campaign freeze remain pending.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:235fe0b6a64b847569c036325f51b298fb33794041a7c07512cf124fd3151f88`; readback verified, previous attempts retained.
