# Validation boundaries

The candidate is empirically `not_run`. Source/package checks do not qualify
native generation or performance. No model, native build, GPU/NPU run or
dependency installation is performed by this procedure.

| Native candidate workflow | Entry / test path | Required backend | Optional comparison | Can CPU substitute? | Dependencies / decisive observation |
|---|---|---|---|---|---|
| Build and load the CLI/library | `.github/workflows/build.yml` CPU/Vulkan jobs; `cmake/ggml.cmake`; no inference assertion in inspected jobs | Selected compiled backend; CPU for CPU build only | Each separately built accelerator | CPU verifies only its build/load | Matching GGML library/private headers and unexpanded submodules; compiler/CMake; frontend build tooling when enabled. No build ran here. |
| One complete image and repeated request | C API `generate_image`, `src/pipeline/image.cpp`; no upstream runtime test file located in this archive | The exact model/backend intended for the claim | A separately qualified CPU baseline | Only for a CPU result | Real model/components, deterministic input ledger, image completion/quality and phase traces. Load success is insufficient. |
| Managed capacity and forced segmented path | `GGMLRunner::execute_graph`, `ModelManager::check_capacity`; proposed native regression harness, not an existing test | A non-CPU single-device backend with valid graph cuts | Monolithic path on the same backend | **No**: CPU bypasses relevant gates | Matching GGML, real supported model, fixed shapes/precision, dispatch evidence, host/device peaks, safe OOM/failure handling and output comparison. |
| Next-segment prefetch activation and cleanup | `SegmentWeightPipeline`, `model_manager_prefetch.cpp`; proposed native trace/assertion harness | Backend/placement advertising and actually executing async prefetch | Same device/model with prefetch disabled | **No** for async device overlap | Event/transfer trace, pin/protection lifetime, completion before consumer, cancellation/failure cleanup, quality and latency. Capability alone is insufficient. |
| Multi-device accounting | `ModelManager::check_capacity`, runner scheduler path; proposed native harness | Exact device set/backend/split mode | Single-device separately | **No** | Multiple devices and matching backend; trace actual placement. Segmented single-device eligibility must not be extrapolated. |

The [loader/storage checks](loader-storage-boundaries.md#proposed-checks)
add proposed catalog-identity, range/short-read and mapping/staging cases.
They require the actual matching parser/manager and a legal small fixture;
source, package and reader checks cannot substitute for those native results.
Observe both the returned result and consumer state: a destination callback
is not read completion, and releasing one mapping owner is not proof of unmap.
No native loader case or agent-efficacy evaluation has been run.

Minimal falsifiers: changing a required model/input without the expected
preparation; evicting pinned/queued weights; stale output after a supported
policy change; a completed image with incorrect quality; a device cap apparently
met only because untracked host/device allocations were omitted; or prefetch
claimed active without transfer/activation evidence.

For any comparison, freeze model/component bytes, inputs, precision, seed,
sampler/sigmas, dimensions, batch and device count. Record preparation/startup,
first real image, warm images, phase timings and peak host/device memory
separately. Keep both successful and failed attempts. Derive acceptance criteria
from the concrete task; the source's memory constants are not performance gates.

Stop at an explicit not-run boundary when the matching GGML source/private
headers, model, device or authorization is absent. Never replace the native
manager/allocator with a fake implementation to obtain a passing result.
