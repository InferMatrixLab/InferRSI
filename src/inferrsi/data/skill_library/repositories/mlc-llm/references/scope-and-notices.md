# Scope and source-specific notices

| Surface | Selected depth / boundary |
| --- | --- |
| Artifact metadata | Actual canonical task/parameter IDs, executor/adapters/roles and parameter resources; not general Pydantic normalization or physical weights/exports |
| Apple target and TVM Metal | Selected build/SDK/prefix, codegen/module/format, native storage/copy/stream consumers and test assertions; not an exhaustive compiler/scheduling tutorial |
| KV configuration | Actual compile/runtime clamp/minimum, workspace inputs and target cache lowering; not full scheduler/admission/prefix/allocator analysis |
| Models/tokenization/quantization | Narrow public ABI/caller context only; no model catalog, weight conversion, tokenizer/template/multimodal quality qualification |
| RNN/speculation/disaggregation/CUDA/services | Named adjacent engine surfaces, not complete operating recipes or transferable Metal parity/performance claims |

The artifact manifest is opt-in and first consumed by WebLLM; current native
serving ignores that contract. Native modules, actual cache behavior, model
quality and service performance need their own supported consumer and evidence.
A fallback module can serialize without being runnable, and an automatic
estimate is not measured free memory or allocation success.

The primary [Apache LICENSE](../LICENSE) and [MLC NOTICE](mlc-notice.md) are
retained unchanged. The pinned TVM fork has its own [LICENSE](tvm-license.md)
including bundled-component listings and [NOTICE](tvm-notice.md), also retained
unchanged. Original names/hashes are in the [source ledger](source-identity.json).
Their owners/bytes are not interchangeable. No vendor tree, model/weight,
binary metallib or native artifact is copied into this portable graph.

New helpers retain Apache/source attribution. Dependency, model/tokenizer and
prebuilt-artifact rights are separate. `NO_LICENSE` is an unavailable machine
SPDX marker, **not** a statement of legal absence; independently retained source
licenses/notices remain authoritative for this source slice.

Original examples/tests may require native packages, toolchains, models or
external assets. They are references here, not bundled runtime dependencies or
permission to install/fetch/execute them. Use synthetic/anonymized helper input,
not private paths, prompts, cache contents or credentials. Source-only and
helper outcomes do not authenticate native observations or certify fit/quality.
