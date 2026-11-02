# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: native-derived. Evidence: `docs/source/notes/autograd.md`, `aten/src/ATen/core/dispatch/Dispatcher.h`, `aten/src/ATen/core/dispatch/DispatchKeyExtractor.h`, `docs/source/sparse.md`, `docs/source/nested.md`, `docs/source/func.md`.

Expected behavior:

- Uses double-precision inputs requiring grad and gradcheck.
- Adds gradgradcheck only when double backward is part of the contract.
- Explains that a successful numerical derivative check does not verify all devices or custom registration.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
