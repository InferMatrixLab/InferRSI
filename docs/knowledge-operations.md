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

Direct reads of checkout Skill bodies require the `skills` extra
(`python -m pip install '.[skills]'`). On a base install, `find` opens a matching
indexed installed Skill through its package projection. Package-only operations
and direct Case reads also work with the base install.

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

Collect with one text input uses the local Find ranker.
Pass a positional query or use `relevance` (`--relevance` on the CLI).
Existing callers can explicitly pass `relevance_method="find-lexical-v1"`.
For a retired method, omit the method argument and supply one question. If you
used a positional filter and a relevance cue together, combine them into one
question and pass scope constraints through the structured filters. [Operation guide](operations.md)

```python
reader = KnowledgeReader()
matches = reader.collect("cgroupv2 cpu.stat.local", material=True, limit=3)
selected = reader.collect(
    ids=["package:inferrsi.ascend.skills.ascend_graph_mode",
         "package:inferrsi.ascend.skills.ascend_device_health"],
    context_bytes=65536,
)
```

```bash
inferrsi collect --id package:inferrsi.ascend.skills.ascend_graph_mode \
  --id package:inferrsi.ascend.skills.ascend_device_health \
  --context-bytes 65536 --json
```

An empty query and no `relevance` give inventory in qualified identity order.
Explicit `ids` retain caller order and are subject to filters, revision
availability and output limits. `limit` caps the number of returned items.
For explicit IDs, omit the positional query
and optionally pass `relevance` to guide selection of optional context files.
`selection.ranking_applied` records whether the items themselves were ranked.

Text discovery scores local Cases, Skills and Records within the requested kind
and filters. Installed Skills selected with `--kind skill` can be delivered
through package records with bundle kind `knowledge`. Their original `SKILL.md`
is available through assembled context or `read --resource`. This works on a
base install. In a mixed search using a custom `--skill-root`, that library
provides its registered Skills. Installed projections supply missing names.
Each version remains available by its qualified reference.

Case applicability text stays searchable. For backend-scoped discovery, a Case's
top-level `backend` names a supported backend or `common`. Discovery without a
backend also includes Cases without that declaration. Scoped selection counts
those Cases under `ranking_scope`. With a scenario, ranked discovery includes
package Records matching that workload and packaged Skills tagged
`skills.discovery`. Captured hits keep the scenario declared by their owner.
Inventory and explicit IDs filter on that declared scenario.

Set `campaign init --backend <backend>` to retain the runtime backend for
ranked campaign capture. A backend supplied on a capture takes precedence.
Existing campaigns can also supply `--backend` directly on each capture.

`KnowledgeStore.collect` delegates to the same selector. With a store attached,
discovery includes its candidate bundles under qualified `store:<id>`
references. See the [store read and revision rules](knowledge-store.md).

`context_bytes` requests a separate context view with a positive byte budget.
Ranked discovery can capture a complete engine `record.json` or Case entrypoint
and its required resources. The assembled context for indexed Skills follows
the resource rules below. `material=True` on a package Skill record returns its
`record.json` entrypoint.

| Additional result | Meaning |
| --- | --- |
| `retrieval` | Recorded entry, filters, ranking execution, returned-item scores and budget counts; outside budgeted item/resource payloads. See [retrieval observations](knowledge-retrieval-trace.md#execution-observations) |
| `selection` | Method, cue, scope and whether discovery ranking was applied |
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
Owner-local named license/notice files (including retained `*-LICENSE.md` and
`THIRD_PARTY_NOTICES.md`) and explicit `skill_metadata.sources[].third_party_notices`
paths are mandatory as well. Declared notice paths use the same boundary and
existence checks as declared references. These resources never depend on a
relevance match; their complete bytes count toward the mandatory set.
If that set does not fit, the owner's entire context is omitted, with required
and available bytes, and a later smaller context can still fit. The owning item
can still be returned. Mandatory instructions are never truncated.

Remaining owner-local Markdown, JSON, text and CSV resources are optional. With
a cue, Find ranks their filenames and text within the owner and only positive
matches are eligible. An empty cue uses resource path order. The context's
`omissions` list nonmatching, oversized, non-UTF-8 and ineligible resources
such as `metadata.json` and scripts. Follow links to further material through
the owning revision. Use exact `read` for the complete Bundle.

The context budget sums exact UTF-8 resource-body bytes across owners in selected
item order, counting a shared resource again if returned for another owner.
It excludes provenance, hashes, omissions and control metadata. The separate
`max_bytes/material_bytes` contract still counts serialized existing item payloads;
adding context does not change those item payloads. Use `--json` for full
provenance/accounting. CLI text mode prints complete context bodies in delimited
blocks plus resource/owner omission codes.

Collect validates a generated Skill projection against the packaged registry,
owner mapping and resource hashes before returning a ranked hit or building an
exact context view. Missing or stale bindings produce `index_unavailable` in
the corresponding item or context omissions. Refresh projections with the
existing `tools/build_skill_index.py` after committing their inputs.

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

`read --material --omit-resources` returns the full entrypoint, provenance,
applicability and revision. Use `read --resource <key>` to display a specific
UTF-8 resource in `content` and its key in `content_resource`. Remove
`--omit-resources` to list resource paths and digests. These views use the same
full-bundle revision.

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
