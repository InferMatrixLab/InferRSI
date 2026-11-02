# Coverage and verification at author freeze

Source discovery covers the full22,762-entry tracked tree;68 selected source
files have exact inspected spans and distinct immutable-blob and checkout
digests.52 runtime files contain root/eightchild routing, substantive procedures,
recovery, metadata, provenance and nine bounded helpers.18 usability prompts
cover root, all children, support failures and two integrated scenarios.

| Route | Executed evidence after graph integration | Remaining boundary |
| --- | --- | --- |
| installation-and-build | Installed identity/availability; source-pinned setup.py --help expected deprecation rejection | No full source build, native extension/toolkit or accelerator qualification |
| tensor-dispatch-autograd | Bundled CPU view/gradient/gradcheck/sparse duplicate diagnostic | Not all operators/layouts/devices or source2.16 native tests |
| training-and-data | Bundled finite CPU data/model/update and evaluation diagnostic | No model convergence, CUDA AMP/fused SDPA or multiprocess loader qualification |
| compiler-and-export | Bundled dynamic export/archive/valid and invalid range checks plus Dynamo eager backend | No Inductor target-kernel/AOTI/ONNX consumer qualification |
| memory-streams-and-graphs | Bundled explicit CUDA absence returned BLOCKED_REQUIRED_BACKEND | Actual CUDA allocator/stream/graph lifetime checks remain blocked |
| distributed-and-checkpoint | Self-created weights-only/mmap CPU state roundtrip | Two-rank installed Gloo standalone NATIVE_FAIL for missing libuv, unchanged with process-local USE_LIBUV=0; NCCL/FSDP2/DCP reshard/runtime unqualified |
| profiling-and-debugging | Bundled finite CPU schedule produced one active trace cycle | No accelerator activity/CUPTI or workload/service performance claim |
| custom-operators-and-extension | Bundled CPU custom-op values, gradcheck and all requested opcheck registrations | No C++/CUDA/SYCL build or target kernel/stream qualification |

`author-runtime-checks.json` retains exact installed versions, script digests,
arguments, exit codes and redacted observations. The initial export negative
failure is retained in `author-runtime-checks-initial.json`; repair accepts the
actual expected AssertionError only with the expected upper-bound8 and reraises
unrelated failures. The affected case then passed. Installed/adapted helper
execution is not represented as original pinned-source native testing.

Author static checks passed: AST, metadata, local links, nine --help checks,
three invalid-argument checks and privacy scan. Ruff passed for the whole owned
runtime subtree. Sixteen assertions in four hard cases passed author direct
content inspection with retained anchors; this is neither independent review nor
measured agent efficacy. Root owns fresh-agent/source review and packaged tests.

Canonical runtime bytes were already LF during execution. External reports/cases
were normalized to LF before freeze; source checkout bytes were not changed.
Immutable blob hash versus inspected CRLF checkout hash remains explicit.
