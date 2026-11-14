# Evidence ledger and reading boundary

All findings below are source facts or operational interpretations at the
immutable revisions in [repo provenance](repo-provenance.md). None is a device
execution result. The [machine readset](source-manifest.json) records each
inspected file's Git blob OID/SHA-256, checkout SHA-256 and exact inspected spans.
Enumeration alone is not semantic inspection. Repeated slices are consolidated;
no full-file read is inferred from a fetched file or hash.

| ID | Mechanism and actual source evidence | Operating consequence |
|---|---|---|
| F1 | `COMPATIBILITY.en.md`, `version.txt`, `tools/setup_helpers/version.py`, `setup.py` | Distinguish released product/package matrix, supported development build lines and installed-torch-derived build version. |
| F2 | `README.md`; source-build guide; `generate_code.sh`; `setup.py` | NPU driver/CANN/Linux requirements; metadata/build/codegen can mutate source/submodule directories. |
| F3 | `torch_npu/__init__.py`; `_init/core/module_loader.py`; `_init/registry/registry_manager.py` | Ordered initialization and extension child prerequisites; op-plugin/Meta registration side effects. |
| F4 | `_init/registry/backend.py`; `csrc/core/npu/NPUHooksInterface.cpp` | Rename PrivateUse1, install methods/module, preserve lazy init, pointer ownership and base-format resize guard. |
| F5 | `csrc/aten/VariableFallbackKernel.cpp`; `csrc/framework/utils/CpuFallbackUtils.h`; fallback-control test | Distinct dense CPU fallback, fallback disable guard, sparse failure and autograd path. |
| F6 | `torchnpugen/gen_backend_stubs.py`; pinned op-plugin configuration and `gen_op_plugin_functions.py` | Version-specific schema/implementation filtering and generation contract. |
| F7 | Pinned op-plugin `AddKernelNpuOpApi.cpp`, `AddKernelNpu.cpp`; full extension registration/example | Real result inference, alpha/overlap/scalar checks, ACLNN/legacy boundary and independent NPU/autograd/Meta bindings. |
| F8 | `csrc/core/npu/NPUCachingAllocator.cpp`: free, recordStream, event insertion/reaping and release blocks | Free-requested versus reusable versus returned-to-runtime memory; capture deferral. |
| F9 | `csrc/core/npu/CachingHostAllocator.cpp`: record_event pointer/context checks | Pinned lifetime tracking applies to known allocations; external registration needs its own owner contract. |
| F10 | `csrc/core/npu/NPUEvent.cpp`, `NPUStream.cpp`; `npu/streams.py`; stream tests | Thread-local current stream; host queue versus device completion; device binding and future-only waits. |
| F11 | `csrc/core/npu/NPUGraph.cpp`; `npu/graphs.py`; native multi-stream capture test | Non-default managed stream, queue/pinned allocator guards, private pools/RNG and stable-input replay. |
| F12 | `dynamo/__init__.py`; `_init/registry/dynamo.py`; import-contract test | Lazy entry points and `npu` backend's possible eager fallback when TorchAir absent. |
| F13 | `_inductor/__init__.py` selected loader spans | Distinct NPU backend dependencies/patches; DVM thread restriction and deprecated MLIR boundary. |
| F14 | `fxrt/README.md` | Optional in-wheel inference backend and view/debug contracts; executor internals are inventoried, not exhaustively read. |
| F15 | `_init/registry/distributed.py` | HCCL/LCCL device registration and process-group options. |
| F16 | `csrc/distributed/ProcessGroupHCCL.cpp`: syncStreams, collective and allreduce | Producer event, communication stream, lifetime protection and operation-specific postprocessing. |
| F17 | Same file: WorkHCCL synchronizeInternal/wait and collective future/end events | Work consumer-stream dependency versus optional host blocking; host future is not device completion. |
| F18 | `csrc/aten/AutoCastOps.cpp`; `npu/amp/autocast_mode.py` | Operator autocast policies, unsafe BCE guard and deprecated custom-autograd wrappers. |
| F19 | `npu/amp/grad_scaler.py`; native AMP tests; `optim/__init__.py` | Dynamic/static scale, per-optimizer state, nonfinite checks, distributed overflow and fused optimizer boundary. |
| F20 | `profiler/profiler.py`; `profiler/scheduler.py` | Schedule transitions, timeline prerequisites, output handling and collection/parse separation. |
| F21 | `csrc/profiler/profiler_mgr.cpp`; `npu/_sanitizer.py`; launch-blocking docs | CANN collector feature gates, sanitizer callback routing and diagnostic-mode effects. |
| F22 | `contrib/transfer_to_npu.py`; `onnx/__init__.py`; `utils/serialization.py`; `distributed/tensor/__init__.py` | Bounded migration/export/state/distributed registration evidence; detailed implementation limits named in support workflows. |

Source facts such as “the native test asserts X” do not mean that test passed
here. Proposed operating checks and bundled public-API examples remain separate
from upstream native execution. The older focused allocator owners retain source
pin `67511c53cd4c88014f6123de7097677e60e85faa`; no result is transferred between pins.
