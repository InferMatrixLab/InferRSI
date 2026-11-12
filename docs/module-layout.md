# Target module layout

This page records the directory rule for the integration slice. Only the
first-wave Knowledge move (K01) is implemented: `src/inferrsi/knowledge/` holds
the seven moved Knowledge bodies, and the old root modules are static
compatibility shells. No other package has been created or moved to satisfy it.
#371 remains the proposal for the Apps package path and is not accepted here.

## Target modules

The four target modules are peers: `knowledge`, `harness`, `benchmark`, and
`apps`. Knowledge, Harness, and Benchmark do not import one another. Apps is
the only assembler. `src/inferrsi/contracts.py` stays a `RunSpec`
re-export. It must not become a shared business-contracts package.

The current `src/inferrsi/harness/` tree is a mixed implementation. Its
presence is not the target Harness boundary and is not evidence that the four
modules are isolated.

Do not keep a sibling `data/` resource tier. Knowledge corpus later moves
under the Knowledge module. The internal corpus split is left to a future
Knowledge issue. `repo_packs/*/pack.json` is a target description and follows
the Harness slice. `observability/template.html` is a view template and
follows the Apps slice. Neither belongs in the corpus only because it sits
under `data/` today.

`src/` stays the import root. `tests/` and `tools/` stay at the repository
root. Also keep these root files where they are: `AGENTS.md` (entry contract),
`CHANGELOG.md`, `MANIFEST.in` (it grafts `src/inferrsi`, so a later resource
move must update packaging in that same slice), and `.agents/` (review skill).

Do not create empty `knowledge/`, `benchmark/`, or `apps/` directories in the
contract slice. Do not treat draft #338 as a reason to add a top-level
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
| `cli.py`, `arguments.py`, `__main__.py` | Future Apps entry, after #371 | Not moved |
| `knowledge_operations.py`, `knowledge_store.py`, `catalog.py`, `research.py`, `skill_catalog.py`, `_skill_selection.py`, `_source_snapshot.py` | Static compatibility shells since K01; bodies in `knowledge/` | Interfaces unchanged |
| `harness/` | Mixed legacy tree, not target isolation | Not redefined |
| `evaluation.py`, `model/validators/` | Benchmark-leaning checks | Not moved |
| `infra/`, `execution.py`, `runspec.py`, `inspection.py` | Seams used by the current tree | Not a fourth core |
| `reporting.py`, `summary_chart.py`, `evidence_paths.py` | Current report helpers | Not moved |
| `claim.py` | Verdict vocabulary used by current checks | Not moved and not a fourth core |
| `contracts.py` | `RunSpec` compatibility re-export | Must remain one module file |
| `data/` | Packaged resources, mixed kinds | Not relocated here |

## Import gate

`tests/test_target_module_import_gate.py` fails on a new import of
`inferrsi.knowledge`, `inferrsi.benchmark`, or `inferrsi.apps` from anywhere
except `inferrsi.apps`, and on Knowledge or Benchmark importing Harness.
`from inferrsi import knowledge` counts as an import of that core.
Same-core imports are allowed, including a relative import rewritten to an
absolute name such as `from .bar import VALUE` inside `knowledge/`. Each forbidden
importer and target pair is reported once. The only exceptions are the exact
first-wave pairs below, read from `docs/legacy-knowledge-manifest.json`.

"There is no exception list of current edges" described the tree before K01,
when the three package names were unused and no current edge needed an
exception. It was never a permanent ban on reviewed exceptions; since K01 the
exact first-wave pairs below are the only exceptions.

The gate scans `src/inferrsi/**` as the transfer graph. It resolves absolute,
relative, and `from package import name` imports, includes the parent-package
`__init__` that Python executes when a submodule is imported, both for import
targets and for the imported module itself (except the root `inferrsi`
package init, which runs for every import and is not a business edge), adds
the manifest-declared export edges, and computes the transitive closure. A dynamic import (`__import__`, `importlib.import_module`, or
`module_from_spec`) inside a checked closure is an undeclared edge and fails
closed. Other dynamic forms (`getattr`, `exec`, `eval`, `runpy`, `pkgutil`)
are out of scope for this package. `tools/` and `tests/` are separate
registered consumers; this gate does not scan them.

A clean result means no new cross-core import of those names. It does not mean
the modules are isolated. Isolation stays false while any one of these holds:
`knowledge/`, `benchmark/`, or `apps/` is absent or has no scannable
module; the compatibility allowlist
is non-empty; the registered residual `harness.skill_evaluation` → root
`knowledge_operations` exists; or `harness/**` still imports Model or Infra,
directly or through another module. The three packages may appear in stages.
A clean graph for the new cores is reported separately as "new core business
closure isolated" and never sets overall `isolation_complete` to true.

`knowledge-model-policy` stays the only required status. Until a separate
process decision makes this import gate required, every migration PR attaches
the gate result and does not describe it as branch protection.

## First-wave compatibility exceptions (Proposed)

These exceptions implement D018/D020 in
[`contracts/gate-policy-runstore-and-first-prs.md`](contracts/gate-policy-runstore-and-first-prs.md)
and
[`contracts/isolation-errors-and-cli.md`](contracts/isolation-errors-and-cli.md).
They stay Proposed until this policy passes formal architecture review. K01
must not start before that review accepts them.

Relative to `src/inferrsi/`, exactly nine (importer, target) pairs are
permitted:

| Importer | Exact target | Route |
| --- | --- | --- |
| `catalog` | `inferrsi.knowledge.catalog` | Named symbols only; not `repository_pack` |
| `catalog` | `inferrsi._repo_pack_data` | `REPO_TYPES`, `repository_pack` |
| `_source_snapshot` | `inferrsi.knowledge._source_snapshot` | Same-named Knowledge module |
| `skill_catalog` | `inferrsi.knowledge.skill_catalog` | Same-named Knowledge module |
| `_skill_selection` | `inferrsi.knowledge._skill_selection` | Same-named Knowledge module |
| `research` | `inferrsi.knowledge.research` | Same-named Knowledge module |
| `knowledge_store` | `inferrsi.knowledge.knowledge_store` | Same-named Knowledge module |
| `knowledge_operations` | `inferrsi.knowledge.knowledge_operations` | Same-named Knowledge module |
| `infra.inspection` | `inferrsi._repo_pack_data` | Direct, never through `catalog` or H |

These nine pairs are the only compatibility exceptions. A module prefix does
not authorize an adjacent module, and a second importer of an allowed
Knowledge target fails. `inferrsi._repo_pack_data` has exactly two permitted
importers outside Knowledge: root `catalog` and `infra.inspection`. An import
of that leaf from inside `inferrsi.knowledge`, for example from
`inferrsi/knowledge/catalog.py`, is intra-closure and not a tenth exception.
The leaf's own import rule and `REPO_TYPES` object identity govern it.
`REPO_TYPES` is the same tuple object through root `catalog`, the leaf, and
`inferrsi.knowledge.catalog`.

- **Shell shape.** An old root leaf that imports its Knowledge target or the
  data leaf is a compatibility shell. It may contain only a module docstring,
  a `__future__` import, `ImportFrom` lines from its listed targets with
  listed names (an alias only as `name as name`), and an `__all__` that is a
  literal list of constant strings. Star imports, function or class bodies,
  module-level assignment, `__getattr__`, `sys.modules`, dynamic imports, and
  unlisted import lines or names fail. An old leaf that keeps a body after its
  Knowledge module exists also fails.
- **Data leaf.** `inferrsi._repo_pack_data` imports only `json`,
  `importlib.resources`, `typing.Any`, and `from __future__ import
  annotations`, anywhere in the file. It defines only `REPO_TYPES` and
  `repository_pack`. Any `inferrsi.*` import or dynamic import in it fails.
- **Closures.** A Knowledge module reaches nothing outside Knowledge except
  the data leaf and `inferrsi._json_v1`, the canonical encoder in the P0a
  design. Benchmark modules and every `inferrsi.harness.*` module reach no
  other core, no Apps module, and no old root leaf, except the registered
  residual below. Apps reaches no old root leaf. `inferrsi.infra`
  reaches no Knowledge, Harness, Benchmark, or Apps module, so `infra` → root
  `catalog` → Knowledge fails while `infra` → the data leaf passes.
- **New H entries.** `harness.api` means `inferrsi.harness.api`.
  `execution_service` and `run_store` are entry labels; the gate does not
  infer module paths from those labels. Any `inferrsi.harness.*` module that
  exists is still checked against the closure rule above. The current mixed
  `harness` tree is not automatically an isolated core.
- **Residual.** The registered `harness.skill_evaluation` → root
  `knowledge_operations` edge stays listed and keeps overall isolation false.
  A second direct harness importer of that target fails, and a new H entry
  may not use the residual even through `skill_evaluation`. A mixed non-entry
  harness module may still reach that target only through the residual
  importer; that existing leak is not a new exception. The exemption is
  reachability after removing only that exact residual edge: another path
  to the same target is still a violation, regardless of traversal order.

The manifest records the base commit, each old leaf's file hash at that
commit, export names, audited definitions, consumer evidence, catalog's two
symbol routes, the required `infra.inspection` import rewrite, and the
original `REPO_TYPES` / `repository_pack` fragment from `catalog.py` with its
hash. K01 created `_repo_pack_data.py`, and the manifest locks its full-file
hash. K01 re-verified every recorded hash against its own base. Two leaves
had changed after P0b, so K01 re-recorded all seven hashes at its base and
keeps the P0b values in `revision_history`; that revision goes through formal
review with the move.

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

## Fixture locations

`tests/fixtures/skill-comparison/` and `tests/fixtures/skill-eval-pr/` hold
the skill-eval fixtures. `tests/fixtures/` also contains helpers such as
`skill_eval_pr_support.py` and `skill_eval_compare_support.py`. Do not
overwrite those helper modules. A later path change must update the tests,
docs, and workflow that cite these directories in the same change.
