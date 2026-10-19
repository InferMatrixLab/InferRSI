# Infrastructure

`executors/` and `processes.py` own local subprocesses, deadlines and cleanup.
`targets/` fingerprints source; `platforms/` discovers and qualifies devices.
Transport, artifact writes and environment probes are shared utilities.

Infra does not import Harness, Model or campaign examples. Device counts, SKUs
and campaign settings are supplied by callers. Discovery does not establish
backend/model compatibility; qualification requires independent evidence.

See [the architecture and extension contracts](../../../docs/architecture.md).
