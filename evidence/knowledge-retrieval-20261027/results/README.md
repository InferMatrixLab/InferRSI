# Completed bounded retrieval results

The full 24-case quality comparison and 20-pair CPU benchmark passed their
prospectively frozen gates. This is local offline retrieval evidence;
human/maintainer acceptance, merge and Issue closure remain separate.

- `quality.json`: 96 outputs per revision exactly equal; 20 partial-labelled
  positives and four negative probes. Existing #129 relevance-item behavior
  was preserved, not introduced or improved by this manifest patch.
- `benchmark.json`: 20 balanced groups, 640 API calls and 160 CLI processes;
  hot relevance paired-median reduction 40.0068267%, 95% interval
  [38.3789227%, 41.0592071%]. All 400 output pairs and 80 stdout pairs equal;
  final source/corpus identities unchanged.
- `performance.md` and `latency-summary.json`: complete per-mode/query p50/p95
  display, including regressions. CLI relevance decode p95 rose
  1.810 to 3.046 ms; no cause or blanket tail improvement is inferred.
- `context-delivery-diagnostic.json`: post-hoc API-response context presence
  for 19/20 labelled owners, separate from the frozen item-ranking metric.
- `baseline-profile.json` and `baseline-trace-129.json`: separate source/path
  diagnostics, excluded from performance samples.
- `validation-summary.md`, `environment.md`, `independent-review.md`: local
  failed-suite/baseline reproduction, package checks, hardware/interpreter
  limits and independent read-only review with unknown reviewer model/effort.
- `architecture/`: editable EN/ZH SVGs, PNG previews, source, layout checks
  and reproducible source notes; these diagrams establish software contracts.

Files named `dry-run-*` are baseline-v-baseline mechanics only and explicitly
INCONCLUSIVE. Their two cases/two paired groups are not pooled into formal
results. Validator synthetic selfchecks include optimized Python and missing
measurement cases; they are not retrieval performance samples.

The whole Windows pytest attempt was not green. All initial failures/errors
were reproduced on baseline; focused manifest/inventory checks, isolated
package construction and wheel-only source/output parity checks passed.
Remote CI is pending at PR creation. No model, GPU, service, production-query
or agent-task experiment ran, and partial AI-authored source labels are not
human gold or complete Recall.
