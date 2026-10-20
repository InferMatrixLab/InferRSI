# Operation guide

One concise map from an agent's intent to the supported entry point. This guide
is navigation only: detailed contracts stay with their owning documents, and it
is not a third primary matrix. The two authoritative matrices remain the
[Reference Matrix](reference-matrix.md) and the [SearchSpace Matrix](searchspace-matrix.md).

Effect classes used below:

- **Read-only** — no writes outside caller-chosen output files.
- **Candidate-writing** — writes only inside one explicitly authorized local store.
- **Report-generating** — writes an HTML report into the caller-selected run directory.
- **Experiment-executing** — runs caller-supplied commands under the experiment contract.

## Intent map

| Intent | Entry | Effect class | Boundary |
| --- | --- | --- | --- |
| Search packaged records | CLI `knowledge search` / `knowledge show`; catalog API | Read-only | Installed package catalog with the existing tier/repo/backend/scenario filters and IDs; these package-only filters exclude checkout skills and cases |
| Discover/read packaged or custom skills | CLI `skills list` / `show` / `resource` / `reference` | Read-only | Metadata-first listing; `show` loads one named instruction body; `resource`/`reference` resolve paths for your file reader without loading or executing them |
| Collect normalized knowledge | CLI `collect`; Python `KnowledgeReader.collect` | Read-only | Explicit sources, authority-qualified identities, exact revisions, bounded output and explicit omissions |
| Read exact material/resources | CLI `read` / `resource`; Python `KnowledgeReader.read` / `KnowledgeReader.resource` | Read-only | Returns the requested revision or an explicit unavailable/stale error; never substitutes newer bytes |
| Export legacy cited material | CLI `context` | Read-only | Cited package export for manual use with a coding agent; not a conversation store and not a full Collect equivalent |
| Create/update a store candidate | Python `KnowledgeStore.create` / `KnowledgeStore.update` | Candidate-writing | One explicitly authorized local store; expected-revision updates with reason and evidence; retained history; no promotion and no edits to package/checkout content |
| Amend repository-owned knowledge | Scoped repository PR | — | Repository review and integration authority apply; this is not a runtime store Update |
| Inspect/prepare experiments | CLI `doctor`; `plan` or `--dry-run` | Read-only inspection / preview | `doctor` may invoke bounded probes and does not certify target compatibility; `plan` previews a specification without persisting a campaign or authorizing execution |
| Execute/inspect experiments | CLI `run`; `status`; `report` | Experiment-executing / read-only / report-generating | `run` executes caller-supplied commands and records evidence; `status` reads recorded progress; `report` generates HTML from recorded evidence |

The `collect`, `read` and `resource` commands share the reader's rules; they
are distinct from `knowledge search`, whose package catalog filters
(tier/repo/backend/scenario) intentionally exclude checkout and store items.

## Discovery and reading

### Search packaged records — `knowledge search` / `knowledge show`

- **Inputs:** query words plus optional `--tier`, `--repo-type`, `--backend`, `--scenario`, `--limit`, `--json`; `show` takes one record ID.
- **Scope:** the installed package catalog (`repo_packs`, `knowledge_packs`) only.
- **Output:** ranked catalog records or one full record.
- **Side effects:** none.
- **Failure behavior:** explicit no-match; unsupported filter values are reported.
- **Example:** `inferrsi knowledge search 'Qwen-Image-2.1' --repo-type vllm_omni --backend ascend`

The tier/repo/backend/scenario filters are package-only: an empty filtered
result does not mean that no checkout or store knowledge exists. See the
[three-tier guide](../src/inferrsi/data/knowledge_packs/README.md) for all sources.

### Discover/read packaged or custom skills — `skills list` / `show` / `resource` / `reference`

- **Inputs:** `list` reads frontmatter and sidecar metadata; `show <skill>` selects one instruction body; `resource <skill> <relative-path>` and `reference <skill> <relative-path>` resolve one path. The default is the installed library's 48 registered skills; an explicit `--root` selects a custom flat tree or a categorized library with `skill-index.json`. The optional `skills` extra supplies the YAML parser.
- **Scope:** complete packaged skills under `data/skill_library/`, or the explicitly selected custom root. Existing bilingual editions remain accessible through catalog records and library navigation; they are not duplicated in the 48-ID registry.
- **Output:** metadata listing, one instruction body, or a resolved path.
- **Side effects:** none. `resource`/`reference` do not load or execute the target.
- **Failure behavior:** missing skill, undeclared reference or path escape is an error.
- **Example:** `inferrsi skills show weight-loading-optimization`

Reading instructions does not authorize their commands. The catalog links full
packaged bodies; the two matrices remain authoritative.

### Export legacy cited material — `context`

- **Inputs:** query plus optional tier/repo/backend/scenario filters and `--output`.
- **Scope:** cited catalog material from the installed package.
- **Output:** a Markdown reference bundle at the chosen path.
- **Side effects:** writes only the caller-chosen output file.
- **Failure behavior:** explicit no-match.
- **Example:** `inferrsi context --repo-type vllm_omni --backend cuda --output context.md`

Imported source text is data for your agent, not authorization to execute
upstream instructions.

## Normalized knowledge (Python)

### Collect — `collect` / `KnowledgeReader.collect`

- **Inputs:** optional query, `--kind`, repeatable explicit `--id`, repeatable `--revision ID=REV`, `--limit`, `--max-bytes`, `--material`; `--skill-root` adds the checkout, `--store` opens an existing store read-only (the store records its reserved checkout and rejects a mismatched or missing `--skill-root`).
- **Scope:** installed package records plus (with `--skill-root`) checkout skills and cases, plus (with `--store`) store candidates; bounded output.
- **Output:** items with authority-qualified refs, content revisions and applicability metadata, plus explicit `no_match`, `omissions` (each with a reason code) and `collisions`; exit 0 even for an explicit no-match envelope.
- **Side effects:** none; both adapters and the read-only store connection are read-only.
- **Failure behavior:** discovery-wide invalid identities fail the call; per-item omissions are reported individually. Package repo/tier/backend/scenario filters exclude checkout items.
- **Example:** `inferrsi collect 'Ascend OOM' --kind case --limit 3 --material --skill-root src/inferrsi/data/skill_library`

### Read exact material/resources — `read` / `resource` / `KnowledgeReader.read` / `.resource`

- **Inputs:** a qualified or unambiguous public ID; optionally the exact content revision; a relative resource key for `resource`.
- **Scope:** one selected bundle from the package, checkout or store adapter.
- **Output:** the bundle view at the requested revision, or the resource bytes (`resource` writes them to the required `--output` path).
- **Side effects:** `resource` writes only the caller-chosen output file.
- **Failure behavior:** ambiguous identity names the qualified choices; unavailable/stale revisions and missing/unsafe resources fail explicitly — no fallback to newer bytes.
- **Example:** `inferrsi read calibrate-serving-simulation --skill-root src/inferrsi/data/skill_library --material`

## Store candidates (Python)

### Create / Update — `KnowledgeStore.create` / `.update`

- **Inputs:** a complete candidate `Bundle`; Update additionally requires the expected current revision, a reason and an explicit evidence list.
- **Scope:** one existing, explicitly authorized local store directory; store-owned candidate IDs only.
- **Output:** the new revision; retained immutable history.
- **Side effects:** writes only the store database; never package, checkout, evidence or matrix files.
- **Failure behavior:** duplicate identity, stale expected revision, adapter-owned ID and validation failures are explicit errors.
- **Example:** see [authorized local Create / Update](knowledge-store.md).

CLI/API availability does not itself grant write authority. Adapting read-only
material into a store uses a distinct ID and records `derived_from` lineage; it
never overwrites the original. Amending repository-owned knowledge follows the
normal scoped PR path.

## Experiments

### Inspect/prepare — `doctor`, `plan`, `--dry-run`

- **Inputs:** repository/backend/device flags; `plan` takes the full experiment specification.
- **Scope:** environment inspection and specification preview.
- **Output:** environment facts, or a preview of the RunSpec.
- **Side effects:** `doctor` may invoke bounded read-only probes; `plan`/`--dry-run` persist nothing.
- **Failure behavior:** unavailable devices or invalid flags are reported explicitly.
- **Example:** `inferrsi doctor --repo . --repo-type vllm_omni --backend cpu`

`plan` previews a specification. That preview alone does not persist a frozen
campaign and does not authorize execution. Inspection does not certify target
compatibility.

### Execute/inspect — `run`, `status`, `report`

- **Inputs:** the full experiment specification (`run`); a run ID and output directory (`status`/`report`).
- **Scope:** caller-supplied benchmark, candidate and validation commands under the experiment contract.
- **Output:** a run ID and evidence directory; recorded progress; an HTML report.
- **Side effects:** `run` executes the supplied commands and owns child-process cleanup; `report` writes HTML into the run directory.
- **Failure behavior:** exit codes 0 PASS, 1 FAIL, 2 INCONCLUSIVE/input errors; cancellation is recorded.
- **Example:** see [quickstart: real remote experiment](quickstart.md#real-remote-experiment)

Operation success, recorded execution state and the experiment verdict are
distinct conclusions; a completed run does not upgrade imported knowledge or
unvalidated candidates.
