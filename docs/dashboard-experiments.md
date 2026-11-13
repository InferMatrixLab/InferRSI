# Experiment curves and evidence events

The performance overview and **Successes and failures** use the same absolute
measurement projection, filters and selected identity. Both dashboard layouts
embed the same renderer; offline HTML needs no network or CDN. Live refresh
restores the selected measurement/event by identity. A removed record is reported
as unavailable rather than selecting another run.

This implements the visualization scope of [RFC #392](https://github.com/InferMatrixLab/InferRSI/issues/392)
and its proposed contract refinements. It does not accept or close the RFC,
rerun a campaign, change frozen gates, or establish a performance verdict.

## Reading the view

- The default x axis is an explicitly recorded round. Explicit order and
  timezone-bearing timestamps have separate axis modes; they are never mixed.
  Missing positions appear in **Unpositioned records** and the complete table.
- Workload, metric, unit, scope, statistic and direction define separate axes.
  HTTP/E2E seconds and component milliseconds never share an axis or line.
- Lines connect only complete, matching comparison configurations. A missing
  value breaks the line; events do not become zero-valued measurements. Repeated
  runs at the same x remain separate points, with no inferred order or average.
  Segments incident to repeated x positions are withheld to avoid picking a run.
- The event lane and buttons include run states, recorded execution/quality
  events and every original success/failure statement. Event-only workloads
  remain selectable. Recorded scopes bind markers to the appropriate panel;
  unscoped events stay in the shared event list rather than being assigned a scope.
- Hover, focus, Enter/Space or click selects evidence details. A candidate-only
  link matching multiple runs offers a run chooser. A plotted measurement opens
  its precise run or explicitly identified external source record.
- Narrative classification, quality, execution state and evidence verdict stay
  separate. A target gap is arithmetic, not an acceptance verdict. A failed
  quality check can coexist with a valid measurement below the numeric target.
- **All records** is the accessible measurement/event table. The original summary
  remains expandable, including partial state, limitations, lessons and references.
  Missing or unresolved artifacts display their unavailable state.

## Adapter and projection contract

`dashboard_experiments.py` owns axis/comparison eligibility, stable identities,
reference conversion and explanatory reasons. `optimization_story` remains a
narrative consumer with its existing schema. Nothing rewrites an input artifact.

| Projection field | Native harness source | External v1 source |
| --- | --- | --- |
| Campaign / candidate / run | Campaign and candidate metadata | Campaign/candidate metadata; external records have no synthetic native run |
| Measurement identity | Actual run + `evaluation.json#/candidate/median` | Explicit metric `id`; otherwise record SHA-256 + JSON pointer `/metrics/N/aggregate` |
| Round | Candidate metadata / recorded rounds, with existing ambiguity checks | Same |
| Order / timestamp | Timestamp of first recorded candidate measurement event; order absent | Metric `order` / timezone-bearing `timestamp`; event `time` |
| Workload | `run.lock.json.workload_id` | Metric `workload` |
| Metric / unit | Evaluation; locked metric/unit are display fallbacks | Metric `name` / `unit` |
| Scope / statistic | Locked `comparison_scope` / evaluator median | Metric `scope` / `aggregation` |
| Value / sample count | Evaluation `candidate.median` / length of recorded finite `candidate.values` | Metric `aggregate` / explicit positive integer `sample_count` |
| Direction | Evaluation `minimize` or `maximize` | Explicit metric `direction` |
| Comparison | Existing private native signature plus exact candidate command, repetitions and required trial checks | Explicit metric `configuration` below |
| Quality / verdict | Recorded validator and evaluator | Existing `quality.verdict` and `performance_verdict` |
| References | Paired evaluation baseline and locked `min_improvement_pct` | Explicit metric `references`; old baseline/target remain unclassified |

Point identity covers campaign, experiment and measurement. Native experiment
identity includes candidate/run. External experiment identity includes candidate
and source-record path; it is labelled as such. Explicit metric IDs must be
unique within the record. Missing/duplicate IDs fall back to the immutable
artifact pointer, so replacing that artifact invalidates those fallback
selections. Stable explicit IDs survive value updates and input-array reorder.
Changing a source-record path creates a new external experiment identity.
Narrative events use the recorded log version and entry location; native events
use the run's append-only event source and line. External events use a unique
explicit event `id` or the immutable source-record hash and event location. These are source locations,
not inferred experimental order.

### Comparison boundaries

The series key includes all six axis dimensions and comparison configuration.
Two unknowns never prove equality. Explicit dimensions may allow an isolated
measurement even when configuration is incomplete; missing axis information
keeps it in the table with a reason. Unknown direction never defaults to minimize.

Native lines retain the original checks on model/revision, workload, scenario,
backend, scope, metric/unit/direction, baseline source snapshot, baseline command,
selected devices, validator and verified environment. Exact candidate commands,
repetition count and required trial checks add constraints. In particular,
changing candidate flags cannot bypass comparability through a shared baseline.
Private command/environment values are consumed only in memory. The projection
exports opaque equivalence classes, not their values or hashes. Original
aggregate gain/adjudication rules remain unchanged.

External `configuration` requires the following explicit values:

```json
{
  "model": "synthetic-model",
  "model_revision": "fixture-v1",
  "shape": "1024x1024",
  "batch": 1,
  "precision": "bf16",
  "hardware": "synthetic-device-class",
  "protocol": "http-warmed-v1"
}
```

All fields except positive integer `batch` are nonempty strings. Whitespace-only
values (including Unicode whitespace) are unknown for both required and optional
string fields and cannot form a comparable series. `shape` explicitly
identifies resolution/tile/input shape for the workload; use a recorded
`not_applicable` value only when the adapter can establish that fact. Optional
`server_profile`, `runtime` and `measurement_protocol` also participate when
present. Missing, redacted, invalid or unsupported configuration fields prohibit
joining; no names, environment hashes or prose supply missing dimensions.
The adapter must include every configuration affecting comparability. Hashes
verify source bytes, not the scientific sufficiency of that declaration.

The optional fields are additive to external v1. Each member of `metrics` is
one measurement, so a multi-workload result must be adapted into explicit metric
entries. An aggregate across workloads is never split by guessing names or
extracting numbers from narrative. Existing sample/aggregate validation remains.

### References and target conversion

Each reference lives inside one structured metric and inherits its workload,
metric, scope, direction and configuration. It includes `id`, `role`, `unit`,
`value`, and nonempty `provenance`. Roles are `local_baseline`,
`external_reference`, and `frozen_target`. Targets require `frozen: true`.
References remain in details even when an invalid or underspecified definition
prevents a line. Short reference-line segments are drawn at the applicable
experiment's x, avoiding a campaign-wide line for incompatible local controls.

The default `definition` is `absolute`. Two explicit frozen target conversions
are supported; `relative_to` must resolve to one positive, absolute reference:

| Definition | Required direction/domain | Absolute target |
| --- | --- | --- |
| `improvement_pct` | minimize, `0 ≤ p ≤ 100` | `B × (1 − p/100)` |
| `improvement_pct` | maximize, `p ≥ 0` | `B × (1 + p/100)` |
| `inverse_latency_ratio` | minimize, `r > 0` | `B / r` |

`unit` denotes the output metric unit, also for a percentage/ratio definition.
Original value, definition, formula, provenance and applicability remain visible.
Non-finite results, invalid domains, missing direction, ambiguous references,
unfrozen targets or unit mismatches produce reasons and no line. A minimized
metric's gap is `value − target`; a maximized metric's gap is `target − value`.
Positive means short of target. The UI currently offers absolute measurements
only, with no performance-index or relative-gain axis.

An external author-reported reference stays external even when it defines a
frozen target. It never becomes a local optimization control. Legacy external
`baseline`/`target` numbers lack role/freeze provenance and remain available in
details, with no inferred reference line. The older snapshot `chart` SVG is
retained for existing API consumers; the interactive HTML uses `experiments`
for both overview and summary instead of displaying that legacy index chart.

## Reproduce the synthetic example

The fixture generator writes only to its supplied output directory. It includes
W1/W2/W3, compatible experiments, incompatible precision, two unknown hardware
configurations, native and external repeated runs, component scope, missing
artifact, undated and legacy records, a quality failure, a capture failure,
three reference roles, a maximize metric, and a partial story.

```bash
python tests/fixtures/dashboard_experiments.py /tmp/dashboard-experiment-example
# Open /tmp/dashboard-experiment-example/dashboard.html locally.
pytest tests/test_dashboard_experiments.py tests/test_dashboard_external.py
# Optional real Chromium tests, including both layouts' actual loopback refresh:
python -m pip install playwright
python -m playwright install chromium
pytest tests/test_dashboard_experiments_browser.py
```

[English screenshot](assets/dashboard-experiments-en.png) ·
[Chinese screenshot](assets/dashboard-experiments-zh.png) ·
[Evidence detail](assets/dashboard-experiments-evidence.png) ·
[Narrow screen](assets/dashboard-experiments-mobile.png) ·
[Blank configuration regression](assets/dashboard-experiments-blank-config.png) ·
[Offline HTML example](examples/dashboard-experiments.html).
All shown numbers and identities are synthetic. These artifacts demonstrate the
visualization, not accelerator performance or campaign PASS. Browser checks
cover keyboard selection, exact run navigation, shared filters, time mode,
Chinese narrow layout, table access, live reorder/value updates and disappearing
selections. Automated browser tests require optional Playwright and its Chromium;
they do not certify every browser or screen reader.

In the `profile_first` layout, all review panels are collapsed on initial load,
including the top performance trend and successes and failures. Their curves,
events and original records are available by expanding the corresponding panel.
Opening or closing these panels is preserved during language changes and live
data refreshes.

The round axis shows `R<round>` and abbreviated recorded experiment titles below
the event track. Hover over a title to see its full text. Multiple titles at the
same round remain separate labels; timestamp and order axes keep their original
labels. Abbreviations shorten display text only and do not infer optimization names.
