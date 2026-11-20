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
after `stale_snapshot`; there is no silent substitution. Snapshots are regenerated
before reads and checked again after assembly, including dependency changes.
Snapshots are content identities, not an authorization credential.

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
