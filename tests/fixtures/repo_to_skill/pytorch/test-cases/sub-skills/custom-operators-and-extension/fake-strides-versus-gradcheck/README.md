# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `torch/_library/custom_ops.py`, `torch/library.py`, `torch/utils/cpp_extension.py`, `docs/source/notes/extending.md`, `test/test_custom_ops.py`.

Expected behavior:

- Distinguishes output alias contract from mutation metadata and returns fresh output or correct supported schema.
- Matches fake size/stride/dtype/device metadata without reading data.
- Explains opcheck registration/functionalization and gradcheck derivative mathematics are separate.
- Handles incoming gradient strides explicitly and requires target device/stream checks for the native kernel.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
