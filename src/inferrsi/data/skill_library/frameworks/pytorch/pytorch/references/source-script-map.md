# Source artifact and helper disposition

The bundled helpers are bounded adaptations/wrappers, with public installed-package imports and no inspection-checkout dependency. The source inventory is complete at the path level; only selected artifact bodies were inspected as recorded in the readset. Group exclusions classify infrastructure purpose, not a claim each script body was audited.

| Source repo artifact | Decision | Bundled replacement | Reason |
| --- | --- | --- | --- |
| torch/utils/collect_env.py | adapt | scripts/inspect_environment.py | Large collector calls subprocesses and exposes package/hardware/local config; preserve narrow installed identity/backend checks with no subprocess, paths or mutation. |
| torch/distributed/run.py | wrap | sub-skills/distributed-and-checkpoint/scripts/rank_contract.py | Keep the installed public launcher; bundle a tiny allreduce/DDP workload instead of copying its elastic/process-management implementation. |
| docs/source/notes/modules.md | adapt | sub-skills/training-and-data/scripts/tiny_training.py | Replace 10000-iteration pedagogical loop with at most eight in-memory CPU updates and finite/state checks. |
| docs/source/notes/cuda.md; test/test_cuda.py | adapt | sub-skills/memory-streams-and-graphs/scripts/cuda_lifetimes.py | Preserve wait_stream/record_stream and static graph buffer mechanisms; omit calibration sleeps, allocator-address assumptions and large models. |
| test/test_autograd.py; docs/source/sparse.md | adapt | sub-skills/tensor-dispatch-autograd/scripts/tensor_contracts.py | Keep tiny gradient/view/sparse duplicate checks without the large internal test harness. |
| test/export/test_export.py; torch/export/__init__.py | adapt | sub-skills/compiler-and-export/scripts/export_contract.py | Keep dynamic-range positive/negative and archive checks; no source harness or default native compilation. |
| test/test_serialization.py; docs/source/notes/serialization.md | adapt | sub-skills/distributed-and-checkpoint/scripts/state_roundtrip.py | Only self-created temporary tensor state, explicit weights_only/mmap; no external artifact loading or format conversion. |
| torch/profiler/profiler.py; test/profiler/test_profiler.py | adapt | sub-skills/profiling-and-debugging/scripts/profile_step.py | Finite CPU schedule and optional new output; no arbitrary user script re-execution or device benchmark. |
| torch/library.py; test/test_custom_ops.py | adapt | sub-skills/custom-operators-and-extension/scripts/custom_operator.py | Fresh-output/fake/autograd example with gradcheck and optional opcheck; no NumPy conversion, downloaded dependency or native compile. |
| tools/amd_build/build_amd.py | reference-only | sub-skills/installation-and-build/references/workflows.md | Repository-wide source transformation and backend build prerequisites; inappropriate to copy as a package diagnostic. |
| tools/generate_torch_version.py; tools/metadata/* | reference-only | sub-skills/installation-and-build/references/workflows.md | Build-owned version/dependency metadata tied to the source tree; report installed identity with public APIs instead. |
| tools/setup_helpers/*; tools/build_libtorch.py; tools/native_aot/* | reference-only | sub-skills/installation-and-build/references/workflows.md | Source build/codegen/toolchain/dependency graph; copying isolated scripts would lose build ownership and perform large native builds. |
| torch/distributed/checkpoint/format_utils.py | reference-only | sub-skills/distributed-and-checkpoint/references/workflows.md | Trusted-store conversions can load unrestricted pickle and write checkpoints; not safe as a generic input validator. |
| test/run_test.py; test/** native harnesses | reference-only | all route workflows | Matching built source and internal testing dependencies required; use selected candidates after integration, not bundled full harness. |
| scripts/**; .ci/**; .github/** maintainer automation | exclude | none | Release/CI/environment/package publication and machine orchestration; not needed for installed runtime diagnostics, may mutate external state. |
| tools/linter/**; torchgen/**; tools/testing/** | exclude | none | Source-tree code generation/lint/test infrastructure; operating recipes preserve ownership but do not copy a partial infrastructure stack. |
| benchmarks/**; torchgen/_autoheuristic/** | exclude | none | Large performance/data generation and tuning suites; no controlled benchmark-scale task or device was supplied. |
| third_party/**; android/** tool scripts | exclude | none | Vendor/unpopulated submodule or unsupported legacy mobile build context; not copied or executed. |

Run helpers only when their route is selected. All parsers accept --help without torch import. Device and distributed helpers require actual backend/trusted-job prerequisites. Runtime helpers are diagnostic resources, not validation reports.
