# InferRSI tests

Run `python -m pytest` from the repository root on Linux for the full suite.
Pass a directory to run one module, for example `python -m pytest tests/harness`.
Windows can collect the suite and run the portable parallel-round cases with
`python -m pytest tests/harness/test_parallel_round.py::TestPortableParallelRound`.
Parallel-round execution tests that need POSIX directory descriptors run on Linux.

- [Apps](apps/) covers the CLI, integrations, application workflows, and result views.
- [Benchmark](benchmark/) covers task preparation, measurements, and evaluators.
- [Campaigns](campaigns/) covers model-specific workloads, adapters, and archived campaigns.
- [Contracts](contracts/) covers shared types, schemas, and evidence paths.
- [Harness](harness/) covers execution, run state, recovery, and isolation.
- [Knowledge](knowledge/) covers the library, repository packs, search, and installation.
- [Repository](repository/) covers architecture, evidence archives, release tooling, and smoke tests.
- [Skill evaluation](skill_eval/) covers skill evaluation workflows, their graders, and automation.

Place a new test with the module that owns the behavior. Keep related cases together,
using named parameters when inputs exercise the same contract. Shared test data,
synthetic campaigns, and frozen snapshots live in [fixtures](fixtures/).
The root holds shared helpers, installed-package probes, and the
[cross-component artifact byte-equivalence test](test_artifact_helper_copies.py).
