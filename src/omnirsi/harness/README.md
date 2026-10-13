# Harness

`runner.py` owns the common AB/BA loop, source checks and evidence lifecycle.
`evaluation.py` adjudicates results; `reporting.py` renders the report.

Compose `scenarios/external.py` with a metric reader for a new engine, or
`scenarios/media.py` with a request callback for image/video sample collection.
Keep model payloads and backend branches outside the shared loop.

See [the architecture and extension contracts](../../../docs/architecture.md).
