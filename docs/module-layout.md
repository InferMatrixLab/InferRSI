# Target module layout

This page records the directory rule for the integration slice. The first-wave
Knowledge move (K01) is implemented: `src/inferrsi/knowledge/` holds the seven
moved Knowledge bodies. R1 (#412) deleted the seven static root compatibility
shells that K01 left, so those names import only from `inferrsi.knowledge`.
The engineering task contribution now implements `benchmark/registry.py`
and `benchmark/tasks/`. The CLI package `apps/cli/` and
`apps/workflows/benchmark_operations.py` assemble this slice. The former `observability/`
package is dissolved. Its
campaign records, traces, logs and profile captures are in `harness/records/`,
its dashboard views and templates are in `apps/views/`, and the
collected-context projection is in `knowledge/context_projection.py`.
#371 owns the Apps composition. Its accepted directory follow-up
[#490](https://github.com/InferMatrixLab/InferRSI/issues/490) groups the implemented
storage, handoff and workflows slices described below.

The old `run` chain is split by owner. Its gates are in
`benchmark/legacy_run_v0.py`, its execution facts stay in `harness/`, and
`apps/legacy/` composes them with the report. That path was established by
the earlier confirmed split.
`apps/cli/` imports the old run only inside its `run` command, so the other
commands, including ordinary optimization, still load no Benchmark module.
R1 deleted the three root forwarders of that chain (`evaluation.py`,
`execution.py` and `reporting.py`), and the CLI imports `apps/legacy/` itself.

## Target modules

### Apps storage migration

`apps/storage/` owns `archive.py`, `artifact_reader.py`, `result.py` and
`evidence_layout.py`. API, handoff, view and delivery consumers import these
canonical implementations. Storage has no direct or transitive import back to
handoff. The package initializer imports nothing.

The four old Apps paths remain explicit static exports of the same public
objects. [apps-module-migrations.json](apps-module-migrations.json) records the
implemented paths, exports and consumers. Private-helper imports and test
patches must target the canonical module. Old Apps pickle references load
through these exports; new pickles use the canonical definition. The retired
root `inferrsi.evidence_paths` has no alias and remains unavailable.

Shim removal requires a separate reviewed PR recording consumer migration,
wheel and plugin validation, and the first removal version. Integrations and
integrated acceptance remain subsequent #490 slices.

### Apps handoff migration

`apps/handoff/bridge.py` binds fixed preparations to execution specifications
and projects saved records into evidence. `context_provider.py` delivers actual
Knowledge bytes and pins for Harness sealing. `candidate_provider.py` plans
generation and collects candidates from fixed Harness records. These modules
consume `apps/storage/`; storage never imports back into handoff.

The three former Apps paths retain explicit public exports recorded in the
[migration inventory](apps-module-migrations.json). `apps.api.CandidateProvider`
and the former provider module export the one class defined in
`apps/handoff/candidate_provider.py`. `EvaluationPort` remains defined in
`apps/api.py`. The handoff initializer imports nothing, and importing either
path performs no Knowledge reads, device probes, process launches or service
registration. Harness owns the sealed context, original attempt and request
digest; these ownership boundaries and DTOs remain unchanged.

### Apps workflows migration

`apps/workflows/` owns `campaign.py`, `benchmark_operations.py`, `benchmark_compare.py`,
`improvement.py`, `skill_evaluation.py` and `skill_eval_engineering.py`. It joins Knowledge reads,
Harness execution and Benchmark judgments. CLI commands, views and evaluation
tools import these canonical implementations. Its initializer imports nothing;
imports of either path perform no data reads, probes, process launches or service
registration. Signatures, return values and retained-record schemas are unchanged.

The six former Apps paths keep explicit exports from the same
[migration inventory](apps-module-migrations.json). The engineering verifier also
keeps its former file and `python -m` entry points through a static absolute import
and a `__main__` guard, recorded as `script_entry` in the inventory. Other shims
contain only their docstring, explicit import and literal `__all__`. New pickles
use the canonical module; patches to helpers or imported dependencies target it.

`benchmark_compare.py`, introduced by #501 while this migration was in progress,
composes paired benchmark plans, native host handoffs, collection and reports.
It returns host actions; the Agent performs the native calls. Its previous Apps
path retains the same public functions and configuration objects. The comparison
rules remain in Benchmark and the report view remains in `apps/views/`.

New optimization plans and evaluation controller snapshots fingerprint the
canonical source files, not the compatibility shims. A frozen pre-move runtime
map remains incompatible with a new runtime, including for `status` and `recover`.
Do not edit a frozen plan to bypass this check. Use the original pinned runtime
to resume, following [release-boundary recovery](optimization-workflow-unification.md#release-boundary-recovery).

### Core and technical packages

The four target modules are peers: `knowledge`, `harness`, `benchmark`, and
`apps`. Knowledge, Harness, and Benchmark do not import one another. Apps is
the only assembler. `src/inferrsi/contracts/__init__.py` re-exports only
`RunSpec`, defined once in `contracts/runspec.py`. The technical-only package
also owns `json_v1.py`, `claim.py` and `evidence.py`; it contains no shared
business DTOs and performs no core or host initialization.

`contracts/evidence.py` holds the evidence segment names and the per-campaign
path rules. It only builds paths and does no filesystem I/O. Creating the
directories is `apps/storage/evidence_layout.py`, which reuses those rules, so `mkdir`
stays out of the contracts package. `resources/repository_packs.py` is the
neutral repository-pack facade: the one `REPO_TYPES` tuple and the `pack.json`
reader. It imports no `inferrsi` module, and `resources/__init__.py` imports
nothing. Neither package is a fourth core. C2 (#451) moved these out of root
`_repo_pack_data.py` and `evidence_paths.py` and deleted both root files, with
no forwarding shell or alias.

The flat package root is retired. `tests/test_package_root_inventory.py` pins the
root to an exact file set: 23 tracked files after C1, 21 after C2, 10 after R1
(#412), 8 after A1 (#408), 6 after A2 (#408) and the final two after M1 (#452).
The two are `__init__.py` and `__main__.py`. M1 moved root `mindie_project.py`,
`mindie_context.py`, `mindie_mcp.py` and `_mindie_read_worker.py` to
`apps/mindie/project.py`, `context.py`, `mcp.py` and `read_worker.py` and deleted
the four root files with no forwarding shell or alias. A2 moved root
`summary_chart.py` to
`apps/views/summary_chart.py` and root `benchmark_operations.py` to
`apps/benchmark_operations.py` and deleted both root files the same way. The workflows
slice later moved that Apps implementation into `apps/workflows/`. A1 moved root `cli.py` and
`arguments.py` to `apps/cli/__init__.py` and `apps/cli/arguments.py` and
deleted both root files. A new root file now fails the guard, so a later module
belongs in a subpackage. The build-generated `_version.py` is ignored wheel
metadata, not a tracked root file. [Retired root modules](#retired-root-modules)
lists the eleven paths that R1 removed, the two that A1 removed, the two that A2
removed and the four that M1 removed.

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
file is not the Apps implementation owned by #371.
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
| `apps/cli/` (`__init__.py`, `arguments.py`), root `__main__.py` | Apps CLI entry and its parser | A1 (#408) moved root `cli.py` and `arguments.py` here; the entry is `inferrsi.apps.cli:main`, and `__main__.py` only delegates to it |
| `apps/workflows/benchmark_operations.py` | Single-task application launcher | A2 (#408) moved the root launcher into Apps; #490 groups its implementation under workflows. Resolves a task entry and invokes the Harness runner; ordinary projects do not use it |
| `benchmark/registry.py`, `benchmark/tasks/` | Task discovery, definitions and specialized rules | Task-specific quality and measurement code stays with each task |
| `harness/optimization_session.py`, `harness/project.py`, `harness/task_protocol.py` | Shared preparation, execution and retained-result assessment | CLI supplies task resources and knowledge access; ordinary project lifecycle does not import Benchmark |
| `harness/optimization.py`, `harness/candidates.py`, `harness/usage.py` | Shared project and packaged-task lifecycle | Injected execution/assessment; declared file/directory candidates, selection direction and exact/up-to rounds |
| `harness/agent_sessions.py` | Native host handoff records | Freezes requests and retains native IDs and exported observations; the initiating Agent calls host tools |
| `harness/skill_evaluation.py`, `harness/artifact_sandbox.py`, `harness/improvement.py`, `harness/atomic_json.py` | Skill-evaluation host adapter, trial execution and retention, sandbox replay, search progression | Verdict rules and task definitions arrive as injected values; no Model, Infra, Knowledge, Benchmark or Apps import |
| `benchmark/skill_evaluation.py`, `benchmark/skill_eval_diagnostic.py`, `benchmark/skill_eval_engineering.py`, `benchmark/improvement.py` | Skill-evaluation criteria, task definitions and acceptance rules | Pure judgments over retained facts; no Harness import and no process start |
| `apps/workflows/skill_evaluation.py`, `apps/workflows/skill_eval_engineering.py`, `apps/workflows/improvement.py` | Composed skill-evaluation entries | Join Knowledge reads, Harness execution and Benchmark rules behind the signatures that `harness/` held before the split |
| `knowledge/knowledge_operations.py`, `knowledge/knowledge_store.py`, `knowledge/catalog.py`, `knowledge/research.py`, `knowledge/skill_catalog.py`, `knowledge/_skill_selection.py`, `knowledge/_source_snapshot.py` | The seven Knowledge implementations, moved by K01 | Interfaces unchanged; the same-named root shells were deleted by R1 |
| `harness/records/` | Campaign manifests, traces, logs, profile captures and delivered-context captures | Imports no Knowledge or Apps module; `apps/workflows/campaign.py` supplies the backend names, the selection default and the context projection |
| `apps/views/`, `apps/workflows/campaign.py` | Dashboard views, templates and the Knowledge-to-records connection | Apps composition under #371; campaign composition is grouped under workflows by #490 |
| `apps/mindie/` (`project.py`, `context.py`, `mcp.py`, `read_worker.py`) | The local MindIE adapter: project grant, stdio MCP, context export and the read worker | M1 (#452) moved the four root MindIE files here; no Harness, Knowledge or Infra module names MindIE, and the initializer imports nothing |
| `harness/` | Mixed legacy tree, not target isolation | Not redefined |
| `harness/runner.py`, `harness/scenarios/external.py`, `harness/atomic_json.py` | Old run execution facts and Harness-owned JSON writes | Ports injected; no Model edge, and no Infra edge except the local process executor |
| `benchmark/legacy_run_v0.py`, `benchmark/sampling.py` | Old run gates and metric validation; image/video sample collection | Imports only `benchmark/metrics.py`; owns its rule inputs and verdict labels |
| `apps/legacy/` | Old run composition, old `evaluate` entry and HTML report | Supplies the Git source snapshot from `apps/host/targets`; remains in Apps |
| `apps/inspection.py` | Prepared-environment inspection bound to this host | Binds the `apps/host/inspection.py` facts API to `apps.host.commands.probe_command` and `apps.host.targets.repository_identity`; replaces root `inspection.py`, which R1 deleted with the three old-run root forwarders |
| `benchmark/metrics.py`, `benchmark/validators/`, `benchmark/artifacts.py` | The metric contract, the Flare and image quality checks, and Benchmark's own file digests and JSON writes | #498 slice 1 moved the first two from `model/protocols/metrics.py` and `model/validators/`, with no forwarder or alias; the gate fails any import of the old paths |
| `harness/serving/` (`server.py`, `http.py`, `image.py`) | Supervised serving processes, the timed JSON transport and the image request client | #498 slice 2 moved them from `infra/processes.py`, `infra/http.py` and `model/protocols/image.py` with no forwarder or alias; the initializer imports nothing, and the gate fails any import of the old paths |
| `apps/host/` (`inspection.py`, `commands.py`, `environment.py`, `platforms/`, `targets/`) | The host environment facts API, bounded probes, dependency facts, device discovery and source identity | #498 slice 3a moved them from Infra with no forwarder or alias; the package keeps Infra's limit and reaches no Knowledge, Harness or Benchmark module; `inspection.py` is the permanent leaf importer |
| `apps/artifacts.py` | Apps's own file digests, file lock and JSON evidence writes | #498 slices 3b and 5 gave Apps this copy and deleted `infra/`; `tests/test_artifact_helper_copies.py` keeps it equal to the Harness and Benchmark copies |
| `apps/integrations/anthropic/` (`anthropic_agent.py`, `anthropic_edit_agent.py`, `request_guard.py`) | The bounded Anthropic Messages agent, its edit-and-check protocol and the request authorization broker | #498 slice 4 moved them from `model/` with no forwarder or alias; only the path-valued `SOURCE` constants changed. The worker loads `request_guard.py` by file location, so it must ship next to the agent |
| `apps/views/summary_chart.py` | Stdlib SVG gain chart and report figure spec | A2 (#408) moved root `summary_chart.py` here; the renderer, its specification checks and its `main` are unchanged, and `tools/campaign_summary_chart.py` calls it |
| `contracts/` (`runspec.py`, `json_v1.py`, `claim.py`, `evidence.py`) | Technical-only contracts: RunSpec, canonical JSON, verdict vocabulary, evidence segment and path rules | Exact module set; the initializer re-exports only `RunSpec`; not a fourth core |
| `apps/storage/evidence_layout.py` | Evidence directory creation over the `contracts/evidence.py` path rules | The `mkdir` half of former root `evidence_paths.py`; host I/O stays in Apps |
| `apps/storage/` (`archive.py`, `artifact_reader.py`, `result.py`) | Fixed artifact publication and reads; normalized AppsResultV1 | #490 storage slice; the old Apps modules retain explicit public exports |
| `resources/repository_packs.py` | Neutral `REPO_TYPES` and `repository_pack` facade | Former root `_repo_pack_data.py`, bytes unchanged; import-free initializer; not a fourth core |
| `knowledge/data/`, `harness/data/` | Packaged resources, placed by owner since K02 | Corpus under Knowledge; pack descriptions under Harness |

## Import gate

`tests/test_target_module_import_gate.py` fails on a new import of
`inferrsi.knowledge`, `inferrsi.benchmark`, or `inferrsi.apps` from anywhere
except application assembly, and on Knowledge or Benchmark importing Harness.
Application assembly is the `inferrsi.apps` package, identified by its first path
segment. No root file is application assembly: A1 (#408) moved `cli.py` and
`arguments.py` into `apps/cli/`, A2 (#408) moved `benchmark_operations.py` into
`apps/`, and with that last move the exact-file `APPLICATION_ENTRIES` listing in
`tests/_gate_policy_support.py` is removed. A root file that returns under any of
those names is not admitted. Other flat modules retain
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
closed, except for by-path loading in task bundle programs, described below.
Other dynamic forms (`getattr`, `exec`, `eval`, `runpy`, `pkgutil`)
are out of scope for this package. `tools/` and `tests/` are separate
registered consumers; this gate does not scan them.

#412 R3 retired the five temporary resource-loader declarations and their
`runtime resource loaders` blocker. Three of the five were removed:

- `harness.task_protocol` no longer loads task code. Each protocol operation
  (`validate_arguments`, `arguments`, `assess`) runs `harness/protocol_child.py`
  as `python -I -B` in its own process group or Windows Job under a deadline, and
  answers with one strict JSON envelope on a private copy of stdout. The child
  imports only the standard library and compiles the exact protocol bytes it has
  checked against the frozen SHA-256. After every operation the last 4 KiB of the
  child's stderr is copied to the caller's stderr; size limits apply when Harness
  reads the child's output files, and the deadline bounds the run. This is an
  interpreter and process boundary, not a filesystem or network sandbox.
- `moe-forward-npu` folded its sibling `processes.py` into `benchmark.py`, and
  `qwen3-tts-npu` folded its sibling `evaluation.py` into `benchmark.py`. The
  bundles no longer load a sibling module by path, and a bundle prepared before
  R3 is refused by its frozen digests and must be prepared again.

An evaluator that times submitted code must call it in its own process, so it loads
the frozen run file by path. The gate decides this by file location, not by task:

- A **task bundle program** is a file directly inside `benchmark/tasks/<bundle>/`
  where that directory has no `__init__.py`. Python could still import such a file
  through a namespace package, so the gate rejects every import of a bundle program
  from package code; Harness and Apps run it as its own process.
- In a bundle program, `importlib.util.module_from_spec` calls are admitted. Every
  name-based lookup still fails there: `__import__`, `importlib.import_module`,
  `module_from_spec` reached by another spelling, and `find_spec` in any spelling,
  including an alias. Static imports of Knowledge, Harness or Apps fail as in any
  Benchmark module.
- Everywhere else, including a deeper file inside a bundle, a bundle directory with an
  `__init__.py`, `knowledge/data/**` scripts, Harness and Apps, the same call is a
  dynamic import and fails.

No table lists tasks or functions, so a new bundle needs no gate change. Today the
MoE grader and the Qwen21 evaluator load this way. Their callers verify the file
identities (`identity.json` in both tasks), and each load returns a fresh module that
is not registered in `sys.modules`. The gate cannot see the path a bundle program
loads, so the rule is a location-based static policy about where by-path loading is
allowed, not a process or sandbox guarantee for candidate code. `first_wave_report().runtime_execution` lists every
bundle program that loads by path, so the static `isolation_complete` result never
reads as runtime isolation.

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

A clean result means no new cross-core import of those names. Isolation stays false
(`isolation_complete`, a static import-closure result) while any one of
these holds: `knowledge/`, `benchmark/`, or `apps/` is absent or has no scannable
module; the compatibility allowlist is non-empty; `harness/**` still imports Model
or Infra, directly or through another module; or the scan reports a violation. A
clean graph for the new cores is reported separately as "new core business closure
isolated". Neither flag says anything about what frozen task or candidate code does
once it runs: that is `runtime_execution`.

On the tree after R3 (#412), `first_wave_report()` has no violation and no
blocker, `new_core_closure_isolated` and `isolation_complete` are both true, and
`runtime_execution` lists the two bundle programs that load files by path.

R1 cleared the `allowlist` and `legacy run forwarders` blockers, and A1 cleared
the `temporary leaf importers` blocker that R1 left for root `arguments.py`. R2
cleared `harness reaches model/infra` (12 hits): `agent_sessions`, `candidates`,
`optimization`, `optimization_session`, `project` and `task_protocol` each reached
`inferrsi.infra` and `inferrsi.infra.artifacts`. They now take `digest`, `sha256`
and `file_lock` from `harness/artifact_primitives.py` and `atomic_write_json` from
`harness/atomic_json.py`, whose function bodies equal those in `infra/artifacts.py`.
`infra/artifacts.py` stays for its other users. No Harness module reaches
`inferrsi.infra` or `inferrsi.model`. R3 cleared `runtime resource loaders: 5`.

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
unchanged, under the C2 entry of its `revision_history` as
`retired_compatibility_pairs` and `retired_catalog_two_routes`.
An import of the leaf from inside `inferrsi.knowledge`, for example from
`inferrsi/knowledge/catalog.py`, is intra-closure and was never an exception.
The leaf's own import rule and `REPO_TYPES` object identity govern it.
`REPO_TYPES` is the same tuple object in the leaf,
`inferrsi.knowledge.catalog` and the moved parser `inferrsi.apps.cli.arguments`.

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
records. With R1 it gained `permanent_importers` and `temporary_importers`, described
in the next section; A1 (#408) removed the second and kept the removed record
in `revision_history`. The K01, K02 and C2 paragraphs above stay as provenance
and describe the tree at their own revisions. This R1 manifest revision
requires formal architecture review; the implementer does not self-approve
it, and passing tests are not that review.

## Permanent neutral-leaf importer rule (Proposed)

Outside `inferrsi.knowledge`, exactly one module may import
`inferrsi.resources.repository_packs`:

| Importer | Bound name | Exact import line |
| --- | --- | --- |
| `inferrsi.apps.host.inspection` | `repository_pack` | `from ...resources.repository_packs import repository_pack` |

This is D020's direct read: the host facts API gets one pack description
without reaching Knowledge or Harness. #498 slice 3a moved the importer from
`inferrsi.infra.inspection` with its file, in one change: the old name is
retired and is never admitted beside the new one, and the move needs the same
formal architecture review as the rule. The rule is `LEAF_IMPORTERS` in
`tests/_gate_policy_support.py`, restated as
`technical_leaf.permanent_importers` in the manifest.
`tests/test_knowledge_compatibility_shells.py` requires the two to match, and
requires that line to be the file's only import under `inferrsi.resources`.
The rule is not a `compatibility_pairs` entry. It adds no blocker and does not
retire, because the importer is not a shell.

The rule covers that one importer, target, name and shape, and nothing wider:

- Any other module outside Knowledge that imports the leaf fails as a second
  importer. That includes another `apps.host` module, `apps/host/__init__.py`,
  another Apps module, a Harness, Benchmark or Infra module and any root file.
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
`apps.host.inspection` edge, so the edge passes by the rule and not by a relaxed
scan.

One temporary entry sat beside the rule from R1 until A1 (#408) and was never
part of it. Root `catalog` was gone, so root `arguments.py` bound `REPO_TYPES`
with `from .resources.repository_packs import REPO_TYPES` for the `--repo-type`
choices. It was `TEMPORARY_LEAF_IMPORTERS` in the gate and
`technical_leaf.temporary_importers` in the manifest, and the report carried a
`temporary leaf importers` blocker. A1 deleted root `arguments.py` and removed
the entry, the gate constant and the blocker in the same change. Nothing
replaced them. The moved parser `apps/cli/arguments.py` reads `REPO_TYPES` from
`inferrsi.knowledge.catalog`, which binds the one tuple object from the leaf.
The `--repo-type` choices are still that object, and the Apps parser imports no
`inferrsi.resources` module. An Apps module that imports the leaf itself fails
as a second importer, the moved parser included. The manifest keeps the removed
entry unchanged in `revision_history`.

The permanent rule is Proposed and requires formal architecture review. So does
the A1 choice to read `REPO_TYPES` through Knowledge. The implementer does not
self-approve either, and passing tests are not that review.

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
`apps.host.commands.probe_command` and `repository_identity` is
`apps.host.targets.repository_identity`, both read from the module on each call,
so a test replaces either name there. `apps/host/inspection.py`, moved from
Infra by #498 slice 3a, imports no Apps module outside `apps/host/`. Root `execution.py` defined the two-argument
`run_experiment`; `apps.legacy.run.run_experiment` is that entry, and an
omitted `execute` or `snapshot` port is read from the module when the run
starts.

Importing a retired path raises `ModuleNotFoundError`, in external code too,
and a pickle that names a class or function by one no longer loads.
[`CHANGELOG.md`](../CHANGELOG.md) states the full import and pickle impact.
Frozen evidence is not rewritten; a historical campaign replays with its
original bundle.

A1 (#408) deleted two more root modules the same way:

| Retired root module | Canonical module |
| --- | --- |
| `inferrsi.cli` | `inferrsi.apps.cli` |
| `inferrsi.arguments` | `inferrsi.apps.cli.arguments` |

The `inferrsi` console script and `python -m inferrsi` call
`inferrsi.apps.cli:main`, and every command, flag, exit code and output byte is
unchanged. A test replaces a CLI name such as `_knowledge_reader` or `files` on
`inferrsi.apps.cli`.

A2 (#408) deleted two more root modules the same way:

| Retired root module | Canonical module |
| --- | --- |
| `inferrsi.summary_chart` | `inferrsi.apps.views.summary_chart` |
| `inferrsi.benchmark_operations` | `inferrsi.apps.workflows.benchmark_operations` |

`tools/campaign_summary_chart.py` keeps its command line and calls
`inferrsi.apps.views.summary_chart:main`, so its arguments, exit codes, output and
the SVG and Markdown bytes it writes are unchanged. The dashboard, the HTML report
and the CLI `benchmarks run` command import the canonical modules.

M1 (#452) deleted the four root MindIE files the same way:

| Retired root module | Canonical module or file |
| --- | --- |
| `inferrsi.mindie_project` | `inferrsi.apps.mindie.project` |
| `inferrsi.mindie_context` | `inferrsi.apps.mindie.context` |
| `inferrsi.mindie_mcp` | `inferrsi.apps.mindie.mcp` |
| `inferrsi._mindie_read_worker` | `src/inferrsi/apps/mindie/read_worker.py`, a file run by path and not imported |

The four files moved with their code unchanged except the imports that name
their neighbours and the package version. `apps/mindie/__init__.py` imports
nothing and does not re-export `__version__`; `mcp.py` reads it with
`from ... import __version__`. The worker is still started as
`python -I -B read_worker.py` with a private working directory, a 20 second limit
and a 2 MiB cap, opens SQLite read-only, imports only the standard library at
the top level and takes `mindie_knowledge` inside `read()`. It is not described
as standard-library-only overall. The grant file, its explicit opt-in, the
recorded read receipts and the OBS layout are unchanged. The `inferrsi mindie`
and `inferrsi campaign import-mindie` commands, the Codex configuration in
[codex-plugin.md](codex-plugin.md) and the MCP server name are unchanged.

The root now holds exactly the two files `__init__.py` and `__main__.py`. The
build-generated `_version.py` is separate wheel metadata.

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
