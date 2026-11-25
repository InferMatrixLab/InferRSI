# Retrieval explanations and evidence navigation

The Dashboard's **Knowledge retrieval and evidence navigation** panel reads
recorded retrievals and `campaign import-search` records. Both dashboard layouts,
Run review, offline HTML and live refresh use the same projection. Select a
round, a capture, an item, and an exact candidate/run. The run links back to its
captures and search records. Missing relationships are shown explicitly.

The implementation builds on the round records delivered by PR #384, Run review
from PR #401, and the experiment identities and navigation from PR #405. The
implementation PR records the exact main revision used for validation. These
interfaces do not depend on unfinished general statistics or workflow proposals.

## Round decisions

The **Round decisions / 逐轮决策** panel shows five stages
for the selected round, in both layouts and in offline/live views:

| Stage | Recorded source and meaning |
| --- | --- |
| Bottleneck analysis | The bottleneck and measurement summary recorded by `campaign diagnose`. A retrieval or submitted round links the diagnosis to that round. Diagnoses awaiting a link appear under **Round not recorded**. For runs with a reviewed optimization trace, the panel shows the conclusion and timed scope when the attached profile matches the recorded source digest. |
| Retrieval results | Explicitly linked capture IDs, shared search records and older managed snapshots linked at submission. The panel shows returned entries, versions, assembly or omission, and caller-declared use or rejection. Shared search queries and expandable request/event evidence remain available even without a capture. Open the capture for its full evidence. |
| Alternatives | That candidate/run's `optimization_trace.search_space`, plus option IDs explicitly referenced by the round's optimization-log candidates. The campaign-wide search space is a separate disclosure, not a reconstructed round shortlist. |
| Final selection | Caller-declared candidate/option choices, reasons, knowledge references and trace attempts. This is selection **to try**, not adoption after validation. |
| Execution results | Every recorded candidate/run in the round, its verdict, quality, measured values and post-validation decision. Caller decisions remain separate from run records; disagreements are visible. Open the exact run for change and execution evidence. |

For an older managed capture with no recorded retrieval round, the dashboard
verifies the file's SHA-256 and matches its path, kind and digest against the
references retained by each submission. Every matching round shows the snapshot,
including a pending round. The retrieval round stays unknown. If the capture has
a recorded retrieval round, the dashboard shows it on that round. The candidate
declares use of individual items separately.

The selector starts at the earliest explicitly recorded round. Records without
a round appear under **Round not recorded**; their position never implies
round 1. Missing snapshots, alternatives, selection reasons and results remain
missing. A trace's caller-written context is labelled separately from a retained
retrieval snapshot. Tampered captures cannot supply returned entries or assembled
context, and cross-round association conflicts remain visible. Knowledge
declarations do not establish consumption or causal performance improvement.

Round selection, expanded details and keyboard focus survive live updates;
language changes retain the selected round and expanded details. The columns
adapt to the panel's available width, including the narrower profile layout.
The profile layout keeps this panel collapsed initially; its **Round decisions**
navigation link opens it, preserving the existing trend-first landing view.

This is a read-only presentation of existing contracts. It does not collect
missing history, create a second control record for managed campaigns, or
complete the real-campaign workflow integration tracked by #491. Managed
campaigns still use the shared Harness controller; do not use legacy record or
decision operations to fill their missing associations.

The following screenshots show the implemented panel using synthetic inputs
and synthetic measurements; they are not real optimization results:

- [Default layout, round 1 in Chinese](../../assets/dashboard-round-decisions-default-zh.png)
- [Profile layout, round 1 in Chinese](../../assets/dashboard-round-decisions-profile-zh.png)
- [Mobile profile layout in Chinese](../../assets/dashboard-round-decisions-mobile-zh.png)

## Execution observations

`campaign capture-context` uses Find ranking for a single free-text question,
then assembles selected material through Collect. The capture records both
operations. Pass one question as a positional query or `--relevance`. Explicit
IDs select material in caller order. See the [migration guide](../operations.md#migrate-old-text-queries)
for callers that previously passed a separate query filter and ranking cue.

```sh
inferrsi find 'decode launch' --explain --json
inferrsi campaign capture-context --directory <CAMPAIGN_DIRECTORY> --id r1-context \
  --relevance 'decode launch' --context-bytes 65536
```

To capture an installed Case at its observed revision, select the bundled
library and use the ID and revision from the read:

```sh
inferrsi campaign capture-context --directory '<CAMPAIGN_DIRECTORY>' --id r1-case \
  --installed-library --id-ref 'checkout:<CASE_ID>' \
  --revision 'checkout:<CASE_ID>=<REVISION_FROM_READ>'
```

The capture records the requested pin. A stale revision is recorded as
`unavailable_revision`. A capture that records explicit IDs is a read. A capture
of a queryless inventory is an inventory operation. Both retain their items and
revisions in the round record. The search and hit totals count text discovery.

`knowledge search --explain` returns a JSON envelope with `items` and `retrieval`.
Python callers use `search_knowledge(..., explain=True)` for the same
catalog envelope. `collect` includes a `retrieval` member outside its
budgeted item and resource payloads.

| `retrieval` field | Meaning |
| --- | --- |
| `schema_version` | Observation contract version, currently 1 |
| `entrypoint`, `calls` | Actual entry and wrapper chain, recorded at execution |
| `implementation` | Package name and available installed version; unknown stays unknown |
| `request` | Query/cue, explicit IDs/revisions, source categories, filters and budgets; no store/checkout absolute path |
| `selection` | Method/version, scope, `ranking_applied`, state and tie rule |
| `items[]` | Returned order, ref, exact version, available score and components |
| `counts` | Considered, matched, returned and exclusion counts observed in this invocation |
| `assembly` | `performed` or `not_requested`; old missing evidence is `unknown` |
| `candidate_details` | `not_recorded`: no reconstruction of a full rejected candidate set |

A catalog text query records `knowledge search → find` and returns catalog
records. Its `catalog-sha256:` revision hashes the returned record using sorted,
UTF-8 JSON. It identifies those catalog bytes. A Collect revision identifies the
normalized bundle used to deliver resources.

Find records each matching term's contribution and uses recorded state,
identity and qualified reference to break score ties. Explicit IDs preserve
caller order and skip item ranking. A plain inventory records `not_requested`.
Older captures retain the scores, components and method identifiers recorded in
their original run. Filters use first-exclusion
counts; these are not overlapping marginal totals. Per-item explanations cover
returned items only. Existing omissions and resource hashes remain available.

Scores are recorded during execution, never recomputed from current knowledge
or weights when loading history. A historical method name without an explicit
execution flag does not establish that ranking ran. Missing entry-point metadata
is displayed as unknown, even if a current default would appear plausible.

## Retain a standalone result

`save_retrieval` can retain an already executed catalog or collect result in the
same immutable capture envelope used by `capture-context`:

```python
from pathlib import Path
from inferrsi.knowledge.catalog import search_knowledge
from inferrsi.apps.workflows.campaign import save_retrieval

result = search_knowledge("decode launch", explain=True)
path, sha256 = save_retrieval(
    Path("<CAMPAIGN_DIRECTORY>"), context_id="r1-catalog", result=result,
)
```

The campaign must already exist. Use a fresh ID; an existing capture is never
replaced. A catalog snapshot does not assemble context. Absence of assembly is
not a budget rejection. Returned refs, prepared resources, caller declarations
and review-supported associations are separate stages. Resource/capture hashes
establish byte consistency, not model receipt, authorship or actual use.

Capture item metadata retains the item's declared `skill_documents` and
entrypoint, not its bundle-wide dependency manifest. Prepared resource paths,
hashes and bodies remain in `contexts[]`; resource omissions and the original
assembly byte budget are retained independently.

## Connect a new round

1. Save the retrieval while working, using `capture-context` or
   `save_retrieval`. Retain the returned capture hash.
2. Register the candidate and its exact run using `campaign record`. Retain code
   locations/revisions in `--details-json` and the existing run artifacts.
3. Add the capture ID/hash to `knowledge[]`, and its ID to the matching
   `iterations[].context_ids`. Name the candidate in that iteration and record
   knowledge references and caller decisions explicitly. Submit a new version
   with `campaign log`; do not edit a previously retained log or input.
4. Import the round's captures and, when available, its explicitly bounded local
   trace with `campaign import-search`. Use `--archive-review` for the existing
   portable v2 passage-to-decision contract. A decision citing a rendered
   resource from a verified `find` or `collect` capture supplies `passage_path`
   with the resource's bundle-relative key. Its `passage_line` counts from the
   first line of that resource. See [the import contract](../../dashboard.md#import-one-rounds-searches)
   for the input fields. Mark complete coverage only when established.
5. Append results and decisions using existing campaign operations. A closing
   import may extend the same trace window/add captures and runs, subject to the
   importer's preservation, overlap and repeated-import rules.

The legacy manual campaign operations above are for externally recorded
campaigns. Managed optimization sessions retain their controller-owned state;
this read-only dashboard extension does not create another controller.
For a managed AB/BA or benchmark capture selected with `--context-id`, the
importer looks for the complete `campaign knowledge` or
`benchmarks session knowledge` JSON tool return in the trace window. The returned
capture reference and contents must match the saved capture. Delivery is recorded
for matching resource blocks even when the round has no use citation. Reviewers
can also supply the return line in `capture_returns`. A managed query without a
verified matching capture keeps coverage partial and complete counts unavailable.
[Service-reuse campaigns](../service-reuse-campaigns.md#records-compatibility-and-validation)
retain knowledge in their own fingerprint-free format, outside this importer.

A manual `campaign capture-context` text query likewise needs its selected
`--context-id` and a matching tool receipt to establish complete coverage.
The receipt records preparation. A matching resource body in a tool return
establishes delivery separately. Queryless inventory and explicit ID assembly
can be retained with zero searches.

Reasons in a submitted managed hypothesis or a manual optimization log can
carry an explicit use citation. The importer aligns it with the verified
delivered passage and later decision position without hand-entered evidence
line numbers. See the [round reason workflow](../../dashboard.md#cite-a-passage-in-the-round-reason).

Multiple metadata records may explicitly identify the same candidate and
round with different `run_id` values. The importer retains all of them, including
failed and INCONCLUSIVE results. Repeated candidate/run metadata is ambiguous
and is rejected. The view never chooses the newest/first run. Historical
candidate-only summary references retain their existing ambiguity warning.

## Shared records and degradation

The view reads local `search/round-<n>.json` (v1) and portable
`search/archive/round-<n>.json` (v2) through bounded, campaign-contained reads.
It reuses the importer's reviewed-association checks on saved v2 evidence.
It does not reopen the private conversation or re-certify the review's author.

- v1 `use`/`evidence` retains local v1 semantics, including log declarations and
  caller-reviewed line references. It never becomes v2 review evidence.
- v2 `declarations` remains caller declarations. Only
  `materials[ref].evidence` with supported, consistent `archive_reviewed` links
  is labelled an archive-reviewed association. Passage/event/decision ordering
  and identity mismatches are visible.
- `counts: null` remains unknown; `observed` is displayed separately. v1 and v2
  are alternative projections of the same round and are never summed.
- Unsupported versions, invalid source metadata, capture or revision mismatch,
  missing artifacts, conflicting rounds and candidate/run mismatches remain
  visible. No relationship is inferred from titles, times or summary prose.
- Empty `used_refs` means that field did not record use. Shared search evidence
  can still document another declaration or association. A declaration about
  an omitted context remains visible with its conflict/omission state.

To supplement history, create a new optimization-log version that cites an
existing, verifiable capture and explicit candidate/round identity. Reimport
only evidence that satisfies the importer's original boundaries. If the original
search was not captured, leave it unknown; a new search is a new capture, not a
reconstruction of the historical search.

Queries, paths and excerpts pass through the existing display redactor even
when their hashes verify. Public GitHub source locators can be retained; private
URLs, absolute paths and credential-like values are withheld/redacted. The
redactor is not a publication review: inspect the complete bundle before sharing.
Display redaction does not rewrite frozen originals. Hashes identify original
bytes and do not authenticate a redacted display.
Redaction preserves the complete text even when replacement markers are longer
than their input. Both layouts repeat the original-byte hash explanation beside
the full assembled context.

## Offline example and checks

```sh
PYTHONPATH=src python tests/fixtures/knowledge_retrieval.py <OUTPUT_DIRECTORY>
pytest tests/apps/test_retrieval_projection.py
pytest tests/apps/test_knowledge_navigation_browser.py
pytest tests/apps/test_round_decisions_browser.py
```

The browser tests require Playwright and Chromium. Open the generated
`dashboard.html` directly. It includes five selected/two assembled/three omitted
items, all three entry paths, two linked optimization rounds, multiple searches,
two runs for one candidate, FAIL/INCONCLUSIVE/no-gain results, local v1, portable
v2, partial/missing coverage, declarations, reviewed evidence and historical gaps.
Its synthetic scores and performance values are not optimization claims.

### Synthetic screenshot examples

These retained examples show the two layouts before the later validation and
focus fixes. They illustrate synthetic fixture data, not current test execution
or model performance. Current browser results are recorded in the implementation
PR and CI.

| View | Default layout | Profile layout |
| --- | --- | --- |
| Capture selection and budget | [Capture](../../assets/dashboard-knowledge-default-capture.png) | [Capture](../../assets/dashboard-knowledge-profile-capture.png) |
| Run details and return navigation | [Run review](../../assets/dashboard-knowledge-default-run-review.png) | [Run review](../../assets/dashboard-knowledge-profile-run-review.png) |
| Shared v2 records | [Archive](../../assets/dashboard-knowledge-default-archive-v2.png) | [Archive](../../assets/dashboard-knowledge-profile-archive-v2.png) |
| Chinese narrow viewport | [Mobile](../../assets/dashboard-knowledge-default-mobile-zh.png) | [Mobile](../../assets/dashboard-knowledge-profile-mobile-zh.png) |

The delivery includes existing-field projection, execution observations and
shared-record navigation. It does not deliver a general token/cost ledger,
complete rejected-candidate collection, performance attribution, H3 replay, or
acceptance of the broader statistics/workflow issues. Maintainer review and
issue-level acceptance remain separate from a merged implementation PR.
