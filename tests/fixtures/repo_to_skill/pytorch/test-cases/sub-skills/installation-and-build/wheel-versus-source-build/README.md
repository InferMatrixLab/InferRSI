# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `README.md`, `pyproject.toml`, `setup.py`, `cmake/EnvVarForwarding.cmake`.

Expected behavior:

- Separates CPU wheel/backend availability from a toolkit and from extension compilation.
- Uses the current scikit-build-core/PEP517 recipe and forwarding rules rather than legacy setup.py build flags.
- Chooses a new isolated build environment or reports missing prerequisites without mutating the existing one.
- Withholds CUDA extension success until compilation and actual backend execution.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
