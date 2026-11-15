# Changelog

## [Unreleased]

### Changed

- Eleven legacy root modules are removed (Refs #412, R1). Their implementations
  already lived in `inferrsi.knowledge` and `inferrsi.apps`. The root files are
  deleted in the change that moves their last consumers, with no forwarding
  shells, `sys.modules` aliases or import fallbacks:
  - `inferrsi._skill_selection` → `inferrsi.knowledge._skill_selection`
  - `inferrsi._source_snapshot` → `inferrsi.knowledge._source_snapshot`
  - `inferrsi.catalog` → `inferrsi.knowledge.catalog`, and
    `inferrsi.resources.repository_packs` for `REPO_TYPES` and `repository_pack`
  - `inferrsi.knowledge_operations` → `inferrsi.knowledge.knowledge_operations`
  - `inferrsi.knowledge_store` → `inferrsi.knowledge.knowledge_store`
  - `inferrsi.research` → `inferrsi.knowledge.research`
  - `inferrsi.skill_catalog` → `inferrsi.knowledge.skill_catalog`
  - `inferrsi.evaluation` → `inferrsi.apps.legacy.evaluation`
  - `inferrsi.execution` → `inferrsi.apps.legacy.run` for `run_experiment` and
    for `execute_trial`, the former `_execute`; `inferrsi.infra.targets` for
    `repository_identity`; `inferrsi.harness.local_process` for `_WindowsJob`
    and `_stop_tree`
  - `inferrsi.reporting` → `inferrsi.apps.legacy.reporting`
  - `inferrsi.inspection` → `inferrsi.apps.inspection`
  - Importing any of the eleven old module paths now raises
    `ModuleNotFoundError`, in external Python code as well as in this
    repository. A pickle that names a class or function by one of those paths
    no longer loads. Objects defined in the canonical modules have named them
    in new pickles since they moved there. `inferrsi.execution.run_experiment`
    and `inferrsi.inspection.inspect_environment` were defined in the root
    files themselves, so every existing pickle of either function reference is
    affected. Such pickles need explicit migration or the prior release. `src/`
    has no pickle usage, and frozen evidence is not rewritten: a historical
    campaign replays with its original source-pinned bundle or wheel.
  - No CLI command, flag, output or exit code changes. Root `cli.py` and
    `arguments.py` stay in place until A1 (#408); this change edits only their
    imports. `arguments.REPO_TYPES` is still the one
    `inferrsi.resources.repository_packs.REPO_TYPES` tuple object, now imported
    from that module directly instead of through root `catalog`.
  - Root `inspection.py` was not an alias: it bound the Infra facts API to the
    host. `inferrsi.apps.inspection.inspect_environment` keeps its signature and
    result and holds that binding. `_command` is `infra.commands.probe_command`
    and `repository_identity` is `infra.targets.repository_identity`, both read
    from the module on each call. Test injection points move with it, from
    `inferrsi.inspection._command` and `inferrsi.execution.repository_identity`
    to those two names on `inferrsi.apps.inspection`. `infra/inspection.py` is
    unchanged and imports no Apps module, and an inspection no longer loads the
    old-run composition or Benchmark to obtain the snapshot.
  - `inferrsi.apps.legacy.run.run_experiment(spec, environment)` is the
    two-argument entry that root `execution.run_experiment` was. Its `execute`
    and `snapshot` keyword defaults are now `None` and resolve to the module's
    `execute_trial` and `repository_identity` when the run starts. A test that
    replaced `inferrsi.execution._execute` now replaces
    `inferrsi.apps.legacy.run.execute_trial`. An explicitly passed port still
    wins.
  - `docs/legacy-knowledge-manifest.json` ends at zero `compatibility_pairs`,
    from nine. Eight were edges of the seven deleted Knowledge shells; root
    `catalog` had two. The nine records and root `catalog`'s two routes are
    kept, unchanged, under the manifest's last `revision_history` entry. The
    ninth pair, `infra.inspection` → `inferrsi.resources.repository_packs`, is a
    live import that no deletion removes. It is now a permanent exact rule
    outside the allowlist: `technical_leaf.permanent_importers` in the manifest
    and `LEAF_IMPORTERS` in `tests/_gate_policy_support.py`. That one module
    binds only `repository_pack`, with one plain module-level `from` import.
    Any other importer, name, alias, import of the leaf as a module object,
    nested import, `sys.modules` use or dynamic import fails, and an
    `inferrsi.resources.` prefix allows nothing. The leaf's bytes, locked
    SHA-256, allowed imports, two symbols, top-level shape and import-free
    parent initializer are unchanged.
  - One temporary entry is declared beside that rule and is not part of it.
    Root `arguments.py` reads `REPO_TYPES` from the leaf
    (`technical_leaf.temporary_importers`, `TEMPORARY_LEAF_IMPORTERS`), and it
    joins `cli.py` in the gate's exact `APPLICATION_ENTRIES` because it now
    names `inferrsi.knowledge` itself. Both end in A1 (#408), which removes root
    `arguments.py`. Until then the report carries a
    `temporary leaf importers: 1` blocker.
  - The gate no longer registers `LEGACY_RUN_FORWARDERS`. The eleven names are
    `RETIRED_ROOT_MODULES`: a file that returns under one is a violation, and
    no Knowledge, Harness, Benchmark or Apps closure may reach one.
  - `first_wave_report()` on this tree has no violation, and the `allowlist`
    and `legacy run forwarders` blockers are gone. `isolation_complete` and
    `new_core_closure_isolated` are still false. Three blockers remain: the
    temporary entry above, twelve `harness` → `inferrsi.infra` hits in six
    Harness modules (R2), and five declared runtime resource loaders (R3).
  - The permanent importer rule, the temporary entry and this manifest revision
    require formal architecture review. Passing tests do not supply it, and the
    implementer does not self-approve them.
  - `.github/knowledge-model-policy.json` drops the three deleted shell paths
    (`src/inferrsi/catalog.py`, `src/inferrsi/skill_catalog.py` and
    `src/inferrsi/knowledge_operations.py`) from `protected_paths`. The three
    `src/inferrsi/knowledge/` implementations stay protected, and no other
    policy field changes.
  - The exact root inventory in `tests/test_package_root_inventory.py` shrinks
    from 21 to 10 tracked files: `__init__.py`, `__main__.py`,
    `_mindie_read_worker.py`, `arguments.py`, `benchmark_operations.py`,
    `cli.py`, `mindie_context.py`, `mindie_mcp.py`, `mindie_project.py` and
    `summary_chart.py`. The final two-file root waits for the A1/A2 (#408) and
    M1 (#452) moves. The build-generated `_version.py` stays wheel metadata, not
    a tracked root file.
- Repository-pack access and the evidence path rules leave the package root
  (Refs #451). Root `_repo_pack_data.py` and `evidence_paths.py` are removed in the
  same change, with no forwarding shells or `sys.modules` aliases:
  - `inferrsi._repo_pack_data` → `inferrsi.resources.repository_packs`
    (`REPO_TYPES`, `repository_pack`).
  - `inferrsi.evidence_paths` → `inferrsi.contracts.evidence` for
    `EVIDENCE_SEGMENTS`, `campaign_evidence_root` and `evidence_subpaths`, and
    `inferrsi.apps.evidence_layout` for `ensure_evidence_layout`.
  - Importing either old module path fails, and a pickle that names one of these
    functions by an old module path no longer loads. Such external pickles need
    explicit migration or the prior release; new pickles name the canonical
    modules above. `src/` has no pickle usage, and frozen evidence is not
    rewritten.
  - Signatures, return values and errors are unchanged. `REPO_TYPES` stays one
    seven-entry tuple object for every remaining consumer: root `catalog`,
    `knowledge.catalog` and the CLI arguments. The reader keeps the anchor
    `files("inferrsi").joinpath("harness", "data", "repo_packs", ...)` and imports
    no `inferrsi` module, and `resources/__init__.py` imports nothing. The seven
    `pack.json` files keep their bytes and stay under `harness/data/`.
  - `contracts.evidence` only builds paths and does no filesystem I/O.
    `apps.evidence_layout` creates the four directories in the same order with
    the same `mkdir(parents=True, exist_ok=True)` call. `contracts/__init__.py`
    still re-exports only `RunSpec`.
  - `docs/legacy-knowledge-manifest.json` relocks the neutral leaf's module and
    file path and points the `catalog` and `infra.inspection` pairs at the new
    module. The leaf's bytes and locked hash value are unchanged, and the nine
    compatibility pairs remain. That relock requires formal architecture review:
    passing tests do not supply it, and the implementer does not self-approve it.
  - The exact root inventory in `tests/test_package_root_inventory.py` shrinks
    from 23 to 21 tracked files: `__init__.py`, `__main__.py`,
    `_mindie_read_worker.py`, `_skill_selection.py`, `_source_snapshot.py`,
    `arguments.py`, `benchmark_operations.py`, `catalog.py`, `cli.py`,
    `evaluation.py`, `execution.py`, `inspection.py`, `knowledge_operations.py`,
    `knowledge_store.py`, `mindie_context.py`, `mindie_mcp.py`,
    `mindie_project.py`, `reporting.py`, `research.py`, `skill_catalog.py` and
    `summary_chart.py`. It is an exact set that each later removal shrinks, not
    the final two-file root. The build-generated `_version.py` is wheel metadata,
    not a tracked root file.
  - The #412 entry above supersedes three statements in this entry: root
    `catalog` is no longer a `REPO_TYPES` consumer, the nine compatibility pairs
    are retired, and the root inventory is 10 files.
- Shared technical contracts now live in `inferrsi.contracts` (Refs #451). The four
  root files `_json_v1.py`, `runspec.py`, `claim.py`, and `contracts.py` are removed
  in the same change. Canonical implementations are `contracts/json_v1.py`,
  `contracts/runspec.py`, and `contracts/claim.py`; `contracts/__init__.py`
  re-exports only `RunSpec` from its single definition. Public
  `from inferrsi.contracts import RunSpec` remains supported, and Harness
  re-exports the same `inferrsi.contracts.claim.Verdict` object.
  - The old `inferrsi._json_v1`, `inferrsi.runspec`, and `inferrsi.claim` imports
    and pickle module paths are retired, with no forwarding shells or
    `sys.modules` aliases. Historical pickles require explicit migration or the
    prior release; new pickles name the canonical implementation modules.
  - Canonical JSON bytes, error stages, RunSpec serialization/validation, and
    Verdict values are unchanged. Frozen evidence is not rewritten.
  - `tests/test_package_root_inventory.py` locked the exact 23-file root
    inventory that this change left and rejects unexpected additions; each later
    removal must shrink that set in its own PR, rather than requiring the final
    two-file root now. The entry above shrinks it to 21.
- The `inferrsi.observability` package is dissolved into its owning packages. No forwarding
  modules remain, so imports must use the new paths:
  - `campaign_records`, `campaign_trace`, `optimization_log`, `optimization_trace`,
    `profile_timeline` and `timing_clock` are under `inferrsi.harness.records`.
  - `dashboard`, `dashboard_data`, `dashboard_external`, `dashboard_live`,
    `dashboard_timeline`, `dashboard_workflow`, `experiment_timing`, `optimization_chart`,
    `optimization_story` and both HTML templates are under `inferrsi.apps.views`.
  - `pre_profile_searches` from `profile_timeline` is in
    `inferrsi.apps.views.profile_searches`.
  - `capture_context` and `verify_capture` from `knowledge_capture`, and `create_campaign`
    with backend validation, are in `inferrsi.apps.campaign`.
- The old `run` chain is split by owner. The CLI, its exit codes 0/1/2 and the
  `evaluation.json` bytes are unchanged. Root `inferrsi.evaluation`,
  `inferrsi.execution` and `inferrsi.reporting` keep working as forwarders.
  That held until the #412 entry above removed all three.
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
