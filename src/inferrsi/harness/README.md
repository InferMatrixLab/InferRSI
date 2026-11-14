# Harness

`runner.py` owns the common AB/BA loop, source checks and evidence lifecycle.
Its `execute`, `snapshot`, `assess` and `report` ports are injected; it records
the assessment it receives and judges nothing. `scenarios/external.py` runs one
command trial and applies the caller's metric validation. `atomic_json.py`
writes the retained JSON evidence.

`api.py` is the public H entry (`allocate` / `execute` / `read`) for ordinary
local CPU commands; `local_process.py` owns the process domain and the legacy
`execute_command` record.

The old run is composed in `apps/legacy/run.py`. Its gates live in
`benchmark/legacy_run_v0.py`, its report in `apps/legacy/reporting.py`, and
image/video sample collection in `benchmark/sampling.py`.
Keep model payloads and backend branches outside the shared loop.

See [the architecture and extension contracts](../../../docs/architecture.md).
