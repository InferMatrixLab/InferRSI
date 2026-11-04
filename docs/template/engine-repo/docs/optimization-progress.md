# End-to-end optimization progress

Keep an optimization-progress figure in the root README alongside the
[architecture](architecture.md). Show how the **same engine workload** changes
over development time, with phase bands and a named milestone for each measured
configuration. This complements the final baseline comparison table; it does
not replace quality results, failed trials or acceptance evidence.

![Illustrative end-to-end throughput progress; synthetic values only](figures/end-to-end-optimization.svg)

## Included illustration and redraw command

The [example CSV](figures/optimization-progress.example.csv) is entirely
synthetic. Its values, days and phase names are layout examples, not MiniCPM or
Z.ai results, expected speedups, targets or a development schedule. All example
rows are `INCONCLUSIVE` and have no evidence. The layout follows the phase and
milestone presentation in
[Z.ai's article](https://z.ai/blog/glm-built-its-inference-infrastructure).

From the **engine repository root**, redraw the included illustration:

```bash
python -m pip install matplotlib
python tools/plot_optimization_progress.py \
  docs/figures/optimization-progress.example.csv \
  --output docs/figures/end-to-end-optimization.svg \
  --title "Engine end-to-end throughput optimization" \
  --unit "items/s" --illustrative
```

Python and Matplotlib are documentation-authoring tools only. They are not
engine dependencies or default accelerator CI steps. The script also accepts a
PNG output path. Commit the source CSV and SVG together; record the Python and
Matplotlib versions used when publishing a measured chart.

## Replace with measured data

1. Freeze a comparison scope in the acceptance issue and campaign `plan/`:
   model/weights, exact hardware/count, precision, input set, concurrency,
   request/output lengths, timing boundary, warmups, repetitions, aggregation
   and required quality/E2E gates. Link it in the README's chart caption. Keep
   separate charts for incomparable scopes; do not connect their points.
2. Create a campaign-owned CSV in `evidence/<campaign-id>/results/`. The first
   row is the measured baseline and must be at day zero. Subsequent rows are
   cumulative engine configurations at their actual elapsed development days,
   in strictly increasing order. Fractional days are allowed. Use one phase per
   contiguous group of milestones; phase bands are visual groupings, not timing
   evidence. Keep every comparable measured milestone, including regressions
   and flat results. Record unmeasured/aborted attempts in the ledger below;
   never substitute zero, interpolate a missing value or extrapolate a forecast.
3. Use the columns below. Each non-illustrative row needs its original evidence
   location and `PASS`, `FAIL` or `INCONCLUSIVE` verdict. The script checks the
   presence of those fields, not the truth or completeness of the evidence.
   Review the evidence before publication. The CSV is a plotting input, not a
   new evidence format or a replacement for frozen campaign artifacts.
4. Run the same command with the measured CSV and **without** `--illustrative`.
   Replace the title and unit with the engine's actual scope. Update the README
   alt text/caption, results table and ledger together. State the current verdict
   and missing gates beside the figure. Public qualified gain claims still
   require complete evidence and `PASS`; reported failed/incomplete measurements
   retain their labels. The plot's markers distinguish these verdicts.

| CSV column | Meaning |
| --- | --- |
| `day` | Finite elapsed development days from the first baseline, starting at 0 |
| `phase` | Contiguous development phase, e.g. bring-up, scheduling, kernels, validation |
| `optimization` | Short name of the actual cumulative change or baseline |
| `throughput` | Positive finite E2E throughput in one declared unit, same statistic at every point |
| `verdict` | Original campaign/milestone verdict; no inferred promotion from a speedup |
| `evidence` | Public evidence URL or repository-relative result path, with full provenance in the ledger |

The plotted ratio is `throughput_at_milestone / throughput_at_first_row`.
It is **not** the product of isolated kernel gains, nor the ratio to the previous
point. A faster configuration may still fail quality or an acceptance gate.
Use measured throughput only; latency, TTFT/TTFA and memory need separate plots
with their own units/direction. Keep run variability, intervals and aggregation
details in the linked results; a point estimate does not establish significance.

## Comparison scope and evidence ledger

Fill this record before publishing a measured chart. Campaign pins and numeric
gates stay in the acceptance issue/evidence; link those records here.

```text
Acceptance issue / frozen comparison scope: <issue-and-plan-links>
Baseline identity / measurement: <baseline-evidence-link>
Hardware / model / precision / workload / concurrency: <exact-scope>
E2E timing boundary / throughput unit / statistic: <measurement-definition>
Warmups / repetitions / uncertainty: <protocol-and-results-link>
Current verdict / quality gates / remaining gaps: <verdict-and-evidence>
Plot source / redraw command / authoring versions: <reproducible-record>
```

| Day / phase | Cumulative change and revision evidence | E2E throughput / gain | Quality / verdict | Raw runs, commands and decision |
| --- | --- | --- | --- | --- |
| `<elapsed-day-and-phase>` | `<change-and-revision-record>` | `<measured-value-and-ratio-or-not-measured>` | `<quality-result-and-verdict>` | `<evidence-and-kept-rejected-or-unmeasured-reason>` |

Each plotted point must resolve to its own baseline/candidate identity,
configuration, repeated raw measurements, quality results and verdict rationale
in the four [evidence segments](../evidence/README.md). Preserve the original
verdict of rejected or incomplete trials. Updating the figure never authorizes
rewriting historical measurements or frozen validators.
