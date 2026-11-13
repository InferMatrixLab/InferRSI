# Capability inventory

This is a complete tracked-tree discovery pass with bounded substantive
readsets, not a claim that every file was read. The exact source and read spans
are in the [source manifest](source-manifest.json). Every tracked file and every
directory, including deeper levels, was classified in the external construction
inventory; this runtime index exposes each top-two-level directory and its owner.
Counts include descendant Git entries and are not additive across ancestor rows.

| Source surface | Capability | Depth and boundary |
|---|---|---|
| `torch_npu/_init, _compat, npu and csrc/core hooks` | PrivateUse1/lazy runtime/compatibility | substantive selected registration, hooks, events and graph spans |
| `torch_npu/csrc/aten, framework; torchnpugen; op-plugin` | Operator schema/dispatch/adapter generation | substantive selected generator, fallback and Add/extension mechanisms |
| `torch_npu/csrc/core/npu; npu/memory.py and streams` | Memory, streams, events and private pools | substantive allocator/event/stream paths; public memory API inventoried |
| `dynamo, _inductor, _compiler, fxrt` | Compilation and graph execution | selected loaders and capture internals; FXRT IR/executor and long-tail compiler passes inventoried |
| `distributed Python/C++; symmetric memory; multiprocessing/ipc` | HCCL, sharding, RPC, pipeline and IPC | substantive HCCL process-group path; higher-level/transport contracts bounded or inventoried |
| `npu/amp; optim; contrib; custom_dtype; utils/hif8_tensor` | Training, precision, optimizers and modules | substantive AMP and export lists; optimizer algorithms/quantized modules inventoried |
| `profiler; csrc/profiler, toolkit, logging, sanitizer; asd` | Profiling, memory traces, faults and diagnostics | selected collection/scheduler/CANN bridge/sanitizer spans; fault recovery inventoried |
| `onnx, jit, utils/serialization, utils/dlpack, storage` | Export, persistence and interop | selected registration/remap boundary; specialized serialization/export/interop implementations inventoried |
| `docs/en and docs/zh; README/compatibility/support/security/contribution` | Documentation and compatibility | selected primary guides; API catalogs discovered; Chinese duplicates not copied |
| `test, examples, benchmarks` | Behavior assertions and deployment examples | selected native candidates read; no benchmark/model download executed |
| `tools, ci, .ci, .github, .gitcode, cmake, docker, top-level build files` | Build, generation, CI and packaging | selected setup/codegen inspected; environment-mutating automation reference-only |
| `third_party and all 11 gitlinks` | External libraries/compiler/runtime boundaries | all gitlinks inventoried; only pinned op-plugin fetched and partly inspected |

Primary workflows are reachable through the eight root routes. Less common
surfaces have explicit [support contracts](support-workflows.md), including
their missing implementation/runtime evidence. Source presence alone is not
full coverage or a supported API claim.

| Tracked directory | Descendant entries | Route owner | Inspection state |
|---|---|---|---|
| `.ci` | 16 | installation-and-compatibility | inventoried-only |
| `.ci/docker` | 16 | installation-and-compatibility | inventoried-only |
| `.devcontainer` | 1 | installation-and-compatibility | inventoried-only |
| `.gitcode` | 42 | installation-and-compatibility | inventoried-only |
| `.gitcode/config` | 5 | installation-and-compatibility | inventoried-only |
| `.gitcode/scripts` | 14 | installation-and-compatibility | inventoried-only |
| `.gitcode/workflows` | 22 | installation-and-compatibility | inventoried-only |
| `.github` | 12 | installation-and-compatibility | inventoried-only |
| `.github/actions` | 1 | installation-and-compatibility | inventoried-only |
| `.github/workflows` | 11 | installation-and-compatibility | inventoried-only |
| `benchmarks` | 61 | installation-and-compatibility | inventoried-only |
| `benchmarks/inference` | 7 | installation-and-compatibility | inventoried-only |
| `benchmarks/llm` | 32 | installation-and-compatibility | inventoried-only |
| `benchmarks/torchbench` | 14 | installation-and-compatibility | inventoried-only |
| `benchmarks/v1sparsedrive` | 8 | installation-and-compatibility | inventoried-only |
| `ci` | 19 | installation-and-compatibility | inventoried-only |
| `ci/access_control` | 12 | installation-and-compatibility | inventoried-only |
| `ci/docker` | 3 | installation-and-compatibility | inventoried-only |
| `cmake` | 1 | installation-and-compatibility | inventoried-only |
| `docker` | 10 | installation-and-compatibility | inventoried-only |
| `docker/devel` | 6 | installation-and-compatibility | inventoried-only |
| `docs` | 1458 | installation-and-compatibility | contains-inspected-spans |
| `docs/en` | 726 | installation-and-compatibility | contains-inspected-spans |
| `docs/zh` | 731 | installation-and-compatibility | inventoried-only |
| `examples` | 32 | installation-and-compatibility | inventoried-only |
| `examples/libtorch_hccl` | 4 | distributed-and-hccl | inventoried-only |
| `examples/libtorch_npu` | 3 | installation-and-compatibility | inventoried-only |
| `examples/libtorch_resnet` | 3 | graph-and-compile | inventoried-only |
| `examples/libtorch_triton_ascend` | 22 | graph-and-compile | inventoried-only |
| `figures` | 14 | installation-and-compatibility | inventoried-only |
| `fxrt` | 595 | graph-and-compile | contains-inspected-spans |
| `fxrt/cmake` | 3 | graph-and-compile | inventoried-only |
| `fxrt/fxrt` | 590 | graph-and-compile | inventoried-only |
| `test` | 984 | installation-and-compatibility | contains-inspected-spans |
| `test/_afd` | 3 | installation-and-compatibility | inventoried-only |
| `test/_inductor` | 139 | graph-and-compile | inventoried-only |
| `test/allocator` | 7 | memory-streams-and-events | inventoried-only |
| `test/autograd` | 11 | installation-and-compatibility | inventoried-only |
| `test/bottleneck_test` | 3 | installation-and-compatibility | inventoried-only |
| `test/contrib` | 28 | training-and-precision | inventoried-only |
| `test/cpp` | 2 | installation-and-compatibility | inventoried-only |
| `test/cpp_extensions` | 19 | operator-development | inventoried-only |
| `test/custom_ops` | 62 | operator-development | inventoried-only |
| `test/distributed` | 172 | distributed-and-hccl | contains-inspected-spans |
| `test/dynamo` | 64 | graph-and-compile | inventoried-only |
| `test/expect` | 2 | installation-and-compatibility | inventoried-only |
| `test/functorch` | 6 | installation-and-compatibility | inventoried-only |
| `test/fx` | 36 | installation-and-compatibility | inventoried-only |
| `test/fxrt` | 2 | graph-and-compile | inventoried-only |
| `test/jit` | 15 | graph-and-compile | inventoried-only |
| `test/nn` | 50 | installation-and-compatibility | inventoried-only |
| `test/npu` | 111 | installation-and-compatibility | contains-inspected-spans |
| `test/onnx` | 12 | graph-and-compile | inventoried-only |
| `test/optim` | 7 | training-and-precision | inventoried-only |
| `test/package` | 1 | installation-and-compatibility | inventoried-only |
| `test/profiler` | 72 | profiling-and-debugging | inventoried-only |
| `test/testing` | 1 | installation-and-compatibility | inventoried-only |
| `test/trans_contiguous` | 13 | installation-and-compatibility | inventoried-only |
| `test/typedStorage` | 1 | installation-and-compatibility | inventoried-only |
| `test/unsupported_test_cases` | 5 | installation-and-compatibility | inventoried-only |
| `test/untypedStorage` | 1 | installation-and-compatibility | inventoried-only |
| `test/utils` | 10 | installation-and-compatibility | inventoried-only |
| `third_party` | 71 | installation-and-compatibility | inventoried-only |
| `third_party/acl` | 45 | installation-and-compatibility | inventoried-only |
| `third_party/acl_src` | 3 | installation-and-compatibility | inventoried-only |
| `third_party/dcmi` | 2 | installation-and-compatibility | inventoried-only |
| `third_party/dlpack` | 1 | installation-and-compatibility | inventoried-only |
| `third_party/dvm` | 2 | installation-and-compatibility | inventoried-only |
| `third_party/hccl` | 3 | installation-and-compatibility | inventoried-only |
| `third_party/mspti` | 3 | installation-and-compatibility | inventoried-only |
| `third_party/mstx` | 1 | installation-and-compatibility | inventoried-only |
| `third_party/shmem` | 2 | installation-and-compatibility | inventoried-only |
| `third_party/torchair` | 3 | installation-and-compatibility | inventoried-only |
| `tools` | 64 | installation-and-compatibility | contains-inspected-spans |
| `tools/compat_check` | 2 | installation-and-compatibility | inventoried-only |
| `tools/flight_recorder` | 9 | installation-and-compatibility | inventoried-only |
| `tools/linter` | 49 | installation-and-compatibility | inventoried-only |
| `tools/setup_helpers` | 3 | installation-and-compatibility | contains-inspected-spans |
| `torch_npu` | 1002 | installation-and-compatibility | contains-inspected-spans |
| `torch_npu/_afd` | 2 | installation-and-compatibility | inventoried-only |
| `torch_npu/_compat` | 8 | privateuse1-and-dispatch | inventoried-only |
| `torch_npu/_compiler` | 1 | graph-and-compile | inventoried-only |
| `torch_npu/_inductor` | 251 | graph-and-compile | contains-inspected-spans |
| `torch_npu/_init` | 22 | privateuse1-and-dispatch | contains-inspected-spans |
| `torch_npu/_logging` | 2 | profiling-and-debugging | inventoried-only |
| `torch_npu/asd` | 5 | profiling-and-debugging | inventoried-only |
| `torch_npu/contrib` | 37 | training-and-precision | contains-inspected-spans |
| `torch_npu/csrc` | 428 | installation-and-compatibility | contains-inspected-spans |
| `torch_npu/distributed` | 27 | distributed-and-hccl | contains-inspected-spans |
| `torch_npu/dynamo` | 3 | graph-and-compile | contains-inspected-spans |
| `torch_npu/jit` | 4 | graph-and-compile | inventoried-only |
| `torch_npu/multiprocessing` | 1 | distributed-and-hccl | inventoried-only |
| `torch_npu/npu` | 42 | installation-and-compatibility | contains-inspected-spans |
| `torch_npu/onnx` | 3 | graph-and-compile | contains-inspected-spans |
| `torch_npu/optim` | 12 | training-and-precision | contains-inspected-spans |
| `torch_npu/profiler` | 111 | profiling-and-debugging | contains-inspected-spans |
| `torch_npu/testing` | 9 | installation-and-compatibility | inventoried-only |
| `torch_npu/utils` | 31 | installation-and-compatibility | contains-inspected-spans |
| `torchnpugen` | 33 | operator-development | contains-inspected-spans |
| `torchnpugen/aoti` | 2 | operator-development | inventoried-only |
| `torchnpugen/autograd` | 13 | operator-development | inventoried-only |
| `torchnpugen/templates` | 11 | operator-development | inventoried-only |
