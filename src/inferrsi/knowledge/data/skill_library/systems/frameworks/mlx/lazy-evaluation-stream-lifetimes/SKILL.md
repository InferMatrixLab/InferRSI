---
name: lazy-evaluation-stream-lifetimes
description: Diagnose MLX lazy evaluation, cross-stream ordering and array-buffer lifetimes when timing, memory use or asynchronous results disagree with expectations.
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "MIT",
      "tags": [
        "mlx",
        "lazy-evaluation",
        "stream",
        "buffer-lifetime",
        "synchronization"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/ml-explore/mlx",
          "commit": "bff10220c742907f0c68e55ff174aaea56f74e3d",
          "paths": [
            "mlx/ops.cpp",
            "mlx/transforms.cpp",
            "mlx/array.cpp",
            "mlx/backend/cpu/eval.cpp",
            "mlx/backend/metal/eval.cpp",
            "mlx/backend/cuda/eval.cpp",
            "python/src/transforms.cpp",
            "python/tests/test_eval.py",
            "LICENSE",
            "mlx/scheduler.cpp",
            "python/tests/test_memory.py",
            "CMakeLists.txt",
            "setup.py",
            "python/tests/test_device.py",
            "python/tests/mlx_tests.py",
            ".github/workflows/build_and_test.yml"
          ],
          "readset": "references/source-map.md"
        }
      ],
      "applicability": {
        "scope": "MLX evaluation/stream/buffer diagnosis at the pinned implementation; qualify the actual backend separately.",
        "prerequisites": "Access to the pinned MLX execution/lifetime contract and a bounded reproduction with an identified evaluation/read boundary; device-dependent conclusions need the actual selected backend.",
        "input_contract": "MLX revision/build, backend/device, Python/C++ entry, array shapes/dtypes, primitive streams, evaluation/read boundary and transformation context; timing needs warmup/work boundaries, while memory needs live references, in-flight buffers, allocator cache and synchronized observations.",
        "produced_artifact": "A producer/evaluation/dependency-wait/backend/availability-cleanup trace, ownership table, observed symptom and one discriminating check with build-bound actual evidence status.",
        "failure_modes": "Timing graph construction or submission as execution, assuming evaluated means completed, synchronizing only the default stream, or treating graph detachment/Python deletion as reusable storage can misdiagnose time or memory.",
        "refusal_point": "Stop when the trace answers the question; if the required backend is absent, retain the source-supported diagnosis and exact runtime gap rather than substituting CPU import success."
      },
      "limitations": [
        "Source-derived candidate; no local native-backend, model, service or efficacy validation.",
        "Static content checks do not promote this candidate or establish installed API conformance."
      ],
      "provenance_readsets": [
        "references/source-map.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Separate graph construction, async_eval submission, eval and host reads, and record which stream the measurement actually synchronizes.",
        "Preserve the dependency-wait path and selected backend buffer-retention/donation contract before changing streams or assuming storage can be reused.",
        "Distinguish live, in-flight and allocator-cached memory; inspect the real error/cleanup path before proposing a leak fix or hiding the failure."
      ]
    }
---

# Diagnose MLX evaluation and lifetimes

Use for an MLX workload with misleading submission timings, missing cross-stream dependencies, unexpected retained memory, or a result read before completion. Do not use as an LLM request scheduler, a model KV-cache policy, a compiler/fusion guide, or proof that a backend is installed.

This is a source-derived candidate. Runtime behavior and performance remain unverified. Read the [pinned source map](references/source-map.md) and [execution contract](references/execution-lifetime.md). CPU, Metal and CUDA have distinct implementations; `common` catalog placement describes framework-level guidance and does not certify portability.

## Inputs

Collect the actual MLX revision/package build, backend and device, Python/C++ entry point, array shapes/dtypes, primitive streams, evaluation/read boundary, transformation context, and a bounded reproduction. For timing, retain warmup policy, inputs and the measured work boundary. For memory, distinguish live array references, in-flight buffers, allocator cache and synchronized measurements.

## Procedure

1. **Locate the producer.** Follow the operation to its primitive and stream. At the source pin, `add` creates an array with an `Add` primitive and input dependencies; creating that graph is separate from evaluating it (F1).
2. **Locate the actual completion boundary.** Separate graph construction, `async_eval` submission, `eval`, and scalar/host reads. `eval` waits; an array marked `evaluated` can still carry an unfinished event. Record the explicit stream synchronized by the measurement rather than assuming the default stream covers every queue (F2).
3. **Trace dependency ordering.** Within one evaluation, cross-stream inputs use fences. Across asynchronous evaluations, unfinished events are waited on when their producer and consumer streams differ. A CPU/GPU device change is tracked separately from a same-device stream change. Preserve that dependency path before changing stream placement (F3).
4. **Trace ownership after graph detachment.** A non-tracer array can lose primitive/input graph references after scheduling while backend work still owns input buffers. Inspect the selected backend's retention mechanism and any donation path; dropping a Python variable is not proof that in-flight storage can be reused (F4).
5. **Classify the symptom.** Submission-only timings require a completion-boundary correction; retained in-flight memory requires completion evidence; cached allocator memory needs separate allocator evidence. For an error, inspect the evaluation cleanup and event-error path before calling it a leak or deadlock. Do not add a fallback that hides the original failure (F5).
6. **Choose the smallest discriminating validation.** Use the [validation reference](references/validation.md). First test the selected CPU semantics when applicable, then the actual Metal/CUDA path when the claim depends on it. Preserve inputs, dtype, stream topology and correctness checks. Benchmark only after identifying the executing path and timing boundary.

## Output and stop conditions

Return a compact producer → eval → dependency wait → backend → availability/cleanup trace, an ownership table, the observed symptom, one proposed next check, and passed/failed/not-run evidence tied to the actual build. Stop when the trace answers the question. If the required backend is absent, retain a source-supported diagnosis and the exact runtime gap; do not replace device evidence with CPU import success.

Do not claim a speedup from lazy graph construction time, infer fusion from lazy evaluation, infer zero data-movement cost from unified memory, or transfer Metal callback details to CUDA. A framework test does not establish model quality or serving behavior.
