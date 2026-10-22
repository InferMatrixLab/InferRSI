# results/ (template)

- Metrics, logs, profiler exports  
- Verdict rationale: `PASS`, `FAIL`, or `INCONCLUSIVE`  
- Links to baseline vs candidate comparison artifacts

A campaign-level figure of every trial's gain, no-gain and loss rows included,
comes from [tools/campaign_summary_chart.py](../../tools/campaign_summary_chart.py):
copy [summary-chart.example.json](summary-chart.example.json) beside the result
files, fill in measured values, and commit the specification with the figure.
See the [campaign summary chart guide](../../docs/campaign-summary-chart.md).
