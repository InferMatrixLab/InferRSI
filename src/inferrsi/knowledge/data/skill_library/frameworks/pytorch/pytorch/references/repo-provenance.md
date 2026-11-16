# Repository provenance and refresh contract

- Canonical source: [https://github.com/pytorch/pytorch](https://github.com/pytorch/pytorch).
- Source default branch observed: main, resolved 2026-11-02.
- Immutable source commit: `9a90a4fefcaafa63ac984621963a6fcc66aee68c`.
- Source package identity: `torch`, version.txt `2.16.0a0`, Python >=3.11.
- Source checkout: shallow, no populated submodules; tracked content clean after
  Windows long-path checkout repair. `git diff-index --name-only HEAD` returned
  no tracked changes. Source builds were not attempted.
- Inspection package: separately installed CPU release `torch 2.15.0+cpu`,
  build git identity `d0f2af8b66b20da4baa50644c0cd3f887a2eae2e`, Python 3.12.6,
  NumPy 2.5.4. Pip dependency check, isolated import/signature inspection and one
  CPU add were preparation checks, not native tests of this source commit.
- Required accelerator/backend qualification: **BLOCKED_REQUIRED_BACKEND** for
  NVIDIA CUDA/graphs/fused attention/NCCL, ROCm, macOS MPS, XPU and unprovided
  external backends. Full native source build, C++/CUDA/SYCL extension builds,
  multi-device/multi-node, ONNX consumer and mobile/AOTI deployment are not_run.
- Knowledge state: source-derived candidate. Empirical efficacy: not_run.

The [readset](source-readset.json) records exact inspected spans, immutable Git
blob OIDs/SHA-256 values and inspected checkout SHA-256 values separately.
CRLF checkout bytes are not represented as upstream blob hashes. Normalized
line comparison establishes each inspected checkout file matches the pinned
blob's text. Complete tracked tree inventory and verification records live in
the contribution's external fixtures, not this runtime graph.

Use [directory coverage](source-directory-coverage.md) to find ownership and
exclusions. Inventory counts establish discovery breadth, not every-line reading
or execution. [Script map](source-script-map.md) records runtime replacements;
no helper requires the inspection checkout or its private environment.

Refresh the affected route when source identity, package version, public API,
compiler/build metadata, device stack, serialization trust boundary or source
evidence changes. Keep source revision, tested wheel and downstream measured
stack separate. Existing focused DCP/host/compiler owners retain their original
pins. Latest PyTorch and latest TorchNPU commits are independent snapshots, not
an automatically compatible pair.
