# Task-local bubblewrap build completed; isolation still untested

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for isolation, evaluator qualification and E2E.**

CPU2001 completed0:0 in14allocated seconds with4CPUs/zeroGPUs; allocation released.
It built and installed only the reviewed static libcap2.78 dependency, installed
exact offline Meson1.12.1/Ninja1.13.2, then compiled bubblewrap0.13.1 and test-utils.
All26pure utility subtests passed. The installed binary is not setuid/setgid; all
eight required option names are present, and all nine frozen inputs passed both
preflight and postflight checks. Full installed binary/static library bytes are
retained privately and independently comparable with their reported hashes.

Ninja's build-graph-expanded link command selects the task-local libcap archive;
ELF NEEDED contains only libc.so.6. This is not an independently collected execution
trace. Upstream _makenames executed as a trusted build generator; libcap's constructor
queries capability bounds during linked-tool startup. Neither demonstrates isolation.
The official archive checksum matched; PGP signature was not verified. Optional
libselinux was unavailable and the actual build did not enable it. No shared-libcap
installation, ldconfig, Go/PAM/program/libcap-test path was selected.

CPU2000's missing-development-dependency failure and both rejected v1 wrappers
remain preserved. Existing evaluator packages/locks were unchanged; no namespace
probe, evaluator, task data, generated code or model ran in2001. The next step is
the unchanged trusted benign inventory/probe using the new hash-bound binary.
Version/help and pure utility tests do not qualify that executor or establish an
E2E gain. Readiness remains2388/7200GPUseconds, initial147separate.

Full compiler/scheduler/Meson logs remain private; Meson's test log automatically
contains environment fields. Only the required non-sensitive utility stdout is
published here. Source archives and wheels remain external to the public evidence;
the copied input checksum file records identities, not local inventory verification.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:c2f15aafafc508b617f7ec226eaad516e5ffe0ac08213ad07bc9061af50ae7b2`; readback verified.
