# Indexer limit-saturated serialization study — Issue #255

**PASS for this bounded CPU retrieval campaign under its prospectively frozen protocol, including independent saved-output/resource audit.**

This candidate is distinct from the rejected historical resource memo. It removes only redundant view-size serialization after the item count is full for exact normal Bundle instances. Subclasses retain the prior serialization/error behavior. All reads, full resource validation, ranking, filters, query checks and omission order still run. This does not improve retrieval accuracy or close #255.

## Controlled result

| Path | A p50 ms | B p50 ms | p50 change | A p95 ms | B p95 ms | p95 change | A/B CPU p50 ms | n/arm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| context_api | 709.98 | 669.06 | -5.764% | 1334.15 | 894.67 | -32.941% | 709.81/669.01 | 120 |
| default_api | 830.52 | 778.98 | -6.205% | 1495.02 | 1138.81 | -23.826% | 829.67/778.88 | 120 |
| default_cli | 1123.31 | 1083.29 | -3.563% | 1575.09 | 1621.67 | +2.958% | 1122.36/1081.72 | 120 |
| search_cli | 209.69 | 210.75 | +0.507% | 349.68 | 381.13 | +8.992% | 209.07/208.56 | 120 |

Primary statistic is the median of within-pair reductions, **9.434%**, percentile-bootstrap95%CI **4.603–13.337%**; it differs from the ratio of marginal p50s. Frozen threshold≥5% with lowerCI>0 passes. Secondary p50≤10%/p95≤20% point guards and p50 upper95%CI≤10% all pass.

Untouched search CLI p95 uncertainty remains wide (−42.025%…+32.846%). This sampled tail is not a production SLO or proof of absence of any tail regression. Its point guard passes; the p95 interval was prospectively descriptive. API process CPU and CLI child CPU track median wall time closely here; this observation does not retroactively explain or waive the historical CLI failure.

## Reproducibility and preserved history

- Baseline `f93df0548a26714f6514337a8525c7c14108acad`; candidate `9f7862a9f8619dd68ac59f12736f6b50da10d9e8`; tree `261645a7adc0ac097281096df6752ef7fec394f8`.
- Protocol SHA256 `d577712b231be4bf33e66d401da22d50a38b01951707dae7a65b8d9c2dfc6a44`; runner `fe46d6fdfecccd5ce3fe8ac517aa8db39dc7c7dacf1aae775b62a7f3b5cc9760`.
- One execution,120 balanced randomized AB/BA pairs (seed25530), paired bootstrap10,000 resamples (seed25531). Started2026-10-30T08:08:51Z, terminal~08:29Z. No samples removed, pooled or repeated; no interim outcome-based stop.
- Fixed queries: primary default Collect(query="",limit=5), context Collect(relevance="memory",limit=5,context_bytes=262144), matching full default CLI, untouched catalog CLI(query="cgroupv2",limit=5). API reused-reader warmup and fullCLI startup policies are in frozen protocol. Fresh process is not cold filesystem cache.
- Exact source/corpus identities before/after match. All480 paired path outputs have matching SHA256/bytes; default API and CLI outputs also match each arm. Full first-pair captures and all completed-arm receipts retained.
- Historical resource-cache v1 FAIL, separate confirmation uncertainty, accuracyv2/v3 FAIL and cue-study negative evidence remain unchanged. No old sealed heldout was accessed or evaluated.

## Deterministic correctness and limits

- Synthetic counter test reduces view-size serializations3→1 atlimit1; all3 bundles still read. Byte-budget-only omissions still size every item until count saturation.
- Invalid normal resource after saturation still reports invalid; custom nonserializable subclass view still raises TypeError after saturation. Invalid0/None/negative/bool limits still rejected.
- Initial focused source tests79 passed/2Windows skips (81 selected), Ruff passed. Broader affected suite:113 passed,2 Windows-only skips in53.73s, including operations,store,CLI,selection and new sizing tests; no full-suite claim. Full repository src/tests/tools Ruff passes.
- Dominant scan/full-resource hashing work remains O(N+B_total), where B_total sums bytes hashed over all candidates (shared resource bytes may be hashed repeatedly); this is a small CPU retrieval improvement on the specified workloads, not service/model/hardware benefit. No peak-memory measurement or accuracy gain claim.
- Current evidence supports considering this small runtime change for scoped review, not closing the accuracy half of #255. Independent saved-output audit verified120groups,240arm receipts,480paired mode comparisons, exact bootstrap recomputation, unchanged source and5contexts/17required resources with exact bytes/hash/revision (138807bytes total). See `independent-review.json`.

## Efficiency versus accuracy tracker

| Axis | Evidence | Status |
| --- | --- | --- |
| This bounded efficiency change | Primary paired reduction9.434%, CI4.603–13.337%; exact output/resource parity | PASS for frozen workload; review/publication separate |
| Retrieval accuracy improvement | No ranker/corpus/query changes; paired results unchanged in this study | Not established; remains open |
| Historical accuracyv2 / v3 | Hit4/6→5/6 but MRR0.5833→0.5417 /0.5333 on their older pinned corpus | Both FAIL; no heldout evaluation |
| Historical cue feasibility | Blind preparationINCONCLUSIVE; covered synthetic cue MRR29/36→29/36 | No demonstrated improvement |

The [earlier consolidated table](../../indexer-255-covered-cue-20261030/results/consolidated-results.md) retains all historical baselines and uncertainty. Its numbers are not new measurements on this baseline. No knowledge-corpus quality or #255 closure is inferred from this performance PASS.
