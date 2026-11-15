# Changelog

## [Unreleased]

### Changed

- The old `run` chain is split by owner. The CLI, its exit codes 0/1/2 and the
  `evaluation.json` bytes are unchanged. Root `inferrsi.evaluation`,
  `inferrsi.execution` and `inferrsi.reporting` keep working as forwarders.
- Moved import paths, with no forwarder left under `inferrsi.harness`:
  - `inferrsi.harness.evaluation` → `inferrsi.apps.legacy.evaluation` (`evaluate` with a
    `RunSpec`) and `inferrsi.benchmark.legacy_run_v0` (the gates).
  - `inferrsi.harness.reporting` → `inferrsi.apps.legacy.reporting`.
  - `inferrsi.harness.scenarios.media` → `inferrsi.benchmark.sampling`.
- `inferrsi.harness.runner.run_experiment` now requires its `execute`, `snapshot`,
  `assess` and `report` ports. Use `inferrsi.apps.legacy.run.run_experiment` for the
  composed old run with the previous defaults.
- `inferrsi.harness.scenarios.external.execute_trial` takes `metric=` (a complete
  validation function) in place of `metric_reader=`. Use
  `inferrsi.apps.legacy.run.execute_trial` to keep `metric_reader=` with the common
  metric contract applied.

## [0.1.0] — Developer Preview

Pre-release only. v0.1.0 is a planned Developer Preview. The `v0.1.0` Git tag is not published yet, and this note does not publish a tag or a GitHub Release. There is no API stability promise. The package is not on PyPI. After the tag is published, install from that Git tag. Licensed under Apache-2.0 (`LICENSE`).

### Added

Documented workbench contents for this preview, from the repository README:

- CLI workbench (`inferrsi`) for inference optimization with coding agents. Requires Python 3.10+.
- Knowledge search and cited context export for a coding agent (`inferrsi knowledge search`, `inferrsi context`).
- Evaluation of the benchmark and validation commands you provide, including repeated A/B comparisons with quality gates, source fingerprints, and an HTML evidence report. Verdicts are `PASS`, `FAIL`, or `INCONCLUSIVE`.
- Documented Harness × Model × Infra boundaries, an operation guide, and packaged skill and knowledge records.

### Known limitations

- Developer Preview / pre-release: no API stability promise.
- Not published on PyPI. The `v0.1.0` tag is not published yet.
- Automatic search and automatic knowledge promotion remain planned. Automatic evidence-to-knowledge promotion and automatic RunSpec population are not implemented.
- Knowledge retrieval is read-only. Candidate storage is optional and separately authorized.
- Missing or incomplete evidence stays `INCONCLUSIVE`.
- Process-cleanup behavior still needs platform-specific validation.

### Install

- From this checkout (Python 3.10+): `python -m pip install .`
- After the v0.1.0 tag is published: `pip install "git+https://github.com/InferMatrixLab/InferRSI.git@v0.1.0"`
- PyPI install is not available for this preview.
