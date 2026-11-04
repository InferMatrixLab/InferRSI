# Reviewed-wheel dependency resolution completed

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — a dependency freeze proposal, not campaign activation.**

The v3 resolver uses the two authenticated wheels from CPU1986 while keeping
source builds disabled. It clears inherited resolver settings and uses only
explicit PyPI and the reviewed local wheelhouse. The fixed EvalPlus source and
official declarations are unchanged. The original draft rejection and CPU1985
no-wheel failure remain retained; neither was overwritten or relabeled.

CPU1991 completed0:0 after681 allocated seconds,4CPUs/zeroGPUs, and allocation
release was checked. During the long resolution, a read-only job step observed
new package metadata cache entries; the live job was retained instead of being
resubmitted. Resolution eventually produced92 pinned runtime packages and the
complete dependency freeze proposal. The evaluator environment was not created,
and no package installation, task data, model, generated solution or full
evaluator execution occurred.

Parent static audit authenticates all15 freeze entries, the unchanged source and
declarations, all19 direct requirement specifiers and shared build/runtime package
versions. Each lock entry has a unique exact pin and SHA256 hashes; there are no
direct URL requirements or hidden index directives. Both local wheel entries bind
only their previously reviewed exact hashes. No torch, vLLM or FlashInfer package
is selected. The dependency lock and reviewed resolver script are retained under
plan/ and patch/diagnostics/; sandbox-resolve-1991.json records complete identities.

These checks authenticate the proposed inputs, not an installed runtime. Actual
dependency closure, pinned evaluator installation, imports, readonly runtime
identity, isolation and cleanup remain to be checked. The exact source/locks and
separate install/probe script require independent review before that next step.
All generated-code executor and full quality qualification remains open.

No measured E2E performance effect or GPU budget change: readiness remains
2388/7200GPU-seconds, with the earlier147seconds separate. Statistical/retrieval
policy confirmation and complete campaign freeze are still pending.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:677ac8f26a6c55a4c3979f7c5a0423929ec7331bc6ebb79e35f9db1a6aed9926`; readback verified and earlier attempts retained.
