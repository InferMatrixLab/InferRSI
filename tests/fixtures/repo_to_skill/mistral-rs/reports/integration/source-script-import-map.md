# Source artifacts and safe support

| Artifact | Decision / owner | Reason and bundled replacement |
| --- | --- | --- |
| Metal backend/mod.rs and paged_attention.rs guards | adapt / decode-contract | Explicit-input shape/scale guard helper, not GPU or allocation simulation |
| paged_prefill.rs metadata/workspace functions | adapt / prefill-contract | Bounded declarations/formulas; no actual tensor or numerical attention implementation |
| kernels/mod.rs paged_decode_warmup_shapes | adapt / qualification | Fixed source boundary enumeration, not selector, benchmark or GPU simulator |
| examples/python/paged_attention.py | reference-only / root | Loads named model through installed native bindings; replaced by local contract guidance, not executed |
| Source test commands | external verification report only | Unbundled native fixtures/toolchain dependencies, no runtime checkout-dependent command instructions |
| Remote installers, broad workspace/benchmark/tool scripts | unselected | Host/dependency/network/model/tool/service side effects outside this source slice |
