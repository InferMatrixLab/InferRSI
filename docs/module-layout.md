# Target module layout

This page records the directory rule for the integration slice. It is not an
implemented migration. No package has been created or moved to satisfy it.
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
| `knowledge_operations.py`, `knowledge_store.py`, `catalog.py`, `research.py`, `skill_catalog.py`, `_skill_selection.py` | Knowledge behavior and corpus readers | Interfaces unchanged |
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
importer and target pair is reported once. There is no exception list of
current edges: those three package names are unused on this tree, so the
violation list is empty.

A clean result means no new cross-core import of those names. It does not mean
the modules are isolated. Isolation stays false while `knowledge/`,
`benchmark/`, or `apps/` is absent, and while `harness/` still imports Model
or Infra.

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
