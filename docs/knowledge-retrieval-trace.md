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

## Execution observations

`knowledge search` and `collect` remain separate operations. Neither calls the
other. `campaign capture-context` calls `collect`; its default task relevance
policy is unchanged. There is no global listener or automatic capture.

```sh
inferrsi knowledge search 'decode launch' --explain
inferrsi collect --relevance 'decode launch' --json
inferrsi campaign capture-context --directory <CAMPAIGN_DIRECTORY> --id r1-context \
  --relevance 'decode launch' --context-bytes 65536
```

`knowledge search --explain` returns a JSON envelope with `items` and `retrieval`.
Without that flag, its list API, JSON and tabular output are unchanged. Python
callers use `search_knowledge(..., explain=True)`. `collect` adds a `retrieval`
member outside its budgeted item/resource payloads. Existing item revisions,
return order, `material_bytes`, context assembly and byte budgets are unchanged.

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

Catalog scores count query-term occurrences in the searched JSON; repeated terms
remain repeated components. Ties use ascending ID. A catalog observation's
`catalog-sha256:` revision hashes the returned catalog record using sorted,
UTF-8 JSON. It identifies that record, not a collect bundle or an upstream commit.

The two weighted methods record title, summary, tags/applicability and body
contributions. Task relevance records title, summary, tags, repo/scenario,
applicability and body contributions plus its platform multiplier. Ties use
ascending qualified ref. Explicit IDs preserve caller order and skip ranking;
no relevance request records `not_requested`. Filters use first-exclusion
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
from inferrsi.apps.campaign import save_retrieval

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
   portable v2 passage-to-decision contract. See [the import contract](dashboard.md#import-one-rounds-searches)
   for its input fields. Mark complete coverage only when established.
5. Append results and decisions using existing campaign operations. A closing
   import may extend the same trace window/add captures and runs, subject to the
   importer's preservation, overlap and repeated-import rules.

The legacy manual campaign operations above are for externally recorded
campaigns. Managed optimization sessions retain their controller-owned state;
this read-only dashboard extension does not create another controller.

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
pytest tests/test_retrieval_projection.py
pytest tests/test_knowledge_navigation_browser.py
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
| Capture selection and budget | [Capture](assets/dashboard-knowledge-default-capture.png) | [Capture](assets/dashboard-knowledge-profile-capture.png) |
| Run details and return navigation | [Run review](assets/dashboard-knowledge-default-run-review.png) | [Run review](assets/dashboard-knowledge-profile-run-review.png) |
| Shared v2 records | [Archive](assets/dashboard-knowledge-default-archive-v2.png) | [Archive](assets/dashboard-knowledge-profile-archive-v2.png) |
| Chinese narrow viewport | [Mobile](assets/dashboard-knowledge-default-mobile-zh.png) | [Mobile](assets/dashboard-knowledge-profile-mobile-zh.png) |

The delivery includes existing-field projection, execution observations and
shared-record navigation. It does not deliver a general token/cost ledger,
complete rejected-candidate collection, performance attribution, H3 replay, or
acceptance of the broader statistics/workflow issues. Maintainer review and
issue-level acceptance remain separate from a merged implementation PR.
