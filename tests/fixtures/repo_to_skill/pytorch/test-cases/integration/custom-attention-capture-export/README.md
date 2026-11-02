# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic-cross-route. Evidence: `README.md`, `docs/source/notes/cuda.md`, `docs/source/notes/amp_examples.md`, `docs/source/notes/ddp.md`, `torch/library.py`, `torch/export/__init__.py`.

Expected behavior:

- Connects custom-op schema/fake/autograd, attention semantics, stream/capture lifetime and export routes.
- Requires fake metadata without data reads and checks SDPA mask/dropout contracts.
- Keeps static captured buffer addresses with copy-in and actual CUDA checks.
- Qualifies ONNX translation/opset/external weights and target execution separately; preserves missing backend blockers.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
