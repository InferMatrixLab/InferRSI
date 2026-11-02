# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `docs/source/notes/autograd.md`, `aten/src/ATen/core/dispatch/Dispatcher.h`, `aten/src/ATen/core/dispatch/DispatchKeyExtractor.h`, `docs/source/sparse.md`, `docs/source/nested.md`, `docs/source/func.md`.

Expected behavior:

- Explains detach can share storage and saved-version checks can fail.
- Locates and removes or correctly stages the offending mutation rather than using .data.
- Distinguishes equal jagged lengths from the required shared offsets constituent.
- Uses bounded alias/gradient and ragged checks and does not claim every nested operator is supported.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
