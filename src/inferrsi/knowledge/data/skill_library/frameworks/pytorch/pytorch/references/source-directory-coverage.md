# Repository discovery and coverage

Full tracked-tree discovery at `9a90a4fefcaafa63ac984621963a6fcc66aee68c` contains 22,762 entries. Counts include Gitlinks and tracked metadata; unpopulated submodule contents are absent. Selected readsets, not counts, support semantic claims.

| Source top-level area | Tracked entries | Owner/disposition | Evidence boundary |
| --- | ---: | --- | --- |
| `(root files)` | 52 | installation-and-build; root provenance | README, build metadata, security and notices selected; unrelated editor/release metadata excluded. |
| `.agents` | 34 | support-policy inventory | Repository contribution policy/skills are source context, not instructions that authorize GitHub mutations; no copied managed agent skills. |
| `.ci` | 215 | excluded execution | CI containers/build orchestration and credentials/large installs; selected build metadata only informs install route. |
| `.claude` | 2 | excluded execution | Agent-specific tooling/policy, no runtime deployment. |
| `.ctags.d` | 1 | excluded | Editor navigation, no operating workflow. |
| `.devcontainer` | 7 | excluded execution | Developer container setup not needed for installed-package diagnostics. |
| `.github` | 339 | excluded execution | CI/release/issue workflows are maintainer infrastructure, not user runtime. |
| `.spin` | 1 | installation-and-build | Developer entry/config inventory; no automatic shell build execution. |
| `.vscode` | 2 | excluded | Editor-specific settings. |
| `android` | 94 | compiler-and-export | Legacy mobile build/interface inventory; unsupported Mobile migration boundary, no Android qualification. |
| `aten` | 2786 | tensor-dispatch-autograd; training-and-data; custom-operators-and-extension | Selected dispatcher and SDPA internals deeply inspected; native operator/device/kernel families inventoried, not all read. |
| `benchmarks` | 551 | profiling-and-debugging | Timing methodology and workload-selection boundary; benchmark-scale suites not executed or copied. |
| `binaries` | 12 | installation-and-build | C++ tool/build inventory, not user package entrypoints or validated binaries. |
| `c10` | 445 | memory-streams-and-graphs; tensor-dispatch-autograd | Native caching allocator/dispatch mechanisms selected; other device runtime long tail inventoried. |
| `caffe2` | 49 | installation-and-build; custom-operators-and-extension | CMake/legacy C++ integration surface; legacy runtime not represented as a current training API. |
| `cmake` | 87 | installation-and-build | Environment forwarding/build/backend source; third-party compiler detection not fully qualified. |
| `docs` | 430 | all routes | Workflow/API/security documentation selected with code checks; figures, generated API lists and unselected tutorial details inventoried only. |
| `functorch` | 83 | tensor-dispatch-autograd; compiler-and-export | torch.func migration/function transforms; compiler integration support varies by op. |
| `mypy_plugins` | 2 | excluded runtime | Type-check tooling, not user tensor execution. |
| `scripts` | 91 | source-script-map | Selected support tooling evaluated by family; maintainer/release/infrastructure side effects excluded. |
| `test` | 11912 | all routes | Selected assertions used as native candidates and helper pattern evidence; full native suite not run. |
| `third_party` | 82 | excluded implementation | Gitlinks/vendor headers/license references inventoried; submodules not populated, vendor code not semantically extracted. |
| `tools` | 421 | installation-and-build; custom-operators-and-extension | Build/codegen/maintenance inventory; full developer execution requires a matching built source environment. |
| `torch` | 4975 | all routes | Public Python/C++ entrypoints and selected implementation mechanisms; see module-family table. |
| `torchgen` | 89 | custom-operators-and-extension; installation-and-build | Schema/codegen ownership, not a standalone runtime training package. |

## Public module families

| Family | Route | Procedure and explicit limit |
| --- | --- | --- |
| Tensor factories/indexing/views, FFT/linalg/special/distributions, sparse/nested/masked | tensor-dispatch-autograd | Metadata/alias/domain/layout/gradient control; operator-by-operator numerical/backend qualification remains long tail |
| autograd, func, functorch, subclasses, dispatch/decomposition/prims/refs | tensor-dispatch-autograd; custom operators | Reverse/forward AD and transform contracts; private extension/experimental surface is not universal public support |
| nn, optim, amp, data, multiprocessing, quantization/ao/legacy | training-and-data | Registered state/update, collation/sharding, scaling, attention and compression migration; no model-zoo/dataset download |
| compiler, _dynamo, _inductor, _functorch, fx, export/_export, onnx, jit, nativert | compiler-and-export | Guards -> lowering -> shape/export/consumer contracts; AOT/native runtime compatibility requires target execution |
| cuda, accelerator, cpu, mps, xpu, mtia, numa, backends | installation-and-build; memory-streams-and-graphs | Backend identity and resource boundaries; CUDA lifetime procedure is device-specific, other backend execution unverified |
| distributed: c10d, DDP, fsdp, tensor/DeviceMesh, checkpoint, elastic, pipelining, rpc, symmetric memory | distributed-and-checkpoint | Rank/order/state ownership and trust procedures; specialized parallelism/fault-tolerance paths need scoped native tests |
| serialization/storage/package, _weights_only_unpickler | distributed-and-checkpoint | Trusted state_dict, mmap, alias preservation and format distinction; torch.package executable packaging has its own trust/version boundary |
| profiler, monitor, logging/debug utilities, benchmark | profiling-and-debugging | Bounded traces, timing, numerical and compiler isolation; experimental tooling availability is installation-specific |
| library, _library/_custom_op, C++ extension/backend_registration, torchgen/ATen schemas | custom-operators-and-extension | Schema/mutation/fake/AD/extension boundary; no universal third-party backend qualification |
| utils tensorboard/model_zoo/bundled_inputs/mobile_optimizer | nearest training/export/profiling route | Optional dependency/artifact lifetimes; external telemetry, network downloads and legacy deployment not executed |

## Long-tail qualification register

All major user workflow families have an owner above; the graph does not enumerate every operator signature, device kernel, quantizer, optimizer, sparse/nested transform, C++ ABI, exporter opset, distributed schedule, native runtime or maintainer/release path. These are deliberate depth/validation limits, not hidden omissions. For a concrete task, select its exact overload/model/shape/backend and extend a bounded readset and native check before making new support or performance claims.

Required missing backend evidence stays BLOCKED_REQUIRED_BACKEND. Full source build/native test suite, GPU kernels/graphs/NCCL, ROCm/MPS/XPU/external accelerators, multi-node fault recovery, ONNX target and AOT/mobile consumers remain unqualified. Source coverage and preparation smoke do not convert these to PASS.
