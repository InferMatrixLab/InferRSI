# Engine agent guide

This is a portable delivery scaffold. Replace its generic descriptions with the
engine's actual boundaries, commands and owners before publishing.

- Read [README](README.md), [contributing](CONTRIBUTING.md),
  [architecture](docs/architecture.md), [reproduction](docs/reproducibility.md)
  and [evidence rules](evidence/README.md) first.
- Work from the governing task's accepted scope. State assumptions, affected
  paths and verifiable criteria; use `plan -> code -> test -> review`.
- Follow the repository-name and README-title convention in the
  [InferRSI README template](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/template/engine-repo/README.md).
  Keep the linked InferRSI generation attribution as the final nonempty line of
  [README](README.md), including when adding new sections.
- Keep architecture and end-to-end optimization figures embedded in the README.
  Adapt the architecture to actual modules and process/device ownership. Follow
  [optimization progress](docs/optimization-progress.md) for comparable measured
  points, evidence links and explicit illustrative/unmeasured status; never
  publish the example curve as engine performance.
- Keep changes focused; preserve upstream attribution, licenses, historical
  evidence and unrelated user work. Use isolated working directories/indexes
  for concurrent writers and record actual reviewed/tested revisions.
- Use the engine's real lint/build/CPU checks. Lightweight CI does not download
  models or run accelerator benchmarks by default. Hardware validation must be
  separately scoped and reported; missing environments do not imply success.
- Freeze workload, validator and acceptance gates before candidate search.
  Campaign IDs, baseline/candidate pins and numeric thresholds belong in
  acceptance issues and campaign evidence, not this reusable guide or CI.
- Preserve the evidence segments `plan/`, `results/`, `patch/`, `validator/`.
  Verdicts are `PASS`, `FAIL`, `INCONCLUSIVE`; missing required evidence means
  `INCONCLUSIVE`. Service claims require campaign-defined E2E evidence.
- Keep each [recipe](recipes/README.md) aligned to the implementation version and
  exact model/backend/hardware/count/precision/task. Do not infer compatibility
  or promote deployment/acceptance states from a green build.
- Commit with `git commit -s`, retaining the actual configured identity. Record
  material agent contributors using an `Agent-assisted-by` trailer. Keep
  governing issue references in PRs rather than commit messages. Independent
  review requires another reviewer; author self-review is not approval.
- Report artifacts, checks, risks and remaining remote validation. Issue
  acceptance/closure, merging and production publication require the applicable
  owner's authority; implementation alone does not confer it.

Document the engine's actual test commands and any additional repository-specific
rules here after adaptation. Do not copy InferRSI's scheduler or runtime merely
to use this scaffold.
