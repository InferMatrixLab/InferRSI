# Explicit startup authorization and stable output collection verified

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**Fixed trusted diagnostic checks passed; campaign, model quality and E2E remain INCONCLUSIVE.**

CPU2014 completed0:0 in114seconds on4CPUs/zeroGPUs; allocation released.
The actual registered Python exposes neither pidfd API, but the ABI-checked raw
Linux bindings opened stable descriptors, sent the trusted child SIGKILL, and
observed that child's exit. Capability evidence was bound to the same job,
source, Python binary and kernel before any bubblewrap launch.

All11 fixed modes completed. The valid token admitted only the gate check;
EOF, short, wrong and held-open inputs returned23 with no stdout and the rejection
marker. Killing the launcher before setup release also produced no stdout and
the rejection marker, closing CPU2012's observed EOF path. Resource checks and
synthetic evaluation then ran with explicit authorization. Normal exit, timeout
and launcher death each confirmed namespace PID1 and two registered descendants
exited. Every case confirmed launcher exit and stable final output hashes that
match the collected archive, with no forced fallback cleanup or cleanup errors.

All17 finite resource checks passed with the existing UID task limit16:11 forks
were created before EAGAIN, and11 threads before RuntimeError. The latter's
kernel cause remains unclassified. Limits and the narrow IPC filter survived a
fresh interpreter; readonly /dev remained readable, and file/address-space/CPU
rejections behaved as expected. These observations do not establish an aggregate
16GiB hard memory cap, exhaustive syscall confinement or production qualification.

The pinned full EvalPlus API produced the four expected handwritten pairs:
correct pass/pass, plus-only error pass/fail, exception fail/fail, and input timeout
fail/fail. The evaluator call took11.390425316989422seconds and reported zero live
children afterward. Exact serialized result bytes are retained and hash-bound to
the parsed result. These are synthetic control scores, not HumanEval+ model scores.

All10 postflight checks passed. The25,241-entry readonly inventory is identical
before/after, with97packages and43 checked evaluator Python sources; relative to
the prior benign reference, only the explicitly changed probe differs. Actual
sources match the independently reviewed proposal. The raw archive and private
PID/namespace identities remain retained; public records omit those identifiers.

The failed local exclusive-file fixture and the review-rejected stability logic
remain preserved. Independent review identified that a live launcher could still
write after namespace init exit; the repaired implementation now requires both
writers to exit, and stops further cases on incomplete cleanup. CPU2012's actual
failure and late payload evidence remain unchanged in their original records.

No heldout task, model-generated program, GPU or measured E2E change occurred.
Production executor integration and qualification, complete protocol freeze,
owner-confirmed statistics/retrieval gates and formal paired runs remain pending.
Readiness usage remains2388/7200GPUseconds; initial147seconds remain separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:c57741dffc71bca7dd018bf3fa17dd760e4b52acb9665a7ea61cbc710eb9faf4`; readback verified.
