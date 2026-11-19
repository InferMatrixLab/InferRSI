# Infrastructure

`artifacts.py` holds the shared file digests and JSON evidence writes until #498
slice 5 retires this package. The serving helpers moved to
`inferrsi.harness.serving` (slice 2). The host probes, platform discovery, source
identity and environment facts moved to `inferrsi.apps.host` (slice 3a).

Infra does not import Harness, Model, Apps or campaign examples.

See [the architecture and extension contracts](../../../docs/architecture.md).
