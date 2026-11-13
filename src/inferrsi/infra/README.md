# Infrastructure

`processes.py` owns supervised Linux serving workers and their cleanup. Local
command execution, deadlines and process-tree cleanup live in
`harness.local_process`.
`targets/` fingerprints source; `platforms/` discovers and qualifies devices.
Transport, artifact writes and environment probes are shared utilities.

Infra does not import Harness, Model or campaign examples. Device counts, SKUs
and campaign settings are supplied by callers. Discovery does not establish
backend/model compatibility; qualification requires independent evidence.

See [the architecture and extension contracts](../../../docs/architecture.md).
