# Harness

`runner.py` owns the common AB/BA loop, source checks and evidence lifecycle.
`evaluation.py` adjudicates results; `reporting.py` renders the report.

`api.py` is the public H entry (`allocate` / `execute` / `read`) for ordinary
local CPU commands; `local_process.py` owns the process domain and the legacy
`execute_command` record.

Compose `scenarios/external.py` with a metric reader for a new engine, or
`scenarios/media.py` with a request callback for image/video sample collection.
Keep model payloads and backend branches outside the shared loop.

See [the architecture and extension contracts](../../../docs/architecture.md).
