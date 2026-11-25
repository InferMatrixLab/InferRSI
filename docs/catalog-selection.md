# Select evidence from a complete catalog

`catalog-select` is an explicit alternative to Find. Load the appropriate primary
task with `skills enter <primary-id>` first. The seven task routes and the default
Find command are unchanged. Knowledge builds and validates views; the current
Agent or an application callback makes the selection. No model service, model
credentials or autonomous Harness search is introduced.

```bash
inferrsi catalog-select 'Describe the task' --tokenizer o200k_base \
  --token-budget 128000 > catalog.json
# Read every card in prompt.catalog.cards; write the Agent response to selected.json.
inferrsi catalog-select 'Describe the task' --tokenizer o200k_base \
  --token-budget 128000 --selection selected.json > evidence.json
```

The optional `--tokenizer` requires `tiktoken`. Without it, the byte count of the
complete compact JSON model input is used as a conservative token estimate, one
UTF-8 byte per token. `--reserved-tokens` reserves conversation/output capacity;
include all other context in this allowance. Over-budget input returns an explicit
`catalog_over_budget` fallback with ordinary Find results, no truncated directory
and no selector call. A tokenizer counter/name can also be supplied through Python.
Neither estimate nor encoding selection proves the host's actual token usage.

An Agent response has this shape (copy the exact snapshot and qualified refs):

```json
{
  "snapshot_id": "sha256:<snapshot>",
  "model": "<actual-model-or-unknown>",
  "selections": [
    {"ref": "<authority>:<id>", "reason": "Relevant mechanism",
     "questions": ["Does the original bound include this execution stage?"],
     "purpose": "method"}
  ]
}
```

Empty selections are valid. Every selected ref must appear in that snapshot;
unqualified, outside-snapshot and duplicate identities fail. Refresh and reselect
after `stale_snapshot`; there is no silent substitution. Source content and file
membership are checked before reads and again after assembly, including dependency
changes. Within one `CatalogSelection` instance, an unchanged prepared snapshot
reuses its directory, reference graph and readers. Checks hash actual file bytes,
including package records/build inputs and the declared checkout, and verify current
store revisions; matching sizes or timestamps alone do not authorize reuse. A change
invalidates the prepared view, and changes detected during construction are rejected.
Sources containing symlinks or directory redirects use fresh full snapshots rather
than reusing a prepared view, leaving target access to the existing readers.
An I/O error during the optional fingerprint scan also disables reuse. Normal
discovery and reading then determine which entries can be delivered. Completing
a selection still checks the current snapshot before and after assembly.
Completion releases the retained view, including on errors. Returned prompt dictionaries
are independent copies. Reader-local resource digest reuse is keyed by path and
immutable bytes; metadata and dependency validation still run for every manifest.
Snapshots are content identities, not an authorization credential.

### Request a decision card with a selected source

Add `"layer": "L1"` to a selection to request the decision view of its original
Skill or Record. For a Case, also supply a `finding` selector for its original
`case.json`, such as `"case.json#/findings/0"` or `"id:<unique-author-id>"`.
You can supply `revision` from the selected catalog entry to check the pin
explicitly. Both the CLI and the Apps `select_catalog_evidence` callback accept
`layer` per entry. Other entries in the same response keep the default delivery.

```json
{"ref": "checkout:case.admission-drain-occupancy", "reason": "Check the decode occupancy interval",
 "questions": [], "layer": "L1", "finding": "case.json#/findings/0"}
```

Each requested view appears in `decision_cards` in selection order, with the
catalog ref and revision. The catalog projects each card from the same resolved
bundle that supplied that entry's delivered body. A delivered view includes the
complete canonical card, its UTF-8 `card_bytes`, and the original `source_resource` and
`body_resource` locators. Store Record declarations live in the pinned bundle
manifest, so their `source_resource` is null. Reopen a selected source through
this catalog with the original snapshot, selection and revision. Catalog
checkout closures can have different revisions from ordinary Find and Read.

All selected bodies take priority. Each complete or partial card is charged once,
in full, against the remaining `context_bytes`. When a card does not fit, its
selected body stays delivered even if `expansion_bytes` has space to spare.
An `over_budget` result retains the required size and the original pin. Its
`scope: decision_card` omission gives the bytes available for retry.
`base_unavailable` records that the selected body could not be delivered.
The retrieval assembly includes charged cards in `content_bytes` and reports
their subtotal in `decision_card_bytes`. Expansion has its own budget.
For a claim assessment, quote the delivered original at its ref, revision and
resource path. Card text alone cannot confirm a quote.

Python uses the same implementation:

```python
from inferrsi.apps.workflows.knowledge import select_catalog_evidence
from inferrsi.knowledge.catalog_selection import CatalogSelection

result = select_catalog_evidence(
    CatalogSelection(), "Describe the task", current_agent_selector,
    model="<actual-model>", token_budget=128000,
    token_counter=lambda text: len(tokenizer.encode(text)), tokenizer="<encoding>",
    conditions={"backend": "ascend", "dtype": "bf16", "engine_version": None},
    read_options={"expansion_depth": 1, "expansion_items": 5,
                  "expansion_bytes": 32768, "context_bytes": 65536},
)
```

`current_agent_selector(prompt)` returns the response above. The application calls
it once only after the complete input fits. The two-command CLI lets a native
Agent do this using its own current model, without an API dependency. Its model
identity/usage fields are caller reports, not host attestations.

## Scope, cards and conditions

The source is the shared Find evidence collection: supporting Skills, Records
and Cases, excluding primary task entries and the compatibility router. Counts
are dynamic. A custom `--skill-root` replaces the installed library; installed
records remain visible. A read-only `--store` adds its qualified owners. Backend
and kind filters record every exclusion; no lexical ranking or item limit is
applied before selection. Different authorities retain different identities.

Cards derive summary, keywords, applicability, validation state and limitations
from the existing sources, following the layered disclosure direction in #500.
They retain source digests, bundle revisions and available byte sizes. Text
previews are capped with explicit truncation flags. Reference previews show three
edges; full navigation is retained internally and bound to the snapshot. This
caps card fields, never the candidate list. `read_bytes` is the complete bundle
size, not a promise about budgeted context size. Missing parsers/resources remain
visible as unreadable cards, never as successful reads.

Pass a JSON object with `--conditions`. Supported fields are `backend`, `hardware`,
`os`, `model`, `phase`, `engine`, `engine_version`, `dependency_version`, `dtype`,
`workload`, `quality`, and `measurement`. Values are strings or explicit nulls.
Source scalar/list values compare by case-insensitive exact membership. Prose,
version ranges, unknowns and missing fields are **unknown**; no guessed SemVer
ordering or alias normalization is applied. Source content revisions never stand
in for tested engine/dependency versions. Field coverage is reported in the view.
Cards and post-read judgments use the same resolved conditions. If applicability
omits the backend, the entry's declared backend or skill registry supplies it.
The comparison locator identifies the field used. A generic `common` backend
stays unknown. Version wildcards such as `1.4.x` also stay unknown.

A mismatch is **conflict** for a bounded conclusion and **analogue** for a method.
All comparable fields matching yields **match** for those fields only. No supplied
conditions yields **unknown**. These judgments do not change source lifecycle or
verification. The original source is delivered before the final structured
comparison; the Agent must read it, locate any prose-only bounds and explain
claim-specific applicability, missing evidence and minimal target validation.
A hardware-specific conflict does not reject all methods in the document.

## Reads, expansion and trace

Optional navigation follows explicit Markdown links, including owner resources;
external URLs remain pointers. Default expansion is one hop, with separate
optional item/byte limits. Cycles and duplicates, unresolved links, depth/budget
stops and actual resource deliveries are recorded. Deduplication includes revision.
The selected material has its own byte budget. Required skill procedures/resources,
source attribution and license closure are atomic: insufficient space produces an
omission, never a partial procedure marked complete. No imported code is executed.

Catalog checkout skill revisions include declared references, provenance readsets,
third-party notices and applicable ancestor license/notice files up to the
declared root. This larger closure applies only to catalog selection; ordinary
`read`/`resource` retain their existing revisions for unchanged checkout sources.
A change to any required byte changes the catalog revision. Malformed optional
URLs produce an unresolved edge and allow other entries to be read. Invalid or
non-UTF-8 optional resource closures produce a resource-level omission without
discarding other selections; revision conflicts still reject the snapshot.
Within one ref/revision, shared required resources are delivered and charged once.
Each expansion checks its complete closure before budgeting the remaining unique
resources, so deduplication does not permit partial required deliveries.

`context_bytes` counts selected resource `content` plus explicitly requested,
delivered canonical cards. `expansion_bytes` counts only expanded resource
`content`. Both are measured in UTF-8 bytes. For a typed `SKILL.md`, the reader
delivers the procedure with its embedded `metadata.inferrsi` block removed,
records the original file hash and byte ranges, and charges the resulting
procedure bytes. A separately delivered `metadata.json` or `record.json`
counts in full. The output envelope, resource hash fields and retrieval trace
are outside both budgets. The selection prompt has its own serialized-input
token budget.

Top-level omissions use `scope: entry` when a whole entry could not be
delivered. A failed optional resource expansion uses `scope: resource` and
records its path and originating edge in `via`. The owner can already have
delivered other resources. The failed expansion contributes zero bytes.

Results reuse the retrieval observation envelope: snapshot/coverage, selections,
reasons, comparisons, expansion paths, exact resource hashes, omissions, byte
counts and timings. Callback runs additionally retain model/prompt version,
call count and reported usage. Delivery is observable; model reading/adoption
remain unknown unless independently reported. This preserves the discovery,
delivery and use distinctions from #344/#379/#380. An `open` command is never
counted as a successful read.

Functional tests and a ten-query observational comparison do not demonstrate
optimization quality or serving speed. Task benefit remains **INCONCLUSIVE** until
an independently frozen evaluation establishes it. Default-entry promotion is
separate from implementing this mode.

After reading the returned sources, call
`inferrsi.apps.workflows.knowledge.confirm_catalog_evidence(result, assessments)` or add an
`assessments` array to the selection JSON and submit it again. Each assessment
contains `ref`, `revision`, `path`, an exact `quote`, the specific `claim`,
`verdict`, `reason`, `missing` (string list), and `validation_step`. The interface
rejects quotes not present in delivered bytes at that revision. It records a
source-grounded Agent judgment without upgrading source validation or claiming
that citation checking proves the interpretation. The application callback can
use this function after its source-reading turn.

The CLI emits the preparation as compact sorted JSON and counts that exact
transport, including its accounting envelope. Reformatting the prompt, adding
chat framing or other history requires a corresponding host-side allowance.
Record `skill_documents` declarations are expanded as explicit resources. Linked
procedures include their owner files, declared references/readsets/notices and ancestor
licenses atomically; cross-owner Markdown navigation does not become required.
A missing declared resource or unsupported version query stops
that resource expansion with an explicit reason.
