# Target module layout

Four peer modules own the runtime. Knowledge owns retrieval, Harness owns
execution and retention, Benchmark owns assessment, and Apps composes these
through CLI and Python entry points. [Architecture](architecture.md) describes
the dependencies. This page defines placement, import rules and compatibility.
The [retired path inventory](#retired-root-modules) records the old package
root and the [Apps migration inventory](apps-module-migrations.json) records
compatibility paths that still exist.

## Module documentation

A top-level module with its own responsibility or extension points benefits
from a short README next to the code. Describe what it owns, where callers
enter, the key invariants an extension must preserve, and where to find the
relevant tests and design. The [Harness README](../src/inferrsi/harness/README.md)
is an example. Small internal packages can be covered by their parent README.

Keep a local design decision in the module README when a short explanation is
enough. A module with a longer lifecycle, rationale or failure model can link to
a `DESIGN.md` beside its README. Document designs shared by several modules in
the relevant topic under `docs/`. [Architecture](architecture.md) owns
cross-module boundaries, dependencies and composition. [Contracts](contracts/)
own versioned interfaces, schemas and evidence rules. Link to the owning design
or contract from the module README.

## Target modules

### Apps storage migration

[Apps storage](../src/inferrsi/apps/README.md) owns the canonical storage
definitions. The four former paths in the
[migration inventory](apps-module-migrations.json) export the same public
objects. Old pickles resolve through the exports. New pickles and patches to
private helpers use the canonical modules. Storage has no dependency on handoff.
The retired root `inferrsi.evidence_paths` stays unavailable. Shim removal requires
a separate review with consumer migration, wheel and plugin validation, and a
first removal version.

### Apps handoff migration

The three former paths in the [migration inventory](apps-module-migrations.json)
export the canonical objects. `apps.api.CandidateProvider` is the class defined
in `apps/handoff/candidate_provider.py`. `EvaluationPort` is defined in `apps/api.py`.
The handoff initializer and compatibility imports perform no Knowledge reads,
device probes, process launches or service registration. `EvidenceCapture` is
defined in `apps/handoff/evidence_capture.py` and exposed through `apps.api`.

### Apps workflows migration

The former Apps paths in the [migration inventory](apps-module-migrations.json)
export the canonical workflow objects. The engineering verifier retains its
file and python -m entry points through a static import and a main guard.
New pickles and patches to private helpers use the canonical paths. Workflow
imports perform no data reads, probes, process launches or service registration.

New optimization plans and evaluation controller snapshots fingerprint the
canonical source files. To inspect or resume a frozen pre-move run, including
`status` and `recover`, use its original runtime under the
[release-boundary recovery rules](optimization-workflow-unification.md#release-boundary-recovery).

### Apps integrations migration

The [migration inventory](apps-module-migrations.json) describes package shims
and their exports. The old Cannbot package exposes its own project shim, whose
public objects resolve to the canonical definitions. Imports in either order
preserve these module identities. Private helper patches target the canonical
modules. Importing the adapters performs no grant reads or worker launches.

Launchers select the canonical sibling worker with the approved interpreter and
the existing `-I -B` flags. Each worker uses standard-library-only imports and
loads without InferRSI installed. The legacy worker shims remain importable.
Run the canonical worker file directly. To serve the project's approved MindIE
read tools over stdio MCP, run `inferrsi mindie serve`.

Keep Anthropic's `request_guard.py` beside `anthropic_agent.py`. The agent
loads the guard by file path, and the edit adapter copies it into the run.

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
nothing. C2 (#451) moved these out of root
`_repo_pack_data.py` and `evidence_paths.py` and deleted both root files, with
no forwarding shell or alias.

The package root has exactly two tracked files, `__init__.py` and `__main__.py`,
as pinned by [the inventory test](../tests/test_package_root_inventory.py).
The build-generated `_version.py` is wheel metadata. New implementation belongs
in an owning subpackage. See [retired root modules](#retired-root-modules) for
the former paths and their replacements.

There is no sibling `data/` resource tier. K02 moved the Knowledge corpus to
`src/inferrsi/knowledge/data/` and the `repo_packs/*/pack.json` target
descriptions to `src/inferrsi/harness/data/`. Dashboard view templates live in
`apps/views/`.

The move is physical only. Bundle resource keys, dependency keys and the pinned
`source_files` paths in generated records keep their recorded spelling, so
content bytes, hashes and Bundle revisions are unchanged. `_source_snapshot.LIBRARY`
names the corpus at its pinned `source_revision`, not the current checkout path;
repointing it regenerates every record and needs an explicit new revision.

`src/` stays the import root. `tests/` and `tools/` stay at the repository
root. Also keep these root files where they are: `AGENTS.md` (entry contract),
`CHANGELOG.md`, `MANIFEST.in` (it grafts `src/inferrsi`, so a later resource
move must update packaging in that same slice), and `.agents/` (review skill).

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

Use the source-adjacent READMEs for current implementation ownership and
extension entry points.

- [Apps](../src/inferrsi/apps/README.md) covers assembly, host adapters and result delivery.
- [Benchmark](../src/inferrsi/benchmark/README.md) covers task discovery and independent assessment.
- [Harness](../src/inferrsi/harness/README.md) covers execution, retention and recovery.
- [Knowledge](../src/inferrsi/knowledge/README.md) covers package data, lookup and reads.

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
`infra/artifacts.py` stayed for its other users until #498 removed `infra/`. No Harness module reaches
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
  names, with or without a file behind it. Since #498 the names `inferrsi.infra`
  and `inferrsi.model` are retired as a whole, so any import of either fails. Before
  that, `inferrsi.infra` reached no Knowledge, Harness, Benchmark, or Apps module.
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
  another Apps module, a Harness or Benchmark module and any root file.
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
| `inferrsi.mindie_project` | `inferrsi.apps.integrations.mindie.project` |
| `inferrsi.mindie_context` | `inferrsi.apps.integrations.mindie.context` |
| `inferrsi.mindie_mcp` | `inferrsi.apps.integrations.mindie.mcp` |
| `inferrsi._mindie_read_worker` | `src/inferrsi/apps/integrations/mindie/read_worker.py`, a file run by path and not imported |

The four files moved with their code unchanged except the imports that name
their neighbours and the package version. `apps/integrations/mindie/__init__.py` imports
nothing and does not re-export `__version__`; `mcp.py` reads it with
`from .... import __version__` after the integrations move. The worker is still started as
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
