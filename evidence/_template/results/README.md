# results/ (template)

- `summary.json`: compared variants, metric definitions, conditions, sample and
  failure counts, repetitions, variability, performance/quality and limitations.
- `trials.jsonl`: one row per attempted trial, including failures and interruptions.
- `artifacts.json`: authoritative versioned archive metadata, based on
  [artifacts.example.json](artifacts.example.json).
- Verdict rationale: `PASS`, `FAIL`, or `INCONCLUSIVE`.
- Raw requests, logs, profiler exports and media belong in the external archive.

Example trial row (replace all placeholders; regenerate it from control records):

```json
{"id":"<attempt-id>","configuration":{},"status":"interrupted","conclusion":"INCONCLUSIVE: <reason>","artifact_id":"<archive-id>","source_record":"control/trials.jsonl#<record-id>"}
```

`source_record` identifies the original control record, not just a configuration
name. Repeated configurations remain separate trials. Compare the regenerated
index and summary using the [verification procedure](../validator/README.md).

A campaign-level figure of every trial's gain comes from
[tools/campaign_summary_chart.py](../../../tools/campaign_summary_chart.py). It also
renders automatically into the experiment report, and reads a committed
`summary-chart.json` beside the run when a campaign has several steps:

- [summary-chart.example.json](summary-chart.example.json) — `chain`: ordered
  steps that accumulate, drawn as a gain-over-time line.
- [summary-chart-branch.example.json](summary-chart-branch.example.json) —
  `branch`: independent trials on one signed gain axis, including no-gain and
  loss rows.

Copy the shape that matches the campaign, replace the values with measured
results, and commit the specification with the figure. See the
[campaign summary chart guide](../../../docs/campaign-summary-chart.md).
