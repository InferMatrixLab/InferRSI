# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: native-derived. Evidence: `torch/_library/custom_ops.py`, `torch/library.py`, `torch/utils/cpp_extension.py`, `docs/source/notes/extending.md`, `test/test_custom_ops.py`.

Expected behavior:

- Explains real and fake output strides may differ despite matching shape.
- Preserves metadata including dtype/device/stride in the fake implementation.
- Checks registration with opcheck and numerical derivatives separately where applicable.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
