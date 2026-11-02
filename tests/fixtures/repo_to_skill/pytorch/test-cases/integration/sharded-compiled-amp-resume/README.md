# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic-cross-route. Evidence: `README.md`, `docs/source/notes/cuda.md`, `docs/source/notes/amp_examples.md`, `docs/source/notes/ddp.md`, `torch/library.py`, `torch/export/__init__.py`.

Expected behavior:

- Covers distributed/checkpoint, training/data, compiler and profiling routes with explicit state/rank/shape contracts.
- Restores optimizer/scaler/RNG/data progress as required and allocates intended sharded state.
- Checks effective-batch scale/clipping and equal collective order on uneven rank work.
- Keeps numerical correctness and actual device/multi-rank verification separate from compilation and throughput claims.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
