# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: native-derived. Evidence: `docs/source/notes/cuda.md`, `c10/cuda/CUDACachingAllocator.cpp`, `test/test_cuda.py`.

Expected behavior:

- Uses bundled cuda_lifetimes with producer/consumer waits and lifetime records.
- Avoids copying source test calibration sleeps and allocator pointer-reuse assertions.
- Reports BLOCKED_REQUIRED_BACKEND when CUDA is absent rather than counting CPU as a pass.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
