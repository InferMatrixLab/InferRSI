# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `torch/profiler/profiler.py`, `torch/utils/benchmark/utils/timer.py`, `torch/utils/collect_env.py`, `docs/source/notes/numerical_accuracy.md`, `docs/source/notes/randomness.md`.

Expected behavior:

- Checks actual backend/profiler activities and capture window rather than assuming absent GPU work.
- Explains shape/stack profiler reference retention and overhead.
- Synchronizes the intended completion boundary and uses controlled replicated timing with separate cold compile.
- Limits the conclusion to the measured scope and requires separate service evidence for a service claim.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
