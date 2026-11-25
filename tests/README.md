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
Keep probes and support code beside the tests that use them. The repository-wide
[installed-wheel check](repository/check_installed.py) also runs the Harness
[session-lock probe](harness/session_lock_probe.py) against the installed package.
The [artifact-copy contract](repository/test_artifact_helper_copies.py) is the test
called `tests/test_artifact_helper_copies.py` in the byte-pinned runtime sources.
Only this guide and the Python package marker live at the root.
