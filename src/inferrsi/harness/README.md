# Harness

`runner.py` owns the common AB/BA loop, source checks and evidence lifecycle.
Its `execute`, `snapshot`, `assess` and `report` ports are injected; it records
the assessment it receives and judges nothing. `trials/external.py` runs one
command trial, retains its record and collects the trial checks; metric reading
and validation live in `benchmark/metrics.py`. `atomic_json.py`
writes the retained JSON evidence.

`api.py` is the public H entry (`allocate` / `execute` / `read`) for ordinary
local CPU commands; `local_process.py` owns the process domain and the legacy
`execute_command` record.

The old run is composed in `apps/legacy/run.py`. Its gates live in
`benchmark/legacy_run_v0.py`, its report in `apps/legacy/reporting.py`, and
image/video sample collection in `benchmark/sampling.py`.

`skill_evaluation.py` adapts the skill-evaluation client, executes one trial and
retains its facts; check validity, the task verdict and the artifact judgment are
injected by `apps/`. `artifact_sandbox.py` captures a submitted artifact and replays
it under bubblewrap. `improvement.py` advances the search over injected assessments.
`atomic_json.py` and `input_binding.py` supply Harness-owned writes and digests.

Compose `trials/external.py` with a metric reader from `benchmark/metrics.py`
for a new engine, or `benchmark/sampling.py` with a request callback for
image/video sample collection.
Keep model payloads and backend branches outside the shared loop.

See [the architecture and extension contracts](../../../docs/architecture.md).
