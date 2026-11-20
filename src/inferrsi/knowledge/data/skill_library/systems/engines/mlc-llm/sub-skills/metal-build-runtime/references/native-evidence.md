# Exact native discriminators, not name-derived claims

The selected [MLC target test](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/tests/python/support/test_auto_target.py)
tests WebGPU subgroup toggling and LLVM unchanged, not Apple SDK/suffix/prefix
behavior. MLC's broad [model compile loop](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/tests/python/integration/test_model_compile.py)
is compilation across many models/quantizations, not runtime parity.

Pinned [TVM Metal tests](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/tests/python/codegen/test_target_codegen_metal.py)
contain different assertion layers:

- simdgroup-buffer/source-scope and selected stack-allocation rejection cases
  inspect generated source/errors. They still require native TVM, but do not
  by themselves establish GPU execution.
- test_export_load_with_fallback (lines 299–317) forces fallback, builds and
  exports lib.so. Despite its name it does **not** load or execute the result.
- test_metal_compile_callback_source_passthrough is GPU-marked; it returns an
  explicit source/metal pair, runs a 1024-element add-one kernel, synchronizes
  and checks readback. Missing Metal skips cannot count as numerical success.
- test_pointer_byte_offsets_execute_in_threadgroup_memory checks generated
  scope and actually executes/readbacks selected outputs; source-scope-only
  assertions are a different test.
- mixed-format callback rejection tests a compile error, not successful dispatch,
  even where marked as a GPU case.

No original source tests or compiler/native calls are performed by the bundled
helper. Actual evidence needs matched MLC/TVM/FFI build, SDK/OS/device/artifacts,
exact selected tests and nonzero counts/skips, real runnable/load/route/stream
observations and numerical results. Original fixtures are unbundled; a portable
helper must not silently fetch/build dependencies or execute broad source loops.

Native cache continuation/rollback/sliding, allocator pressure, model quality
and service performance remain independent requirements. No export, source hash,
static declaration or skipped test clears BLOCKED_REQUIRED_BACKEND.
