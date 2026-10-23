# Normalized reads and Collect

This is the K2 read slice of the [knowledge base contract](knowledge-base.md).
Existing imported engine catalog IDs remain unchanged; the migrated skill catalog
uses backend-scoped `inferrsi.<backend>.skills.*` IDs. The operations are available as the
`collect` / `read` / `resource` CLI commands and as the Python interface below;
neither requires a conversation or workflow object.

```python
from pathlib import Path
from inferrsi.knowledge_operations import KnowledgeReader

reader = KnowledgeReader(skill_root=Path("src/inferrsi/data/skill_library"))
result = reader.collect(ids=["calibrate-serving-simulation"], material=True, limit=1)
item = result["items"][0]
source = reader.resource(item["ref"], "methods/calibrate-serving-simulation/references/source-notes.md",
                         revision=item["revision"])
```

## CLI access

The `collect`, `read` and `resource` commands expose these operations with the
same rules (see the [operation guide](operations.md) for flags, boundaries and
examples). Sources are selected explicitly: the installed package by default, a
an explicit skills root via `--skill-root`, an existing store read-only via `--store`;
the store records the skills root it reserves and rejects a mismatched or missing
`--skill-root` on open. `resource` requires the exact revision returned by
`collect`/`read` and writes bytes to `--output`.

```bash
inferrsi collect 'Ascend OOM' --kind case --limit 3 --material --skill-root src/inferrsi/data/skill_library
inferrsi read calibrate-serving-simulation --skill-root src/inferrsi/data/skill_library
```

The `--skill-root` selections require the `skills` extra (`python -m pip install
'.[skills]'`); package-only collect/read work with the base install.

Every item has an owning `authority` (`package`, `checkout` or `store`) and a qualified
`ref` of the form `<authority>:<id>`. Public IDs are unchanged and may be used
unqualified while they resolve to exactly one authority. An ID owned by more than
one authority is never resolved by precedence: `read` raises an ambiguous-identity
error naming the qualified choices, explicit Collect reports it as an omission, and
a full Collect returns each qualified item and lists the ID under `collisions`.

Omit `skill_root` for installed package-only use, including full migrated
procedures through IDs such as `inferrsi.ascend.skills.ascend_graph_mode`. A reader reads the installed
catalog and complete skill library once, so one reader is one package snapshot. Query
words are matched against normalized metadata and the entry content, not resource
hashes. `repo`, `tier`, `backend`, `scenario`
retain existing catalog filter semantics; those package-only filters exclude local
skills/cases. `kind`, explicit `ids`, per-ID `revisions`, item `limit` and
`max_bytes` are available. Filters apply before output limits; package metadata
filters run before any resource bytes are loaded. `max_bytes` bounds
returned item payloads, not the omission/control envelope. Each omission carries a
`reason` code (`unknown_identity`, `ambiguous_identity`, `invalid_identity`,
`duplicate_identity`, `unavailable_revision`, `invalid`, `filters`, `query`,
`output_limit`) and, for errors, a `detail` message. No-match is explicit.
Per-item omission applies after identity discovery: a checkout skill or case
record that cannot be parsed or validated during discovery (for example invalid
frontmatter or JSON, a name/directory mismatch, conflicting metadata, a missing
or duplicate case ID) fails the whole reader call explicitly, because
identities cannot be trusted.
Deterministic identity order is not a learned relevance ranking.

## Optional packaged skill selection and context

Two independent opt-ins extend the same `collect` operation:

```python
reader = KnowledgeReader()
# Existing query and material semantics are unchanged.
legacy = reader.collect("cpu.stat.local", material=True, limit=3)
selected = reader.collect("cpu.stat.local", relevance="cgroupv2",
                          context_bytes=65536, limit=3)
```

```bash
inferrsi collect 'cpu.stat.local' --relevance cgroupv2 --context-bytes 65536 --json
```

`relevance` is a separate lexical cue, not a replacement for `query`. Discovery
with this cue considers generated `index_type=packaged-skill` package entries
only; they retain `kind=knowledge`. Existing filters and the whitespace-token
AND substring query run first. Each distinct case-folded word (`\w+`) contributes
4 for substring presence in the title, 3 in the description, 2 in
tags/applicability and 1 in the complete core. Repetition within a field adds nothing. Candidates with
positive overlap sort by decreasing score, then qualified identity, before
`limit` and `max_bytes`. This is deterministic lexical matching, not a learned
ranking or a task-quality guarantee. Explicit `ids` retain membership and caller
order regardless of the cue; `selection.ranking_applied` is false for those calls.
Ordinary collection of other authorities and records remains available without
the relevance opt-in. `KnowledgeStore.collect` delegates these same options.

`context_bytes` requests a separate context view for returned generated packaged
skills. It requires an explicit positive integer budget, with no token estimate
or default. It can be used without `relevance`; optional resources then match the
existing query, or use path order for an empty query. The existing `material=True`
still returns `record.json` for these owners, not `SKILL.md`.

| Additional result | Meaning |
| --- | --- |
| `selection` | Method, cue, scope and whether discovery ranking was applied; only with `relevance` |
| `contexts` | Selected owner views, each with `ref`, exact Bundle `revision`, resources, `content_bytes`, resource omissions, sources, attribution and limitations |
| `context_omissions` | Owner context unavailable: `unsupported_context`, `index_unavailable` or `context_limit` |
| `context_bytes`, `context_budget` | Used body bytes, requested ceiling and accounting method |

Each context resource carries its complete UTF-8 `content`, canonical resource
`path`, exact-byte `sha256`, `role` (`core` or `reference`) and
`locator=whole-resource`. The parent view supplies its owning ref and revision;
`resource` can read exactly those bytes. The full canonical `SKILL.md`, declared
references, provenance readsets and owner licenses (when present) are mandatory.
Licenses are retained along each required resource's skill/repository/framework
directory ancestry inside the packaged library, including cross-skill prerequisites.
If that set does not fit, the owner's entire context is omitted, with required
and available bytes, and a later smaller context can still fit. The owning item
can still be returned. Mandatory instructions are never truncated.

Remaining owner-local Markdown/JSON/text/CSV resources are optional. Their
filename contributes 2 per matching word and their complete text contributes 1;
ties use resource path. An empty cue includes them in path order. Nonmatching,
oversized, non-UTF-8 and non-context resources (including owner `metadata.json`
and scripts) are reported under the context's
`omissions`, not silently discarded. Selected files retain their prerequisites
and limitations; links to further material must still be followed through the
owning revision. The context view is not a standalone export or proof that all
linked dependencies have been read.

The context budget sums exact UTF-8 resource-body bytes across owners in selected
item order, counting a shared resource again if returned for another owner.
It excludes provenance, hashes, omissions and control metadata. The separate
`max_bytes/material_bytes` contract still counts serialized existing item payloads;
adding context does not change those item payloads. Use `--json` for full
provenance/accounting. CLI text mode prints complete context bodies in delimited
blocks plus resource/owner omission codes.

The source-pinned generated projection is validated against the packaged
registry, owner mapping and resource hashes on each optimized read. Missing or
stale bindings produce `index_unavailable` (a discovery item omission or a
context omission); no ordinary-mode fallback occurs. Refresh projections with
the existing `tools/build_skill_index.py` after committing their inputs. No new
registry, persistent cache, service or optional parser dependency is introduced.
Bundle resources, complete library dependency closure and revision calculations
remain unchanged. Collection never executes a skill or its scripts.

Offline fixtures establish compatibility and bounded deterministic selection.
Task outcomes, tokens and latency require a separately authorized comparison
through [Skill Eval](skill-evaluation.md), with cases, versions and budgets frozen
before agent execution. Selection scores and green software checks do not
establish skill efficacy.

## Identity and resources

`Bundle` contains normalized metadata, content bytes and dependency revisions.
Its SHA256 revision covers metadata, every included resource hash and every
resolved dependency revision. Resource-only changes change the revision.
Selected resource reads require the exact returned revision. A changed checkout
or installation rejects an old revision; it never substitutes new bytes.
This reader does not itself retain history or claim standalone exports.

- Local skills include their complete owner folder (except incidental
  `__pycache__`, `*.pyc` and `.DS_Store`) and declared cross-skill references,
  whether declared in the sidecar or in legacy frontmatter. Other links remain navigation in the required full checkout.
- Local structured cases keep their own identity, observation and source limits.
  A case bundle holds its record, content and any `required_resources` declared
  relative to the record; missing, unsafe or escaping resources fail. Case
  `references`/`dependencies` declarations are rejected rather than ignored;
  external evidence stays a source pointer.
- Every declared `skill_documents` edition must be present in the retained
  library; a missing target fails the read instead of leaving a dangling link.
- Existing imported engine catalog records retain IDs/tiers/state. Records with `skill_documents` include the
  entire packaged library as one conservative dependency closure: languages,
  manifests, licenses, helpers and transitive references are preserved. This is
  intentionally broader than one procedure; an unrelated library edit changes
  that dependency revision. It is not a duplicate editable authority.
- All included paths are relative POSIX resource keys. Absolute paths, traversal
  and symlinks are rejected. Missing declared resources/dependencies fail visibly.

Git commits (including explicitly partial historical prefixes), paper versions,
document snapshots and internal artifact identities are distinct source types.
Legacy unnormalized provenance remains `unknown`; an unrecognized legacy type such
as `upstream_report` is kept as `original_type`, with pointers in the original
material; no SHA or source verification is invented. Content revision is neither
an upstream source pin nor an experimentally tested engine revision.

Both adapters are read-only: no reader call writes to the checkout, the installed
package, evidence or either matrix. The separate writer slice retains immutable
store-owned candidate bundles in one authorized store. Reading or collecting
supplied code never runs it or grants permissions.

## Retrieve diagnostic options

Rejected directions use the same checkout Case bundles as other observations:

```python
reader = KnowledgeReader(skill_root=Path("src/inferrsi/data/skill_library"))
options = reader.collect("Ascend OOM", kind="case", material=True, limit=3)
item = options["items"][0]  # Inspect no_match/omissions first in a general client.
case = reader.read(item["ref"], revision=item["revision"])
```

Other example queries are `B300 RMSNorm` and `Drama3 prefix reuse`. Query terms
match metadata and entry content as substrings; combine a mechanism and context
to narrow results. An explicit ID such as
`checkout:case.qwen-ascend-rejected-directions` selects exactly one record.
Package repo/backend/scenario filters still exclude checkout cases; inspect the
returned applicability rather than assuming those filters qualify a case.

For explicit CLI resource-path resolution from the installed library (optional
`skills` extra required), or a custom library selected with `--root`:

```bash
inferrsi skills resource inference-optimization-casebook cases/qwen-ascend-rejected-directions.md
inferrsi skills reference optimization-search-policy ../inference-optimization-casebook/cases/drama3-rejected-directions.md
```

These commands return a `path` for your file reader; they do not load the body
or execute it. The Python `read` example above returns the selected case bundle.

Read observations, limitations and suggested revisit conditions before acting.
The case files ship inside the packaged library and are retained as resources of
its catalog bundles. Individual `checkout:case.*` identities still require the
explicit `--skill-root` adapter shown above; no separate case catalog records are
generated. Cases retain their original verdict/verification scope; retrieval is
not an experiment.
