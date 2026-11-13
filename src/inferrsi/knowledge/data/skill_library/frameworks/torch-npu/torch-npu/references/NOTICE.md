# Attribution and retained notices

This operating graph contains original English operational paraphrases and
small adapted public-API examples grounded in Ascend/pytorch (TorchNPU) and the
pinned Ascend/op-plugin submodule. It does not redistribute compiled libraries,
device kernels or complete upstream test/build trees. Modifications include
workflow restructuring, isolated inputs, finite tiny examples, explicit opt-in
execution and sanitized diagnostics.

TorchNPU source includes Huawei and inherited PyTorch/Caffe2 contributor
attribution. op-plugin source includes Huawei and inherited contributor notices.
Retain the original terms with adapted material:

- [TorchNPU source LICENSE](licenses/torch-npu-LICENSE.txt)
- [TorchNPU documentation LICENSE, CC BY 4.0](licenses/torch-npu-docs-LICENSE.txt)
- [op-plugin LICENSE](licenses/op-plugin-LICENSE.txt)
- [TorchNPU third-party notices](licenses/torch-npu-THIRD-PARTY.txt)
- [op-plugin third-party notices](licenses/op-plugin-THIRD-PARTY.txt)

These files are copied byte-for-byte from immutable Git blobs; the
[retained-license ledger](licenses/source-identities.json) records their
identities and digests. The upstream documentation is
adapted and reorganized rather than reproduced as a guide dump. Source URLs and
revisions are in [repo provenance](repo-provenance.md).

The AREX exact-commit GitHub license resolver returned `NOASSERTION` for
Ascend/pytorch. Every native local-skill sidecar preserves that source value.
This metadata result does not erase the retained licenses or make a legal
conclusion about licensing. InferRSI's local profile owns structured fields in
metadata sidecars; the external verification adapter restores AREX frontmatter
only in a scratch projection. No DisCo managed import is claimed.
