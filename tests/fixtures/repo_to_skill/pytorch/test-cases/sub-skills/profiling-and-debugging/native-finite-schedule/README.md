# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: native-derived. Evidence: `torch/profiler/profiler.py`, `torch/utils/benchmark/utils/timer.py`, `torch/utils/collect_env.py`, `docs/source/notes/numerical_accuracy.md`, `docs/source/notes/randomness.md`.

Expected behavior:

- Uses a finite schedule with prof.step once per workload step.
- Exports/summarizes on_trace_ready after the active cycle.
- Separates CPU schedule instrumentation from device profiling or speed claims.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
