# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `README.md`, `docs/source/notes/cuda.md`, `docs/source/notes/amp_examples.md`, `docs/source/notes/ddp.md`, `torch/library.py`, `torch/export/__init__.py`.

Expected behavior:

- Routes installation identity, profiling, training/data and compiler before tuning a hypothesis.
- Keeps PyTorch and TorchNPU source identities independent rather than asserting a compatible pair.
- Distinguishes source inventory and installed CPU diagnostics from target backend evidence.
- Uses bundled resources rather than requiring the original distillation checkout.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
