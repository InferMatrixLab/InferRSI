# results/ (template)

- Metrics, logs, profiler exports  
- Verdict rationale: `PASS`, `FAIL`, or `INCONCLUSIVE`  
- Links to baseline vs candidate comparison artifacts

A campaign-level figure of every trial's gain comes from
[tools/campaign_summary_chart.py](../../tools/campaign_summary_chart.py). It also
renders automatically into the experiment report, and reads a committed
`summary-chart.json` beside the run when a campaign has several steps:

- [summary-chart.example.json](summary-chart.example.json) — `chain`: ordered
  steps that accumulate, drawn as a gain-over-time line.
- [summary-chart-branch.example.json](summary-chart-branch.example.json) —
  `branch`: independent trials on one signed gain axis, including no-gain and
  loss rows.

Copy the shape that matches the campaign, replace the values with measured
results, and commit the specification with the figure. See the
[campaign summary chart guide](../../docs/campaign-summary-chart.md).
