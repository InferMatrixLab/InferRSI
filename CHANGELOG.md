# Changelog

## [Unreleased]

### Changed

- The `inferrsi.infra` and `inferrsi.model` packages are removed (Refs #498, slices 3b, 4
  and 5). There is no forwarding module or alias, and the import gate fails any import of
  either package name, with or without a file behind it.
  - `inferrsi.infra.artifacts` is now `inferrsi.apps.artifacts`. Apps owns this copy with
    the same function source as the Harness and Benchmark copies, and
    `tests/test_artifact_helper_copies.py` keeps the three equal. `apps/delivery/`, the
    tools, the examples and the tests import it. The Apps copy and `harness/artifact_primitives.py`
    use the same `.session.lock` file lock, so a Harness writer and an Apps export exclude
    each other across processes.
  - `inferrsi.model.anthropic_agent`, `anthropic_edit_agent` and `request_guard` are now
    `inferrsi.apps.integrations.anthropic.*`. Only the two path-valued `SOURCE` constants
    changed. `tools/skill_eval_compare.py` hashes the new files as controllers, so a new
    comparison plan binds them; an existing plan keeps its recorded identities. The
    Messages worker still loads its adjacent `request_guard.py` by file location.
  - The optimization session's runtime identity no longer hashes `infra/artifacts.py`.
    A session planned before this change is refused before `status`, `recover` or any other
    operation runs, and its plan is not changed. Resume such a session with the runtime that
    planned it, as for the serving move.
  - The package now holds exactly `apps`, `benchmark`, `contracts`, `harness`, `knowledge`
    and `resources`. `tests/test_package_root_inventory.py` fails a returning `infra/` or
    `model/`, a new sibling package and a missing one.
  - The Windows host job now compares the Harness copy with the Apps copy and runs the
    cross-process lock test.
- The host bindings move from `inferrsi.infra` to the new `inferrsi.apps.host`
  package (Refs #498, slice 3a). There is no forwarding module or alias, and the
  import gate fails any import of an old path.
  - `inferrsi.infra.commands`, `inspection`, `environment`, `platforms` and
    `targets` are now `inferrsi.apps.host.commands`, `inspection`, `environment`,
    `platforms` and `targets`. Only one import line changes, in `inspection.py`,
    which reads the neutral data leaf one package level deeper.
  - The permanent neutral-leaf importer rule now names
    `inferrsi.apps.host.inspection`. It moved with its file in the same change,
    and `inferrsi.infra.inspection` is retired, so no window admits two importers.
    `technical_leaf.permanent_importers` in `docs/legacy-knowledge-manifest.json`
    names the new module. The A1 state is kept unchanged in `revision_history`, and
    every leaf lock is unchanged. The move needs the same formal architecture review
    as the rule.
  - The `apps/host/` package keeps Infra's limit: the gate fails any path from it to
    a Knowledge, Harness or Benchmark module.
  - `inferrsi.infra` now holds only `artifacts.py`.
- The `inferrsi.infra.campaign` import facade is removed (Refs #498, slice 3c). It
  only re-exported Infra helpers, and its one caller is the example campaign.
  There is no forwarding module or alias, and the import gate fails any import of
  the old path.
  - `examples/qwen21_turbo_b300.py` imports `inferrsi.infra.artifacts`,
    `inferrsi.infra.environment` and `inferrsi.infra.targets` directly.
  - `helper_hashes` moves into that example unchanged. It hashes every Python file
    of the installed package, so a record made after this change no longer lists
    `inferrsi/infra/campaign.py`. Every other path it binds is unchanged, and
    existing records are not rewritten.
- The serving helpers move from `inferrsi.infra` and `inferrsi.model` to the new
  `inferrsi.harness.serving` package (Refs #498, slice 2). There is no forwarding
  module or alias, and the import gate fails any import of an old path.
  - `inferrsi.infra.processes` is now `inferrsi.harness.serving.server`,
    `inferrsi.infra.http` is now `inferrsi.harness.serving.http`, and
    `inferrsi.model.protocols.image` is now `inferrsi.harness.serving.image`.
    The emptied `inferrsi.model.protocols` package is removed. The server helpers
    keep their Linux-only process-group contract.
  - The package initializer imports nothing, so importing the HTTP or image client
    does not load the server helpers.
  - `inferrsi.infra.campaign` no longer re-exports `launch_server` and
    `stop_server`. The example campaign imports them from
    `inferrsi.harness.serving.server`.
  - The optimization session's runtime identity now hashes
    `harness/serving/server.py` in place of `infra/processes.py`. A session planned
    before this change is refused before `status`, `recover` or any other operation
    runs, and its plan is not changed. Resume such a session with the runtime that
    planned it: install the wheel or source of the commit it was started from, and
    run the same `inferrsi benchmarks session` command there.
  - Pickled objects that name an old module path no longer load.
- `docs/contracts/schemas/contract-v1.schema.json` validates more strictly
  (Refs #497). Eleven `pattern` values ended with `$`, which in Python `re`, and so in
  `jsonschema`, also matches before one trailing LF: `"att-1\n"` passed `Id`. They now
  end with `(?![\s\S])`, which matches only at the end of input in Python `re` and in
  ECMA-262. This is a bug fix inside the Proposed `contract-v1`.
  - Changed: `Id`, `Sha256`, `SemanticId`, `Timestamp`, `Decimal`, the `JsonValue` and
    `Parameters` `propertyNames`, `UsageObservation.currency`, `StorageMount.namespace`,
    and `StorageConfig.archive_namespace` and `harness_namespace`. `Path` is unchanged:
    its lookahead already rejects U+0000–U+001F and U+007F.
  - Newly rejected: a value that is valid apart from one trailing LF. Every other value
    keeps its result, and no value is trimmed. In ECMA-262, `$` already rejected the
    trailing LF.
  - The schema SHA-256 changes from `38a11bfe…b004` to `38bdae2a…027d`; no file pins
    it. `dto-field-index.md` shows the new patterns. `fixtures/t108-v4/` is unchanged.
  - New `docs/contracts/fixtures/pattern-boundary-cases.json` pairs a valid value with
    LF, CRLF and CR variants for all twelve patterns.
    `tests/test_contract_schema_patterns.py` validates them through the named
    definitions and runs the patterns in Node.js. `jsonschema>=4.18` joins the `dev`
    extra so these checks run in CI rather than skip. The existing `jsonschema` checks
    in `tests/test_harness_execute.py` now run there too.
- The metric contract and the quality validators move from `inferrsi.model` to
  Benchmark (Refs #498, slice 1). There is no forwarding module or alias, and the
  import gate fails any import of an old path, even when no file is behind it.
  - `inferrsi.model.protocols.metrics` is now `inferrsi.benchmark.metrics`.
    `inferrsi.model.validators` (`flare`, `image`) is now
    `inferrsi.benchmark.validators`.
  - The Flare adapter command is now
    `python -m inferrsi.benchmark.validators.flare`, with the same arguments,
    outputs and exit codes. The old `python -m inferrsi.model.validators.flare`
    fails with `ModuleNotFoundError`.
  - New `inferrsi.benchmark.artifacts` holds Benchmark's own `sha256`,
    `write_json` and `atomic_write_json`. Their code equals the copies in
    `inferrsi.infra.artifacts` and Harness, and
    `tests/test_artifact_helper_copies.py` keeps the copies equal.
    `inferrsi.infra.artifacts` stays for its other users.
  - A new Flare receipt keeps its schema and keys. Its `adapter` digests are those
    of `benchmark/validators/flare.py` and `benchmark/artifacts.py`. Existing
    receipts are not rewritten.
  - The MoE task's `benchmark.py` imports the Benchmark modules. Each MoE
    `evaluate` call prepares its own copy of the task files and launches that copy
    in the same call, so a new run binds the changed `benchmark.py` bytes and no
    directory prepared before this change is launched again.
  - Pickled objects that name an old module path no longer load. The Knowledge
    records that cite `src/inferrsi/model/protocols/metrics.py` at commit
    `b3ef95a` keep that pinned path.
- The five runtime resource loaders are closed and the combined tree is isolated
  (Refs #412, R3). `first_wave_report()` now has no violation and no blocker, and
  `new_core_closure_isolated` and `isolation_complete` are both true.
  - The Harness task protocol no longer runs in the Harness process. Each
    `validate_arguments`, `arguments` and `assess` call runs the new
    `harness/protocol_child.py` as `python -I -B` under a 120 second deadline, in
    its own process group or Windows Job, and returns one strict JSON envelope.
    The child compiles only protocol bytes that match the frozen SHA-256, and a
    protocol `SystemExit` keeps its exit code (argparse usage errors still exit 2).
    An exception the protocol raises is recorded as before R3, under its own type and
    message: an `assess` failure settles as `"<Type>: <message>"`, an `arguments`
    failure keeps its type and message in `coordinator-error.json` and settles through
    the existing coordinator path, and a `validate_arguments` failure prints its own
    message at `session start`. Transport, identity and result failures are recorded
    as `TaskProtocolError` with their kind.
    After every operation the last 4 KiB of the child's stderr, protocol prints
    included, is copied to the caller's stderr; the scratch directory is then
    deleted. The 16 MiB envelope limit and the stderr tail apply when Harness reads
    the files, and the deadline bounds the run.
    `task_protocol.protocol()` is removed; callers use `task_protocol.run()`. A
    task `optimization.py` must take and return JSON values.
  - `moe-forward-npu`: `processes.py` is folded into `benchmark.py`
    (`MARKER`, `cleanup` and `_members` unchanged) and leaves `TASK_FILES`.
  - `qwen3-tts-npu`: `evaluation.py` and the CLI are one `benchmark.py`; the
    prepared bundle no longer has `evaluation.py`. A bundle prepared before this
    change fails its frozen digests and must be prepared again. Retained results
    are not rewritten.
  - The MoE grader and Qwen21 evaluator keep loading the frozen candidate by path in
    their own process, which timing requires. The gate admits
    `importlib.util.module_from_spec` only in task bundle programs, files directly
    inside a `benchmark/tasks/<bundle>/` directory without `__init__.py`, and names no
    task, so a new bundle needs no gate change. Package code may not import a bundle
    program. Name-based lookups (`__import__`, `import_module`, `find_spec` in any
    spelling) still fail there. `first_wave_report().runtime_execution`
    lists each bundle program that loads by path, because static isolation does not
    cover what the loaded code does at run time.
  - The optimization session's runtime identity adds `harness/protocol_child.py`,
    and `harness/task_protocol.py` changed, so a session started before this
    change does not resume after it.

- Six Harness modules stop importing Infra (Refs #412, R2). `agent_sessions`,
  `candidates`, `optimization`, `optimization_session`, `project` and
  `task_protocol` take `digest`, `sha256` and `file_lock` from the new
  `harness/artifact_primitives.py` and `atomic_write_json` from the existing
  `harness/atomic_json.py`. The function bodies equal those in
  `infra/artifacts.py`, so digests, file hashes, JSON bytes, atomic replace and
  lock files are unchanged, and a Harness lock and an Infra lock on the same
  path still exclude each other. `infra/artifacts.py` stays for its other users.
  - `first_wave_report()` no longer reports `harness reaches model/infra`; it had
    12 hits, the package-level `inferrsi.infra` and `inferrsi.infra.artifacts`
    edge from each of the six modules. Harness has no `inferrsi.model` edge.
  - The optimization session's runtime identity adds
    `harness/artifact_primitives.py`. The six edited modules are already in it,
    so a session started before this change does not resume after it.
  - Isolation is still incomplete: the five runtime resource loaders (R3, #412)
    remain.

- The local MindIE adapter moves into the Apps package and its four root files
  are removed (Refs #452, M1), with no forwarding shell, `sys.modules` alias or
  import fallback:
  - `inferrsi.mindie_project` → `inferrsi.apps.mindie.project`
  - `inferrsi.mindie_context` → `inferrsi.apps.mindie.context`
  - `inferrsi.mindie_mcp` → `inferrsi.apps.mindie.mcp`
  - `src/inferrsi/_mindie_read_worker.py` →
    `src/inferrsi/apps/mindie/read_worker.py`, a standalone file that is run by
    path and never imported
  - The four files move with their code unchanged apart from the imports that
    name their neighbours (`.context`, `.project`, `.mcp`) and the package
    version, which `mcp.py` now reads with `from ... import __version__`.
    `apps/mindie/__init__.py` imports nothing and does not re-export the
    version. The `inferrsi mindie` and `inferrsi campaign import-mindie`
    commands, the Codex configuration and the MCP server name are unchanged.
  - The worker keeps its boundary: it starts with `-I -B` in a private working
    directory, with a 20 second limit and a 2 MiB cap, opens SQLite read-only,
    imports only the standard library at the top level and imports
    `mindie_knowledge` inside `read()`. It is not standard-library-only overall.
    The grant file, its explicit opt-in and the recorded read receipts are
    unchanged, as is the OBS layout.
  - Importing `inferrsi.mindie_project`, `inferrsi.mindie_context` or
    `inferrsi.mindie_mcp` now raises `ModuleNotFoundError`, in external Python
    code as well as in this repository, and a pickle that names an object by
    one of these paths no longer loads. Callers import from
    `inferrsi.apps.mindie`. Frozen evidence is not rewritten.
  - The tracked package root shrinks from six files to the final two,
    `__init__.py` and `__main__.py`. The four paths join `RETIRED_ROOT_MODULES`
    in the gate, so a root file that returns under any of them fails, and the
    installed-wheel checker verifies that the adapter and worker ship under
    `apps/mindie/` and that the installed adapter starts the installed worker by
    file path and gets its structured rejection for an unavailable catalog.
  - Isolation is still incomplete: the 12 Harness hits into Infra (R2, #412)
    and the five runtime resource loaders (R3, #412) remain.


- The campaign chart renderer and the single-task launcher move into the Apps
  package and the two root modules are removed (Refs #408, A2), with no
  forwarding shell, `sys.modules` alias or import fallback. Both files move
  with their bytes unchanged:
  - `inferrsi.summary_chart` → `inferrsi.apps.views.summary_chart`
    (`src/inferrsi/summary_chart.py` →
    `src/inferrsi/apps/views/summary_chart.py`), which keeps `build_svg`,
    `build_markdown`, `spec_from_evaluation`, `check_trial_chart_eligibility`,
    `SpecError` and `main`
  - `inferrsi.benchmark_operations` → `inferrsi.apps.benchmark_operations`
    (`src/inferrsi/benchmark_operations.py` →
    `src/inferrsi/apps/benchmark_operations.py`), which keeps `run_task`
  - `tools/campaign_summary_chart.py` keeps its command line and arguments.
    Its exit codes, stdout, stderr and the SVG and Markdown bytes it writes are
    unchanged. The dashboard, the HTML report and `benchmarks run` import the
    canonical modules.
  - Importing `inferrsi.summary_chart` or `inferrsi.benchmark_operations` now
    raises `ModuleNotFoundError`, in external Python code as well as in this
    repository, and a pickle that names an object by either path no longer
    loads. Callers import from `inferrsi.apps.views.summary_chart` and
    `inferrsi.apps.benchmark_operations`. Frozen evidence is not rewritten.
  - The tracked package root shrinks from eight files to six. Besides
    `__init__.py` and `__main__.py`, the four left (`mindie_context.py`,
    `mindie_mcp.py`, `mindie_project.py` and `_mindie_read_worker.py`) wait for
    M1 (#452). The gate's exact-file `APPLICATION_ENTRIES` listing is removed
    with its last entry, so no root file is application assembly, and
    `inferrsi.summary_chart` and `inferrsi.benchmark_operations` join
    `RETIRED_ROOT_MODULES`, so a root file that returns under either name
    fails.
  - Isolation is still incomplete: the 12 Harness hits into Infra (R2, #412)
    and the five runtime resource loaders (R3, #412) remain.

- The CLI moves into the Apps package and the two root CLI modules are removed
  (Refs #408, A1), with no forwarding shell, `sys.modules` alias or import
  fallback:
  - `inferrsi.cli` → `inferrsi.apps.cli` (`src/inferrsi/cli.py` →
    `src/inferrsi/apps/cli/__init__.py`), which exposes the canonical `main`
  - `inferrsi.arguments` → `inferrsi.apps.cli.arguments`
    (`src/inferrsi/arguments.py` → `src/inferrsi/apps/cli/arguments.py`), which
    holds `parser`, `make_spec` and `device_ids`
  - The `inferrsi` console script names `inferrsi.apps.cli:main`, and
    `python -m inferrsi` delegates to the same function. Commands, flags, exit
    codes and stdout/stderr are unchanged. The shared Codex and WorkSwarm
    launcher and the DSH remote bootstrap import the canonical modules.
  - Importing `inferrsi.cli` or `inferrsi.arguments` now raises
    `ModuleNotFoundError`, in external Python code as well as in this
    repository, and a pickle that names an object by either path no longer
    loads. Callers import `main` from `inferrsi.apps.cli` and the parser
    helpers from `inferrsi.apps.cli.arguments`. Test injection points move
    with the code: `inferrsi.cli._knowledge_reader` and `inferrsi.cli.files`
    are the same names on `inferrsi.apps.cli`. Frozen evidence is not
    rewritten.
  - The tracked package root shrinks from ten files to eight. Besides
    `__init__.py` and `__main__.py`, the six left (`summary_chart.py`,
    `benchmark_operations.py` and the four MindIE files) wait for A2 (#408) and
    M1 (#452). The gate's `APPLICATION_ENTRIES` lists only
    `benchmark_operations.py`, and `inferrsi.cli` and `inferrsi.arguments` join
    `RETIRED_ROOT_MODULES`, so a root file that returns under either name
    fails.
  - The temporary neutral-leaf entry for root `arguments.py`
    (`technical_leaf.temporary_importers`, `TEMPORARY_LEAF_IMPORTERS`) and its
    `temporary leaf importers` blocker are removed, and nothing replaces them.
    The moved parser reads `REPO_TYPES` through `inferrsi.knowledge.catalog`,
    which binds the one tuple object from
    `inferrsi.resources.repository_packs`. An Apps module that imports the leaf
    itself still fails as a second importer. The permanent
    `inferrsi.infra.inspection` rule and the empty `compatibility_pairs` are
    unchanged, and the manifest keeps the removed entry in `revision_history`.
    This route for `REPO_TYPES` needs architecture review and is not
    self-approved.
  - Isolation is still incomplete: the 12 Harness hits into Infra (R2, #412)
    and the five runtime resource loaders (R3, #412) remain.
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
