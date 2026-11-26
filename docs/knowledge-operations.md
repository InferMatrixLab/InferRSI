# Normalized reads and Collect

This is the K2 read slice of the [knowledge base contract](knowledge-base.md).
Existing imported engine catalog IDs remain unchanged; the migrated skill catalog
uses backend-scoped `inferrsi.<backend>.skills.*` IDs. The operations are available as the
`collect` / `read` / `resource` CLI commands and as the Python interface below;
neither requires a conversation or workflow object.

```python
from pathlib import Path
from inferrsi.knowledge.knowledge_operations import KnowledgeReader

reader = KnowledgeReader(skill_root=Path("src/inferrsi/knowledge/data/skill_library"))
result = reader.collect(ids=["calibrate-serving-simulation"], material=True, limit=1)
item = result["items"][0]
source = reader.resource(item["ref"], "playbooks/measurement/calibrate-serving-simulation/references/source-notes.md",
                         revision=item["revision"])
```

## CLI access

For discovery, use `find` and follow the relevant hit's `open` command. Use
`collect` to take a batch of known materials, and `read` or `resource` for an
exact bundle or resource. The [operation guide](operations.md) lists the flags.
The package catalog is available by default. Select a custom library with
`--skill-root` or select the bundled library with `--installed-library` on
`collect`, `read`, `resource` or `campaign capture-context`. The read-only
`--store` option requires the store's recorded skills root if one was configured.
`resource` takes the
revision returned by `collect` or `read` and writes bytes to `--output`.

```bash
inferrsi find 'Ascend OOM after caching per-step masks' --kinds case
```

Direct reads of checkout Skill bodies require PyYAML, a core dependency (the
`skills` extra remains a compatibility alias). On an install without PyYAML, `find`
opens a matching indexed installed Skill through its package projection.
Package-only operations and direct Case reads also work without it.

### Read a decision card

`find --decision-cards` adds a `decision_card` to each readable Skill and Record
hit and to each displayed Case finding. For example, this query shows three
findings from the existing Sarathi Case in query-relevance order.

```bash
inferrsi find 'Sarathi chunked prefill' --kinds case --limit 1 --decision-cards --json
```

Follow the selected link's `open_argv` (executable and arguments) or pass its
`read_args` to the CLI. It specifies `read REF --revision REV --layer L1`, the
same source options, and the finding selector when needed. For the TTFT/TBT
finding the selector is `case.json#/findings/3`. The index counts from zero in
the original Case JSON at that revision. A unique authored ID yields `id:<id>`.
The usual L0 ranking, material command and hit preview are available alongside
the opt-in link.

The returned `card` identifies the qualified reference, revision and atom.
If a ranked source changes before Find can pin the decision link, the link
reports `unavailable`. Repeat Find to rank the current declaration and body.
`card.decision` exposes applicability, prerequisites, refusal or limits,
recommendation and validation. Values come from the frozen declaration.
The `refusal_or_limits` object carries each populated `refusal_point`,
`failure_modes` and `limitations` field under its original name.
A Case recommendation carries the attempted direction **with its outcome and
reason**, and its validation field gives the author's revisit condition.
`card.declared` preserves the corresponding source fields, including the original
verification, evidence state, sources and limitations when supplied.
For example, a Record can declare `verification.locally_verified: false` and
an evidence level of `guidance`. A projected field may be empty or null.

- `complete` means all decision fields have a declaration. `partial` returns
  the card and its `missing_fields`. The source's evidence state applies in
  either case.
- `card_bytes` counts the UTF-8 bytes of the canonical JSON **card object**.
  Object keys are sorted, non-ASCII characters use UTF-8, and separators are
  a comma and a colon with no whitespace. The enclosing response and CLI
  formatting are outside the count. Add `--max-bytes N` to the pinned read to
  enforce a limit. A card of exactly N bytes fits. `over_budget` returns the
  required size, missing field names and source read options, and omits the
  whole card.
- `unavailable_revision` reports the requested reference and revision when the
  selected authority lacks that snapshot. A retained Store revision can remain
  readable after its head advances.

`next_read_args` opens the original L2 body at the same revision. When the
declaration lives separately, `source_read_args` opens it (the original
`case.json`, a legacy Skill sidecar, or Store metadata). Use `resource` with
the same reference, revision and source options for L3 attachment bytes.
Python callers can use
`reader.read_decision_card(ref, revision=revision, finding=selector, max_bytes=limit)`.
For a Skill or Record omit `finding`.

A selector that already holds the result of `reader.read_resolved` can project
directly from that read. Keep the returned pair together, including its
qualified owner. The Bundle revision covers the manifest and resource bytes.
Only the reader supplies their authority. Two checkouts can use the same
`checkout:` reference, so keep the pair from the checkout that supplied the body.

```python
from inferrsi.knowledge.decision_cards import project_decision_card

held = reader.read_resolved(selected_ref, revision=selected_revision)
result = project_decision_card(
    held, reference=selected_ref, revision=selected_revision,
    finding=selector, max_bytes=remaining_bytes,
)
```

The projection checks the selected qualified reference, Bundle ID and revision
in memory. A mismatched identity raises `IdentityError`. A changed revision
raises `UnavailableRevision`. Pass `compact=True` for the compact form. A
caller that delivers bodies first can pass the remaining budget and charge
`card_bytes` only when the result includes `card`. Ordering multiple selections,
accounting for their bodies and checking catalog snapshot freshness belong to
the caller.

For a compact read, append `--compact` to the L1 link's `read_args`. For
example, append `--compact --max-bytes 4096` to request the entire decision
within 4 KiB. The caller chooses the budget. The size advertised by Find
still describes the full card.

The compact card has `view: "compact"` and retains the full `decision`,
`status`, `missing_fields`, qualified reference, revision and atom. Its
`declared` object keeps the author's origin, status, state and downstream
impact when present. `validation_evidence` keeps any original
`empirical_validation` and `verification` declarations, including an explicit
`false` for local verification. A null value means neither field was
declared. A validation plan describes what to check. Evidence of execution
comes from the source declaration. For Case findings, `finding_context`
preserves extra qualifiers such as scope. The decision already carries the
direction, outcome, reason, bounds and revisit condition when declared.

`omitted_declared_fields` names raw full-L1 fields whose original form is
available at the pin, including sources, claims or the original finding.
Use the response's `full_read_args` to open full L1 with the same source
options and selector. In Python, pass `compact=True` to
`reader.read_decision_card(...)`, then call
`reader.read_decision_card(**result["full_read"])` on that reader. Both
routes are available even when `over_budget` omits the compact card.

Every item has an owning `authority` (`package`, `checkout` or `store`) and a qualified
`ref` of the form `<authority>:<id>`. Public IDs are unchanged and may be used
unqualified while they resolve to exactly one authority. An ID owned by more than
one authority is never resolved by precedence: `read` raises an ambiguous-identity
error naming the qualified choices, explicit Collect reports it as an omission, and
a full Collect returns each qualified item and lists the ID under `collisions`.

Omitting `skill_root` gives exact inventory and reads over the installed
package, including procedures such as
`inferrsi.ascend.skills.ascend_graph_mode`. A reader loads the installed catalog
and complete skill library once per snapshot. Inventory and exact selection apply
the `repo`, `tier`, `backend` and `scenario` filters to package items.
Filters apply before output limits. Package metadata filters run before loading
resource bytes. Each item omission has a reason code such as
`unknown_identity`, `ambiguous_identity`, `invalid_identity`,
`duplicate_identity`, `unavailable_revision`, `invalid`, `filters`,
`output_limit` or `index_unavailable`. Errors also include a `detail` message.
An empty result reports `no_match`.

Per-item omissions apply after identity discovery. A checkout whose registered
names or case identities cannot be trusted fails discovery explicitly. Examples
include a skill registration whose path disagrees with its name and a missing
or duplicate Case ID.

## Ranked discovery and budgeted context

Use `find QUERY` to rank Cases, Skills and Records. Its result contains hits and
commands to open them. Following a hit's `read_args` returns the primary body.
A linked procedure, example or data file can be read separately by its exact
resource path and revision. An ordinary search or body read does not request
the owner's attachment bundle.

For an optimization question, use the same search within the campaign:

```sh
inferrsi find "fixed seed diffusion baseline" --session <dir>
```

Run the emitted scoped `read` for the relevant hit. The session records the
ordered hits, then the read it actually served. Find reports zero delivered
bytes even when it returns hits. Each operation returns its campaign-relative
receipt in `reference.path`. An empty resource produces an `empty_context`
receipt for audit. A round can cite a scoped read that returned content.
Historical captures remain available for reviewing and replaying old rounds.
New rounds require a scoped read receipt.

To follow a link in the primary body,
append the path as printed, for example `--resource references/benchmark-commands.md`,
to the hit's read arguments. Keep the original `--session` and `--search-ref`.
Read resolves the link inside the pinned bundle and the receipt names the full
resource key in `content_resource`. A file link with a section fragment opens the entire file.

Each read records the actual UTF-8 bytes it returned at the hit's revision.
Large resources return a page with `content_range` and executable
`next_read_args`. Run those arguments to continue the same resource, revision
and search reference. Pages limit their JSON content string to 6 KiB so the
normal Agent tool response can carry the content and its receipt together.
This is a per-response size limit; it does not limit how much of the file you
can read. `next_byte_range` also exposes the continuation coordinates for
callers using `--byte-range START LENGTH`. Use `--byte-range 0 3900` to
request at most the first 3,900 UTF-8 bytes. Each receipt identifies the
bytes in that page. A scoped read serves one selected body or linked resource.
For an exact L1 decision card use standalone `read --layer L1`. Use explicit
bundle assembly when the required files need to be delivered as a group.
Content responses omit the full resource inventory. To inspect that inventory,
run `read ID --revision REVISION` without `--material` or `--resource`.

A benchmark plan can require a particular card under a fixed query, scenario
and byte allowance. Run its supplied Find request and open the card before
submitting round one. Reads return their content even when the allowance is
zero. The report counts the real bytes returned for that request, including
repeated reads and attachments. An over-budget delivery, a late read or a
retry with a larger allowance excludes the pair from card-effect conclusions.
A service-reuse Find retains the hit's actual body and available supporting
files before returning the search receipt. Reads and continuations use this
retained source, including after the installed package changes. The source
commit remains provenance. Each read retains its own content, resource path
and search reference under that campaign’s fingerprint-free protocol. Historical
receipts remain readable; a search made before source retention must be repeated
before it can supply new reads.

Use `collect` to assemble a batch when the identities are already known. Without
IDs it enumerates available items in qualified identity order. Explicit IDs
retain caller order, subject to filters, revision availability and `--limit`.
`--relevance` with explicit IDs can prioritize optional files within those
bundles. A store attached to this reader supplies its retained revisions. See
the [store read and revision rules](knowledge-store.md).

```sh
inferrsi collect --id package:inferrsi.ascend.skills.ascend_graph_mode \
  --id package:inferrsi.ascend.skills.ascend_device_health \
  --context-bytes 65536 --json
```

A Harness candidate generator can request a reproducible input file for a
question. It selects pins with Find, packs the primary bodies in rank order up
to the input limit, then uses any remaining bytes for supporting resources.
Its manifest identifies the bytes delivered and the omissions. Manual
`campaign capture-context --id-ref REF` saves an exact bundle snapshot.

This explicit bundle operation has its own byte cap. The published context
for an indexed Skill includes its declared references, notices and licenses.
If the body and required files together exceed the cap, `collect` reports
`context_limit` for that bundle. Its `record.json` package entrypoint remains
available with `--material`.

| Additional result | Meaning |
| --- | --- |
| `retrieval` | Recorded entry, filters, ranking execution, returned-item scores and budget counts; outside budgeted item/resource payloads. See [retrieval observations](guides/knowledge/knowledge-retrieval-trace.md#execution-observations) |
| `selection` | Method, cue, scope and whether discovery ranking was applied |
| `contexts` | Selected owner views, each with `ref`, exact Bundle `revision`, resources, `content_bytes`, resource omissions, sources, attribution and limitations |
| `context_omissions` | Owner context unavailable: `unsupported_context`, `index_unavailable` or `context_limit` |
| `context_bytes`, `context_budget` | Used body bytes, requested ceiling and accounting method |

Each context resource reports its canonical `path`, `role`, UTF-8 `content` and
the SHA-256 of those delivered bytes. A `whole-resource` locator covers the
entire file. A `skill-procedure` locator delivers the complete procedure and host
frontmatter, omitting the structured `metadata.inferrsi` block from prompt
context. Its `source_sha256` covers the entire file, and `source_byte_ranges`
lists the half-open byte ranges whose concatenation reproduces the projection. Use the parent ref,
revision and path with `resource` to reproduce the source bytes. The skill
procedure, declared references, provenance readsets and owner licenses are mandatory.
Licenses are retained along each required resource's skill/repository/framework
directory ancestry inside the packaged library, including cross-skill prerequisites.
Owner-local named license/notice files (including retained `*-LICENSE.md` and
`THIRD_PARTY_NOTICES.md`) and explicit `skill_metadata.sources[].third_party_notices`
paths are mandatory as well. Declared notice paths use the same boundary and
existence checks as declared references. These resources never depend on a
relevance match; their delivered bytes count toward the mandatory set.
If that set does not fit, the owner's entire context is omitted, with required
and available bytes, and a later smaller context can still fit. The owning item
can still be returned. Mandatory instructions are never truncated.

Remaining owner-local Markdown, JSON, text and CSV resources are optional. With
a cue, Find ranks their filenames and text within the owner and only positive
matches are eligible. An empty cue uses resource path order. The context's
`omissions` list nonmatching, oversized, non-UTF-8 and ineligible resources
such as scripts. Follow links to further material through
the owning revision. Use exact `read` for the complete Bundle.

The context budget sums exact UTF-8 resource-body bytes across owners in selected
item order, counting a shared resource again if returned for another owner.
It excludes provenance, hashes, omissions and control metadata. The separate
`max_bytes/material_bytes` contract still counts serialized existing item payloads;
adding context does not change those item payloads. Use `--json` for full
provenance/accounting. CLI text mode prints complete context bodies in delimited
blocks plus resource/owner omission codes.

Collect validates a generated Skill projection against the packaged registry,
owner mapping and resource hashes when building an exact context view. Missing or stale bindings produce `index_unavailable` in
the corresponding item or context omissions. Refresh projections with the
existing `tools/build_skill_index.py` after committing their inputs.

Offline fixtures establish compatibility and bounded deterministic selection.
Task outcomes, tokens and latency require a separately authorized comparison
through [Skill Eval](skill-evaluation/README.md), with cases, versions and budgets frozen
before agent execution. Selection scores and green software checks do not
establish skill efficacy.

## Identity and resources

`Bundle` contains normalized metadata, content bytes and dependency revisions.
Its SHA256 revision covers metadata, every included resource hash and every
resolved dependency revision. Resource-only changes change the revision.
Selected resource reads require the exact returned revision. A changed checkout
or installation rejects an old revision; it never substitutes new bytes.
This reader does not itself retain history or claim standalone exports.

`read --material --omit-resources` returns the entrypoint, provenance,
applicability and revision. For skills with embedded InferRSI metadata,
`content` carries the procedure and its host header. `content_view` supplies
the delivered SHA-256, source SHA-256 and half-open byte ranges in the source.
The explicit resource read at the same revision returns the original bytes,
including the annotation. Older sidecar-backed procedures retain their
original entrypoint content. Use `read --resource <key>` to display a specific
UTF-8 resource in `content` and its key in `content_resource`. Read accepts an
exact key or a path relative to the primary body. Exact keys take precedence.
Use `./` to select a body-relative path if the two names overlap.
A Markdown link with an anchor, such as `note.md#setup`, opens the file
relative to the body when that file is in the bundle. Follow
`next_read_args` to finish a paged read. To list resource paths and digests,
run a standalone `inferrsi read <ref> --revision <revision>` with the same
source flags. Leave out `--material`, `--resource` and `--omit-resources`.
These views use the same full-bundle revision.

- Local skills include their complete owner folder (except incidental
  `__pycache__`, `*.pyc` and `.DS_Store`) and declared cross-skill references,
  whether declared in skill frontmatter or a legacy checkout sidecar. Other links remain navigation in the required full checkout.
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

Use `find --kinds case` to locate rejected directions. Given the identity and
revision of a hit, reopen the exact Case through the same library:

```python
reader = KnowledgeReader(skill_root=Path("src/inferrsi/knowledge/data/skill_library"))
case = reader.read("checkout:case.qwen-ascend-rejected-directions",
                   revision="<revision from read>")
```

Other example queries are `B300 RMSNorm` and `Drama3 prefix reuse`. Include the
mechanism and symptom to narrow the results. Read the Case's conditions and
limitations before applying the observation.

For explicit CLI resource-path resolution from the installed library (PyYAML, a core
dependency, required), or a custom library selected with `--root`:

```bash
inferrsi skills resource inference-optimization-casebook cases/qwen-ascend-rejected-directions.md
inferrsi skills reference optimization-search-policy ../../../casebooks/inference/inference-optimization-casebook/cases/drama3-rejected-directions.md
```

These commands return a `path` for your file reader; they do not load the body
or execute it. The Python `read` example above returns the selected case bundle.

Read observations, limitations and suggested revisit conditions before acting.
The case files ship inside the packaged library and are retained as resources of
its catalog bundles. To read an individual `checkout:case.*` identity, select
the bundled library with `--installed-library` or a custom checkout with
`--skill-root <path>`. Cases retain their recorded verdict and verification scope.
