# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `docs/source/notes/cuda.md`, `c10/cuda/CUDACachingAllocator.cpp`, `test/test_cuda.py`.

Expected behavior:

- Separates wait_stream ordering from record_stream allocator lifetime.
- Orders producer-to-consumer and result consumption and keeps in-flight storage alive.
- Copies new values into static captured input storage instead of rebinding a Python variable.
- Explains graph-private pool reservation versus live allocation and withholds unavailable CUDA runtime success.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
