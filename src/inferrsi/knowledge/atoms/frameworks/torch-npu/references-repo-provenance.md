# Repository provenance

- Source repository: [Ascend/pytorch](https://github.com/Ascend/pytorch/tree/046934140b96836c3fcef14d0f39ae54dc0a06bf).
- Default branch at acquisition: `master`; immutable commit `046934140b96836c3fcef14d0f39ae54dc0a06bf`.
- Clean shallow snapshot; no native source build or accelerator execution.
- Package identity: `torch-npu` / Python `torch_npu`; a multi-version development
  source, not a verified installed distribution. Build lines are 2.13–2.16;
  released-package compatibility rows remain distinct.
- Additional source: [Ascend/op-plugin](https://github.com/Ascend/op-plugin/tree/ad946817034b3270e309c81c54f0ee808d0b62cb)
  at the exact parent gitlink `ad946817034b3270e309c81c54f0ee808d0b62cb`. The declared submodule remote is
  GitCode; the public GitHub mirror supplied the same commit object.
- Source integrity and actual reading: [source manifest](source-manifest.json).
  Git blob bytes and inspected checkout bytes have separate hashes because
  Windows checkout line endings can differ. Span hashes use UTF-8 text joined
  with LF without a trailing newline; all recorded spans match the Git text.
- Reuse existing allocator owners at their separate source pin; no automatic
  forward-port or runtime equivalence between source revisions is asserted.
- This is an InferRSI candidate contribution. AREX supplied construction and
  verification procedures, not a device result or DisCo managed import.

## Every declared submodule

| Path | Exact gitlink | Evidence state |
|---|---|---|
| `third_party/Tensorpipe` | `29233737f695c3cfca9fee94ca11fd8f8e0ea08b` | not fetched; boundary only |
| `third_party/acl_src/ge` | `a74342b574f03ffe45e059c1a0fa74e50ccf5733` | not fetched; boundary only |
| `third_party/acl_src/graph-autofusion` | `ea356604ae2ba09aab0e53c866a7057c7d35115e` | not fetched; boundary only |
| `third_party/acl_src/runtime` | `c71314c12cefba3011823bd1786012858f310c1d` | not fetched; boundary only |
| `third_party/dvm/dvm` | `2b3f462f116e491574ccc49cda1ae1a01e58cfe6` | not fetched; boundary only |
| `third_party/fmt` | `123913715afeb8a437e6388b4473fcc4753e1c9a` | not fetched; boundary only |
| `third_party/googletest` | `58d77fa8070e8cec2dc1ed015d66b454c8d78850` | not fetched; boundary only |
| `third_party/nlohmann` | `87cda1d6646592ac5866dc703c8e1839046a6806` | not fetched; boundary only |
| `third_party/op-plugin` | `ad946817034b3270e309c81c54f0ee808d0b62cb` | pinned public mirror fetched; bounded representative readset |
| `third_party/torch-mlir` | `155680c08e08bff6d2e6883415e3f5a1b474d96e` | not fetched; boundary only |
| `third_party/torchair/torchair` | `80dd0c68b5fe6606e0578a8c0a5971957d563813` | not fetched; boundary only |

op-plugin evidence covers one real ACLNN/ACL Add adapter, version generation
and extension registration; it does not cover every operator. The remaining
submodules are pinned but not inspected. CANN runtime/GE/autofusion, TorchAir,
DVM, Tensorpipe, compiler toolchains and proprietary device kernels require
their own source/runtime qualification. Bundled parent headers are interface
evidence, not a substitute for those implementations.

## Verification boundary

Linux, CANN, driver and Ascend device access are required for the selected
device routes. HCCL requires multiple participating ranks/devices. Local
standard-library/helper/static checks cannot clear these
`BLOCKED_REQUIRED_BACKEND` gates. Optional compiler support must be observed
for the selected route. No installed TorchNPU API signatures or hardware
performance were measured. Preserve candidate/not-run state when reusing this
graph until the caller supplies actual execution evidence.
