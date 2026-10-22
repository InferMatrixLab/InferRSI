# Campaign summary chart

One figure per campaign that shows every trial's gain against the baseline,
including the trials that gained nothing and the ones that lost ground. It
answers "what did this campaign move, and by how much" without implying that
any single screen is a qualified result.

The renderer is [tools/campaign_summary_chart.py](../tools/campaign_summary_chart.py),
listed in the [operation guide](operations.md#summarize-a-campaign-figure--campaign_summary_chartpy).
It reads a JSON specification and writes SVG plus an optional Markdown table.
It uses only the standard library, so a committed figure reproduces without
installing a plotting package.

## Why gain, not an absolute curve

Trials usually branch off one baseline instead of accumulating on each other.
Drawing them as a rising curve would claim a sequence the campaign never ran,
and would flatten a regression into a step upward. Every row therefore shows its
own gain against the same baseline, and the axis is signed so a loss is visible
left of zero.

## Use it

```bash
python tools/campaign_summary_chart.py evidence/<campaign-id>/results/summary-chart.json \
  -o evidence/<campaign-id>/results/summary-chart.svg \
  --markdown evidence/<campaign-id>/results/summary-chart.md
```

Commit the specification next to the figure. The specification is the source of
truth: it names the measured values, and a reviewer can re-derive the figure and
check each row against the result files it summarizes. Copy
[the example specification](../evidence/_template/results/summary-chart.example.json)
as a starting shape.

## Specification fields

| Field | Required | Meaning |
| --- | --- | --- |
| `title` | yes | Figure title; also the SVG `<title>` |
| `subtitle` | no | Lines under the title: screen protocol, cohort, and what a delta does not prove |
| `unit` | no | Measurement unit shown beside the label-metric value, e.g. `frames/s` |
| `baseline.label` | yes | Which snapshot the gains are measured against |
| `baseline.metrics` | yes | One positive baseline value per metric key |
| `metrics` | yes | Ordered metric list, each `{key, label}`; at most seven per figure |
| `label_metric` | no | Metric whose value is printed and whose gain orders rows; defaults to the last |
| `sort` | no | `gain` (default) orders within a group by gain; `given` keeps specification order |
| `axis.tick` | no | Tick step in percentage points, default `50` |
| `axis.label` | no | Caption under the axis |
| `references` | no | Vertical reference lines, each `{label, metric, value}`; close labels stagger |
| `statuses` | no | Per-status `mark` and `strong` overrides on top of the conventional set |
| `trials` | yes | Each `{group, label, values, status, note}`; duplicate group and label pairs are rejected |

Conventional statuses are `open` (measured, not carried to a repeated
comparison), `rejected` (failed a frozen gate), `flat` (no gain against its
parent) and `regressed` (slower than baseline). `flat` and `regressed` carry a
`×` mark; a campaign may rename or add statuses through `statuses`.

Malformed specifications fail with a message naming the field, instead of
rendering something misleading. Every trial must supply every declared metric.

## Rules for the surrounding text

- Say in the subtitle how many requests and repeats a screen used. A single-run
  screen is not a confirmation.
- Keep the disposition column populated. A row without one reads as a qualified
  gain.
- When a change alters the workload rather than the implementation (a different
  window, sequence length or batch geometry), say so; such rows do not add up
  with the kernel rows.
- Do not use the figure to claim a `PASS`. It summarizes recorded results; the
  verdict still comes from the frozen gates.
