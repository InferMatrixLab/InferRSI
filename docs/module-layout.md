# Target module layout

This page records the directory rule for the integration slice. The first-wave
Knowledge move (K01) is implemented: `src/inferrsi/knowledge/` holds the seven
moved Knowledge bodies. R1 (#412) deleted the seven static root compatibility
shells that K01 left, so those names import only from `inferrsi.knowledge`.
The engineering task contribution now implements `benchmark/registry.py`
and `benchmark/tasks/`. The current flat `cli.py`, `arguments.py` and
`benchmark_operations.py` assemble this slice. The former `observability/`
package is dissolved. Its
campaign records, traces, logs and profile captures are in `harness/records/`,
its dashboard views and templates are in `apps/views/`, and the
collected-context projection is in `knowledge/context_projection.py`.
#371 remains the proposal for the Apps package path and is not accepted here.

The old `run` chain is split by owner. Its gates are in
`benchmark/legacy_run_v0.py`, its execution facts stay in `harness/`, and
`apps/legacy/` composes them with the report. `apps/legacy/` is the path named
by the confirmed split for this slice; that use does not accept #371.
`cli.py` imports the old run only inside its `run` command, so the other
commands, including ordinary optimization, still load no Benchmark module.
R1 deleted the three root forwarders of that chain (`evaluation.py`,
`execution.py` and `reporting.py`), and `cli.py` imports `apps/legacy/` itself.

## Target modules

The four target modules are peers: `knowledge`, `harness`, `benchmark`, and
`apps`. Knowledge, Harness, and Benchmark do not import one another. Apps is
the only assembler. `src/inferrsi/contracts/__init__.py` re-exports only
`RunSpec`, defined once in `contracts/runspec.py`. The technical-only package
also owns `json_v1.py`, `claim.py` and `evidence.py`; it contains no shared
business DTOs and performs no core or host initialization.

`contracts/evidence.py` holds the evidence segment names and the per-campaign
path rules. It only builds paths and does no filesystem I/O. Creating the
directories is `apps/evidence_layout.py`, which reuses those rules, so `mkdir`
stays out of the contracts package. `resources/repository_packs.py` is the
neutral repository-pack facade: the one `REPO_TYPES` tuple and the `pack.json`
reader. It imports no `inferrsi` module, and `resources/__init__.py` imports
nothing. Neither package is a fourth core. C2 (#451) moved these out of root
`_repo_pack_data.py` and `evidence_paths.py` and deleted both root files, with
no forwarding shell or alias.

The flat package root is retired in stages.
`tests/test_package_root_inventory.py` pins the root to an exact file set: 23
tracked files after C1, 21 after C2 and 10 after R1 (#412). The ten are
`__init__.py`, `__main__.py`, `_mindie_read_worker.py`, `arguments.py`,
`benchmark_operations.py`, `cli.py`, `mindie_context.py`, `mindie_mcp.py`,
`mindie_project.py` and `summary_chart.py`. Each later removal PR shrinks that
set in the same change: A1 and A2 (#408) move the CLI, the chart and the
benchmark launcher, and M1 (#452) moves the four MindIE files. The guard does
not assert the final two-file root (`__init__.py` and `__main__.py`) early,
and the build-generated `_version.py` is ignored wheel metadata, not a tracked
root file. [Retired root modules](#retired-root-modules) lists the eleven
paths that R1 removed.

The current `src/inferrsi/harness/` tree is a mixed implementation. Its
presence is not the target Harness boundary and is not evidence that the four
modules are isolated.

There is no sibling `data/` resource tier. K02 moved the Knowledge corpus to
`src/inferrsi/knowledge/data/` and the `repo_packs/*/pack.json` target
descriptions to `src/inferrsi/harness/data/`. The internal corpus split is left
to a future Knowledge issue. The dashboard templates are view templates and
live in `apps/views/`; they did not belong to the corpus merely because they
sat under `data/` before.

The move is physical only. Bundle resource keys, dependency keys and the pinned
`source_files` paths in generated records keep their recorded spelling, so
content bytes, hashes and Bundle revisions are unchanged. `_source_snapshot.LIBRARY`
names the corpus at its pinned `source_revision`, not the current checkout path;
repointing it regenerates every record and needs an explicit new revision.

`src/` stays the import root. `tests/` and `tools/` stay at the repository
root. Also keep these root files where they are: `AGENTS.md` (entry contract),
`CHANGELOG.md`, `MANIFEST.in` (it grafts `src/inferrsi`, so a later resource
move must update packaging in that same slice), and `.agents/` (review skill).

Do not create empty `knowledge/`, `benchmark/`, or `apps/` directories in the
contract slice. Do not treat PR #338 as a reason to add a top-level
`benchmarks/` tree.

## CPU/offline connection

`tests/architecture_closed_loop.py` is the handoff exercised by
`tests/test_architecture_closed_loop.py`. The coordinator does not import
Knowledge, Harness, or Benchmark. Refusal cases still inject outcomes. That
file is not the Apps package, and #371 remains the proposal for that path.
It does not change Bundle revision.

`tests/architecture_real_ports.py` is the CPU/offline connection injected for
the success path. It calls `KnowledgeReader.read` on one installed package
card, `execute_trial` for one local process record, and `evaluate` for one
offline assessment. It does not call `collect` or `search_knowledge`. It does
not choose an archive owner or a run store. `MemoryArchive` still stores only
prepared and assessment bytes. The module stays under `tests/`. A process
exit of 0 in that record remains an execution fact; this assessment does not
turn it into a campaign `PASS`.

## Tentative current ownership

This table is a reading aid for the import gate. It does not authorize moves.
Several flat modules remain shared seams until their slice starts.

| Current path | Tentative reading | This slice |
| --- | --- | --- |
| `cli.py`, `arguments.py`, `__main__.py` | Future Apps entry, after #371 | Not moved; R1 changed only the imports of `cli.py` and `arguments.py`, and A1 (#408) moves both |
| `benchmark_operations.py` | Single-task application launcher | Resolves a task entry and invokes the Harness runner; ordinary projects do not use it |
| `benchmark/registry.py`, `benchmark/tasks/` | Task discovery, definitions and specialized rules | Task-specific quality and measurement code stays with each task |
| `harness/optimization_session.py`, `harness/project.py`, `harness/task_protocol.py` | Shared preparation, execution and retained-result assessment | CLI supplies task resources and knowledge access; ordinary project lifecycle does not import Benchmark |
| `harness/optimization.py`, `harness/candidates.py`, `harness/usage.py` | Shared project and packaged-task lifecycle | Injected execution/assessment; declared file/directory candidates, selection direction and exact/up-to rounds |
| `harness/agent_sessions.py` | Native host handoff records | Freezes requests and retains native IDs and exported observations; the initiating Agent calls host tools |
| `harness/skill_evaluation.py`, `harness/artifact_sandbox.py`, `harness/improvement.py`, `harness/atomic_json.py` | Skill-evaluation host adapter, trial execution and retention, sandbox replay, search progression | Verdict rules and task definitions arrive as injected values; no Model, Infra, Knowledge, Benchmark or Apps import |
| `benchmark/skill_evaluation.py`, `benchmark/skill_eval_diagnostic.py`, `benchmark/skill_eval_engineering.py`, `benchmark/improvement.py` | Skill-evaluation criteria, task definitions and acceptance rules | Pure judgments over retained facts; no Harness import and no process start |
| `apps/skill_evaluation.py`, `apps/skill_eval_engineering.py`, `apps/improvement.py` | Composed skill-evaluation entries | Join Knowledge reads, Harness execution and Benchmark rules behind the signatures that `harness/` held before the split |
| `knowledge/knowledge_operations.py`, `knowledge/knowledge_store.py`, `knowledge/catalog.py`, `knowledge/research.py`, `knowledge/skill_catalog.py`, `knowledge/_skill_selection.py`, `knowledge/_source_snapshot.py` | The seven Knowledge implementations, moved by K01 | Interfaces unchanged; the same-named root shells were deleted by R1 |
| `harness/records/` | Campaign manifests, traces, logs, profile captures and delivered-context captures | Imports no Knowledge or Apps module; `apps/campaign.py` supplies the backend names, the selection default and the context projection |
| `apps/views/`, `apps/campaign.py` | Dashboard views, templates and the Knowledge-to-records connection | Apps path still follows the #371 proposal |
| `harness/` | Mixed legacy tree, not target isolation | Not redefined |
| `harness/runner.py`, `harness/scenarios/external.py`, `harness/atomic_json.py` | Old run execution facts and Harness-owned JSON writes | Ports injected; no Model edge, and no Infra edge except the local process executor |
| `benchmark/legacy_run_v0.py`, `benchmark/sampling.py` | Old run gates and metric validation; image/video sample collection | Imports only `model/protocols/metrics`; owns its rule inputs and verdict labels |
| `apps/legacy/` | Old run composition, old `evaluate` entry and HTML report | Supplies the Git source snapshot from `infra/targets`; path follows the confirmed split, #371 still proposed |
| `apps/inspection.py` | Prepared-environment inspection bound to this host | Binds the `infra/inspection.py` facts API to `infra.commands.probe_command` and `infra.targets.repository_identity`; replaces root `inspection.py`, which R1 deleted with the three old-run root forwarders |
| `model/validators/` | Benchmark-leaning checks | Not moved |
| `infra/` | Seams used by the current tree, including the `infra/inspection.py` facts API | Not a fourth core; reaches no Knowledge, Harness, Benchmark or Apps module |
| `summary_chart.py` | Current report helper | Not moved |
| `contracts/` (`runspec.py`, `json_v1.py`, `claim.py`, `evidence.py`) | Technical-only contracts: RunSpec, canonical JSON, verdict vocabulary, evidence segment and path rules | Exact module set; the initializer re-exports only `RunSpec`; not a fourth core |
| `apps/evidence_layout.py` | Evidence directory creation over the `contracts/evidence.py` path rules | The `mkdir` half of former root `evidence_paths.py`; host I/O stays in Apps |
| `resources/repository_packs.py` | Neutral `REPO_TYPES` and `repository_pack` facade | Former root `_repo_pack_data.py`, bytes unchanged; import-free initializer; not a fourth core |
| `knowledge/data/`, `harness/data/` | Packaged resources, placed by owner since K02 | Corpus under Knowledge; pack descriptions under Harness |

## Import gate

`tests/test_target_module_import_gate.py` fails on a new import of
`inferrsi.knowledge`, `inferrsi.benchmark`, or `inferrsi.apps` from anywhere
except application assembly, and on Knowledge or Benchmark importing Harness.
Application assembly includes `inferrsi.apps` and the three current flat
entries `cli.py`, `arguments.py` and `benchmark_operations.py`, listed by exact
file name as `APPLICATION_ENTRIES` in `tests/_gate_policy_support.py`.
`arguments.py` joined that list in R1: the CLI parser names
`inferrsi.knowledge` itself now that the root shells are gone. The listing is
temporary. A1 (#408) moves `cli.py` and `arguments.py` into `apps/cli/` and
removes both entries, and A2 removes the last one. Other flat modules retain
the same restrictions. The gate checks Benchmark task scripts as well as
module code.
`from inferrsi import knowledge` counts as an import of that core.
Same-core imports are allowed, including a relative import rewritten to an
absolute name such as `from .bar import VALUE` inside `knowledge/`. Each forbidden
importer and target pair is reported once. The only exceptions are exact pairs
read from `compatibility_pairs` in `docs/legacy-knowledge-manifest.json`.
Since R1 that list is empty, so the gate admits no exception.

The Benchmark package now provides resource discovery and task scripts. The
CLI and single-task application launcher assemble them with Harness; task
scripts receive execution support without importing another core.
"There is no exception list of current edges" described the tree before K01,
when the three package names were unused and no current edge needed an
exception. It was never a permanent ban on reviewed exceptions. From K01 until
R1 the nine exact first-wave pairs recorded below were the only compatibility
exceptions, scoped to that move. R1 retired them.

The gate scans `src/inferrsi/**` as the transfer graph. It resolves absolute,
relative, and `from package import name` imports, includes the parent-package
`__init__` that Python executes when a submodule is imported, both for import
targets and for the imported module itself (except the root `inferrsi`
package init, which runs for every import and is not a business edge), adds
the manifest-declared export edges, and computes the transitive closure. Since
K02 that scan also reaches the packaged helper scripts inside
`knowledge/data/**`, which are resources rather than importable modules: their
directories have no `__init__.py`. They import only the standard library and
external engines, so the Knowledge closure rule holds for them unchanged. K02
did not change the gate's scan scope or any closure rule. A dynamic import (`__import__`, `importlib.import_module`, or
`module_from_spec`) inside a checked closure is an undeclared edge and fails
closed, except for the exact resource execution declarations below.
Other dynamic forms (`getattr`, `exec`, `eval`, `runpy`, `pkgutil`)
are out of scope for this package. `tools/` and `tests/` are separate
registered consumers; this gate does not scan them.

The task integration declares these existing resource execution boundaries in
`tests/_gate_policy_support.py`, independently of the Knowledge compatibility
pairs. Each permits exactly one `importlib.util.module_from_spec` call, with the
listed local spec variable, in the named function or module scope. Other dynamic
calls, additional calls, adjacent modules and static cross-core imports remain
checked. These declarations do not make arbitrary candidate code isolated.

| Relative module | Scope | Local spec |
| --- | --- | --- |
| `harness.task_protocol` | `protocol` | `spec` |
| `benchmark.tasks.moe-forward-npu.benchmark` | module | `_process_spec` |
| `benchmark.tasks.moe-forward-npu.grader` | `load` | `spec` |
| `benchmark.tasks.qwen21-denoise-npu.benchmark` | `load` | `spec` |
| `benchmark.tasks.qwen3-tts-npu.benchmark` | module | `_evaluation_spec` |

The report adds a `runtime resource loaders` blocker when these loaders are
present and does not claim either complete isolation or new-core closure
isolation. R1 changed none of these five declarations; closing them is R3 (#412).

R1 (#412) deleted the three root forwarders of the old run chain and removed
their `LEGACY_RUN_FORWARDERS` registration from `tests/_gate_policy_support.py`.
With the seven Knowledge shells and root `inspection`, their names are now
`RETIRED_ROOT_MODULES` in that file. Nothing is registered for them:

- A file or package that returns under one of the eleven names is a violation
  by itself, whatever it contains.
- A returning forwarder or shell also fails as a root-file import of Apps or
  Knowledge, as any unlisted flat module does.
- Every checked closure still treats each name as an old root leaf. A
  Knowledge, Harness, Benchmark or Apps module that imports one fails, with or
  without a file behind the name.

No `legacy run forwarders` blocker exists any more.
[Retired root modules](#retired-root-modules) gives each replacement.

A clean result means no new cross-core import of those names. It does not mean
the modules are isolated. Isolation stays false while any one of these holds:
`knowledge/`, `benchmark/`, or `apps/` is absent or has no scannable
module; the compatibility allowlist
is non-empty; a temporary neutral-leaf importer still imports the leaf;
`harness/**` still imports Model or Infra,
directly or through another module; a declared runtime resource loader is
present; or the scan reports a violation. The three packages may appear in stages.
A clean graph for the new cores is reported separately as "new core business
closure isolated" and never sets overall `isolation_complete` to true.

On the tree after R1, `first_wave_report()` has no violation and three
blockers, so `isolation_complete` is false and R1 does not claim otherwise:

| Blocker | Cause | Closed by |
| --- | --- | --- |
| `temporary leaf importers: 1` | Root `arguments.py` reads `REPO_TYPES` from the neutral leaf | A1 (#408) |
| `harness reaches model/infra` (12 hits) | `agent_sessions`, `candidates`, `optimization`, `optimization_session`, `project` and `task_protocol` each reach `inferrsi.infra` and `inferrsi.infra.artifacts` | R2 (#412) |
| `runtime resource loaders: 5` | The five declared loaders in the table above | R3 (#412) |

R1 cleared the `allowlist` and `legacy run forwarders` blockers. The loaders
also keep `new_core_closure_isolated` false.

`knowledge-model-policy` stays the only required status. Until a separate
process decision makes this import gate required, every migration PR attaches
the gate result and does not describe it as branch protection.

## First-wave compatibility exceptions (Proposed)

Status after R1 (#412): none of these exceptions is in force. The seven root
shells are deleted and `compatibility_pairs` in the manifest is empty. This
section keeps the record of the nine pairs and the rules that still apply. The
heading is unchanged because other pages link to it.

These exceptions implement D018/D020 in
[`contracts/gate-policy-runstore-and-first-prs.md`](contracts/gate-policy-runstore-and-first-prs.md)
and
[`contracts/isolation-errors-and-cli.md`](contracts/isolation-errors-and-cli.md).
They stay Proposed until this policy passes formal architecture review. K01
must not start before that review accepts them.

Relative to `src/inferrsi/`, exactly nine (importer, target) pairs were
permitted from K01 until R1. None is permitted now:

| Importer | Exact target | Route |
| --- | --- | --- |
| `catalog` | `inferrsi.knowledge.catalog` | Named symbols only; not `repository_pack` |
| `catalog` | `inferrsi.resources.repository_packs` | `REPO_TYPES`, `repository_pack` |
| `_source_snapshot` | `inferrsi.knowledge._source_snapshot` | Same-named Knowledge module |
| `skill_catalog` | `inferrsi.knowledge.skill_catalog` | Same-named Knowledge module |
| `_skill_selection` | `inferrsi.knowledge._skill_selection` | Same-named Knowledge module |
| `research` | `inferrsi.knowledge.research` | Same-named Knowledge module |
| `knowledge_store` | `inferrsi.knowledge.knowledge_store` | Same-named Knowledge module |
| `knowledge_operations` | `inferrsi.knowledge.knowledge_operations` | Same-named Knowledge module |
| `infra.inspection` | `inferrsi.resources.repository_packs` | Direct, never through `catalog` or H |

These nine pairs were the only compatibility exceptions. A module prefix did
not authorize an adjacent module, and a second importer of an allowed
Knowledge target failed. C2 (#451) redirected the two data-leaf targets from
`inferrsi._repo_pack_data` to `inferrsi.resources.repository_packs`; the count
stayed nine. R1 (#412) then ended at zero pairs. The first eight rows were
edges of the seven root shells, two of them from root `catalog`, and retired
when R1 deleted those files. The ninth row is not a root-file edge:
`infra/inspection.py` imports the leaf and calls it, so no deletion removes
it. It left the allowlist and is the
[permanent rule below](#permanent-neutral-leaf-importer-rule-proposed).
The manifest keeps all nine records and root `catalog`'s two routes,
unchanged, under its last `revision_history` entry as
`retired_compatibility_pairs` and `retired_catalog_two_routes`.
An import of the leaf from inside `inferrsi.knowledge`, for example from
`inferrsi/knowledge/catalog.py`, is intra-closure and was never an exception.
The leaf's own import rule and `REPO_TYPES` object identity govern it.
`REPO_TYPES` is the same tuple object in the leaf,
`inferrsi.knowledge.catalog` and root `arguments.py`.

- **Shell shape.** No shell exists after R1. The rule is kept for a pair that
  review stages again, and `tests/test_first_wave_isolation_policy.py` still
  drives it with the nine retired pair records. A staged root leaf that imports
  its Knowledge target or the data leaf is a compatibility shell. It may
  contain only a module docstring,
  a `__future__` import, `ImportFrom` lines from its listed targets with
  listed names (an alias only as `name as name`), and an `__all__` that is a
  literal list of constant strings. Star imports, function or class bodies,
  module-level assignment, `__getattr__`, `sys.modules`, dynamic imports, and
  unlisted import lines or names fail. An old leaf that keeps a body after its
  Knowledge module exists also fails.
- **Data leaf.** `inferrsi.resources.repository_packs` imports only `json`,
  `importlib.resources`, `typing.Any`, and `from __future__ import
  annotations`, anywhere in the file. It defines only `REPO_TYPES` and
  `repository_pack`. Any `inferrsi.*` import or dynamic import in it fails.
  Python runs its parent initializer `resources/__init__.py` with every import
  of the leaf, so that initializer is a docstring only: any import, any other
  statement or a dynamic import there fails.
- **Closures.** A Knowledge module reaches nothing outside Knowledge except
  the data leaf with its import-free `inferrsi.resources` initializer and
  `inferrsi.contracts.json_v1`, the canonical encoder in the P0a
  design. The gate admits its exact RunSpec-only parent initialization closure,
  not arbitrary `contracts.*` or `resources.*` modules, and `contracts.evidence`
  is not a Knowledge input. Benchmark modules and every `inferrsi.harness.*` module reach no
  other core, no Apps module, and no old root leaf. Apps reaches no old root
  leaf. Since R1 an old root leaf is any of the eleven retired root module
  names, with or without a file behind it. `inferrsi.infra`
  reaches no Knowledge, Harness, Benchmark, or Apps module, so `infra` → root
  `catalog` → Knowledge fails while `infra` → the data leaf passes.
- **New H entries.** The registered entry modules are
  `inferrsi.harness.api`, `inferrsi.harness.execution_service`,
  `inferrsi.harness.input_binding`, `inferrsi.harness.local_process`,
  `inferrsi.harness.run_store`, and `inferrsi.harness.errors`. Each entry's
  closure is walked on the full graph. The gate does not infer other module
  paths from labels. Any `inferrsi.harness.*` module that exists is still
  checked against the closure rule above. The current mixed `harness` tree is
  not automatically an isolated core.
- **No residual.** The skill-evaluation split (#410) moved `export_bundle` to
  Apps and removed the registered `harness.skill_evaluation` → root
  `knowledge_operations` edge together with its exemption. Every harness
  module is walked on the full graph. A harness module that reaches an old
  root leaf fails, and so does each harness module that reaches the leaf
  through it. The report lists every remaining `harness` → Model or Infra
  path in `harness_model_infra`; the split modules `harness.skill_evaluation`,
  `harness.improvement`, `harness.artifact_sandbox` and `harness.atomic_json`
  have none.

The manifest records the base commit, each old leaf's file hash at that
commit, export names, audited definitions, consumer evidence, catalog's two
symbol routes, the required `infra.inspection` import rewrite, and the
original `REPO_TYPES` / `repository_pack` fragment from `catalog.py` with its
hash. K01 created `_repo_pack_data.py`, and the manifest locks its full-file
hash. K01 re-verified every recorded hash against its own base. Two leaves
had changed after P0b, so K01 re-recorded all seven hashes at its base and
keeps the P0b values in `revision_history`; that revision goes through formal
review with the move.

K02 moved `repo_packs/*/pack.json` to the Harness resource root, so the leaf's
one path expression and its locked `file_sha256` changed. The manifest records
that as `technical_leaf.resource_path_revision` with the old and new hashes and
the exact old and new line, keeps the P0b `original_fragment` for provenance,
and adds `current_fragment` for the body in the file today. The importlib anchor,
allowed imports, two symbols, top-level shape and the two permitted importers
are unchanged, so `infra` still gains no edge into Harness. That manifest
revision goes through formal architecture review with the K02 move; the
implementer does not self-approve it.

C2 (#451) moved the leaf from `src/inferrsi/_repo_pack_data.py` to
`src/inferrsi/resources/repository_packs.py` without changing a byte and
deleted the root file, with no forwarding shell or alias. The manifest relocks
`technical_leaf.module` and `technical_leaf.file` to the new location, records
the move as `technical_leaf.module_path_revision`, and points the
`neutral_leaf_export` route and the `catalog` and `infra.inspection` pairs at
the new module. `file_sha256` keeps its K02 value and is now checked against
the relocated file. The importlib anchor, allowed imports, two symbols,
top-level shape, `REPO_TYPES` object identity and the two permitted importers
are unchanged, so `infra` still gains no edge into Harness; the
`top_level_shape` text is restated for the relocated file and also names the
import-free parent initializer. The K01 and K02 records above stay as
provenance. The nine pairs remain, so the allowlist blocker remains. That
manifest revision requires formal architecture review; the implementer does
not self-approve it, and passing tests are not that review.

R1 (#412) deleted the seven root shells in the change that moved their last
consumers to `inferrsi.knowledge`, so the manifest's `compatibility_pairs` is
now empty and the allowlist blocker is gone. The C2 revision joined
`revision_history` with the nine retired pair records and root `catalog`'s two
routes, each unchanged, including the old root leaf hashes that K01 recorded.
`technical_leaf` keeps its module, file, locked `file_sha256`, allowed imports,
two symbols, top-level shape, both fragments and the K02 and C2 revision
records. It gains `permanent_importers` and `temporary_importers`, described
in the next section. The K01, K02 and C2 paragraphs above stay as provenance
and describe the tree at their own revisions. This R1 manifest revision
requires formal architecture review; the implementer does not self-approve
it, and passing tests are not that review.

## Permanent neutral-leaf importer rule (Proposed)

Outside `inferrsi.knowledge`, exactly one module may import
`inferrsi.resources.repository_packs`:

| Importer | Bound name | Exact import line |
| --- | --- | --- |
| `inferrsi.infra.inspection` | `repository_pack` | `from ..resources.repository_packs import repository_pack` |

This is D020's direct read: Infra gets one pack description without reaching
Knowledge or Harness. The rule is `LEAF_IMPORTERS` in
`tests/_gate_policy_support.py`, restated as
`technical_leaf.permanent_importers` in the manifest.
`tests/test_knowledge_compatibility_shells.py` requires the two to match, and
requires that line to be the file's only import under `inferrsi.resources`.
The rule is not a `compatibility_pairs` entry. It adds no blocker and does not
retire, because the importer is not a shell.

The rule covers that one importer, target, name and shape, and nothing wider:

- Any other module outside Knowledge that imports the leaf fails as a second
  importer. That includes another `infra` module, `infra/__init__.py`, an Apps,
  Harness or Benchmark module and any root file.
- In the declared importer, another leaf name, an alias, a star import, the
  leaf imported as a module object, an import below module level, a
  `sys.modules` use and a dynamic import each fail.
- An `inferrsi.resources.` prefix allows nothing: the package itself and a
  module beside the leaf are refused, for Knowledge too. The rule adds no
  `inferrsi.contracts.` allowance either; that package keeps its own exact
  module list.
- The leaf's locks are unchanged: its bytes and `file_sha256`, the listed
  standard-library imports, the two symbols, the top-level shape and the
  docstring-only parent initializer `resources/__init__.py`.
- A forwarding module under a retired name, a re-export through the leaf's
  initializer and a dynamic import from an undeclared module fail.

`tests/test_first_wave_isolation_policy.py` holds these negative controls. One
of them removes the declaration and shows that the scan then rejects the
`infra.inspection` edge, so the edge passes by the rule and not by a relaxed
scan.

One temporary entry sits beside the rule and is not part of it. Root `catalog`
is gone, so root `arguments.py` binds `REPO_TYPES` with
`from .resources.repository_packs import REPO_TYPES` for the `--repo-type`
choices. It is `TEMPORARY_LEAF_IMPORTERS` in the gate and
`technical_leaf.temporary_importers` in the manifest, held to the same exact
shape. It names root `arguments.py` only: the parser at an Apps path, or any
other Apps module, is not covered. While it exists the report carries the
`temporary leaf importers` blocker. A1 (#408) deletes root `arguments.py` and
removes the entry in the same change; how the moved parser reads `REPO_TYPES`
is decided by that change's review.

The permanent rule and the temporary entry are Proposed. Both require formal
architecture review. The implementer does not self-approve them, and passing
tests are not that review.

## Retired root modules

R1 (#412) deleted these eleven root modules with no forwarding shell,
`sys.modules` alias or import fallback:

| Retired root module | Canonical module |
| --- | --- |
| `inferrsi._skill_selection` | `inferrsi.knowledge._skill_selection` |
| `inferrsi._source_snapshot` | `inferrsi.knowledge._source_snapshot` |
| `inferrsi.catalog` | `inferrsi.knowledge.catalog`; `REPO_TYPES` and `repository_pack` from `inferrsi.resources.repository_packs` |
| `inferrsi.knowledge_operations` | `inferrsi.knowledge.knowledge_operations` |
| `inferrsi.knowledge_store` | `inferrsi.knowledge.knowledge_store` |
| `inferrsi.research` | `inferrsi.knowledge.research` |
| `inferrsi.skill_catalog` | `inferrsi.knowledge.skill_catalog` |
| `inferrsi.evaluation` | `inferrsi.apps.legacy.evaluation` |
| `inferrsi.execution` | `inferrsi.apps.legacy.run` |
| `inferrsi.reporting` | `inferrsi.apps.legacy.reporting` |
| `inferrsi.inspection` | `inferrsi.apps.inspection` |

Root `inspection.py` was not an alias. It bound the Infra facts API to the
host, and `apps/inspection.py` now holds that binding: `_command` is
`infra.commands.probe_command` and `repository_identity` is
`infra.targets.repository_identity`, both read from the module on each call,
so a test replaces either name there. `infra/inspection.py` is unchanged and
imports no Apps module. Root `execution.py` defined the two-argument
`run_experiment`; `apps.legacy.run.run_experiment` is that entry, and an
omitted `execute` or `snapshot` port is read from the module when the run
starts.

Importing a retired path raises `ModuleNotFoundError`, in external code too,
and a pickle that names a class or function by one no longer loads.
[`CHANGELOG.md`](../CHANGELOG.md) states the full import and pickle impact.
Frozen evidence is not rewritten; a historical campaign replays with its
original bundle.

The root now holds the ten files listed under
[Target modules](#target-modules). The final two-file root waits for the
A1/A2 (#408) and M1 (#452) moves.

## Old `run` exit codes

Frozen from
[`src/inferrsi/cli.py`](https://github.com/InferMatrixLab/InferRSI/blob/9f61a83f030bfa2ffe3b54eac1781593309d6380/src/inferrsi/cli.py#L412-L417)
as the compatibility text for a later integration check. This page does not
change that code.

| Condition | Exit |
| --- | --- |
| `status["verdict"]` is `PASS` | 0 |
| `status["verdict"]` is `FAIL` | 1 |
| Any other verdict, including missing | 2 |
| `OSError`, `ValueError`, `JSONDecodeError`, or `sqlite3.Error` via `parser.error` | 2 |

`tests/test_legacy_run_v0_frozen.py` runs the `run` command for pass, fail and
incomplete scenarios. It compares each exit code and the `evaluation.json` bytes
with goldens in `tests/fixtures/legacy_run_v0/`, which the chain wrote before
its evaluation moved to Benchmark. Missing evidence decides over a failed gate.

## Fixture locations

`tests/fixtures/skill-comparison/` and `tests/fixtures/skill-eval-pr/` hold
the skill-eval fixtures. `tests/fixtures/` also contains helpers such as
`skill_eval_pr_support.py` and `skill_eval_compare_support.py`. Do not
overwrite those helper modules. A later path change must update the tests,
docs, and workflow that cite these directories in the same change.
