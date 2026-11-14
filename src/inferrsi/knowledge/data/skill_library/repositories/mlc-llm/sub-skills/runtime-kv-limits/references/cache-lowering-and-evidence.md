# Generic cache IR, target lowering and native evidence

The [dispatch pass](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/compiler_pass/dispatch_kv_cache_creation.py)
returns unchanged when create_paged_kv_cache is absent. Otherwise it extracts a
specific Relax call to mlc.create_paged_kv_cache_generic with 18 positional
arguments. Capacity/prefill/page/sliding shapes, layer partition, head geometry,
RoPE, disaggregation and dtype are separate inputs. The shape tuple has five or
six entries; the inspected optional layer sliding size defaults to 1024. These
are IR construction contracts, not a public Python cache allocation API.

The pass attaches selected layer/head metadata and constructs a
TIRPagedKVCache with the selected target. Its implementation belongs to the
pinned TVM dependency. Optional FlashInfer requires its enable flag, **CUDA**,
F16/BF16 and inline-RoPE geometry compatibility; optional-construction failures
log fallback to TIR. A Metal target is not evidence of CUDA FlashInfer execution.
An IR symbol or attached dimensions cannot authenticate actual cache contents,
physical block identity, append/fork/sliding correctness or runtime dispatch.

The [paged-cache source test](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/tests/python/model/test_kv_cache.py)
compares generic exported IR structurally with an expected module. It is not a
Metal numerical test or proof of the dispatch pass's runtime behavior. The
[compile integration test](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/tests/python/integration/test_model_compile.py)
enumerates many models and quantizations, including Metal dylib and iOS tar
outputs. Compilation is not cache/model parity or serving acceptance; the broad
loop is not a small default diagnostic.

No original C++/Python/TVM test is executed by the bundled helper. Original
codegen/IR tests still require a prepared native TVM/FFI stack. Actual matched
Apple compilation/load/dispatch/synchronization, cache continuation/rollback/
sliding and pressure tests require separate native evidence with exact inputs,
executed counts/skips and actual route observations. A skipped backend case or a
host reference alone does not replace this. Source-local constants/tolerances
are not portable performance or quality gates.
