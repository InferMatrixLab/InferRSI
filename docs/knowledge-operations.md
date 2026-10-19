# Normalized reads and Collect

This is the K2 read slice of the [knowledge base contract](knowledge-base.md).
Existing CLI commands and catalog IDs remain unchanged. The callable interface is
Python; it requires no conversation or workflow object.

```python
from pathlib import Path
from inferrsi.knowledge_operations import KnowledgeReader

reader = KnowledgeReader(skill_root=Path("skills"))
result = reader.collect(ids=["calibrate-serving-simulation"], material=True, limit=1)
item = result["items"][0]
source = reader.resource(item["ref"], "calibrate-serving-simulation/references/source-notes.md",
                         revision=item["revision"])
```

Every item has an owning `authority` (`package` or `checkout`) and a qualified
`ref` of the form `<authority>:<id>`. Public IDs are unchanged and may be used
unqualified while they resolve to exactly one authority. An ID owned by more than
one authority is never resolved by precedence: `read` raises an ambiguous-identity
error naming the qualified choices, explicit Collect reports it as an omission, and
a full Collect returns each qualified item and lists the ID under `collisions`.

Omit `skill_root` for installed package-only use. A reader reads the installed
catalog and bilingual library once, so one reader is one package snapshot. Query
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
- Existing catalog records retain IDs/tiers/state. Bilingual records include the
  entire imported library as one conservative dependency closure: languages,
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
reader = KnowledgeReader(skill_root=Path("skills"))
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

For explicit CLI resource-path resolution from the full checkout:

```bash
inferrsi skills resource inference-optimization-casebook cases/qwen-ascend-rejected-directions.md
inferrsi skills reference optimization-search-policy ../inference-optimization-casebook/cases/drama3-rejected-directions.md
```

These commands return a `path` for your file reader; they do not load the body
or execute it. The Python `read` example above returns the selected case bundle.

Read observations, limitations and suggested revisit conditions before acting.
The cases are checkout resources, not additional wheel catalog records. They
retain their original verdict/verification scope; retrieval is not an experiment.
