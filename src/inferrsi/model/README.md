# Model

`protocols/` defines request and metric contracts. `validators/` owns output
quality checks with explicit campaign-supplied gates. The image validator's
optional dependencies are available through `inferrsi[image]`.

Model/revision pins and numeric acceptance gates stay in campaign plans. Frozen
historical snapshots remain in `tests/fixtures/legacy/`; current examples and
new modules serve new campaigns.

See [the architecture and compatibility boundary](../../../docs/architecture.md).
