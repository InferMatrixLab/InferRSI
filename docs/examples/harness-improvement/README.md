# Recorded offline controller example

These are fixed-output software controls for
[issue #93](https://github.com/InferMatrixLab/InferRSI/issues/93), generated with
the adjacent implementation and `tests.fixtures.skill_eval_improvement_demo`.
Python 3.12.3 and Git 2.47.3 were used on Linux. No real model was invoked.
Full raw trial artifacts are produced locally by the reproduction command;
these public JSON files retain the aggregate report without private paths.

| Control | Actual subprocess calls | Scripted total tokens | Scripted held-out candidate checks | Regressions |
| --- | ---: | ---: | ---: | ---: |
| Paired H0/H0 | 12 | 1,440 | 6/6 | 0 |
| Repeated H0, same call budget as the loop | 48 | 5,760 | 24/24 | 0 |
| Bounded INV/DOM → rerun → holdout | 48 | 4,200 | 6/6 | 0 |

The cheaper DOM fixture costs 240 scripted tokens over six development trials
but has three regressions; the controller rejects it. INV costs 360 versus its
paired H0's 720, passes the mandatory rerun and then the held-out checks. The
full loop records 4,200, not just the selected candidate's 360. These values
are deliberately programmed inputs to test quality-first selection and complete
accounting. **They do not show a measured percentage saving or success-rate
improvement for InferRSI.** The repeated-H0 control matches call count, not billed
cost or a hard token budget, and has no best-of-N answer selection.

The [summary](offline-summary.json) separates preparation and local pipeline
wall time. A single local timing observation is not a speedup benchmark; these
fixtures were also run alongside repository tests. The
[bounded report](bounded-report.json) retains phase costs, selection reasons,
rerun/holdout assessments and unknown proposal/monetary cost. Cached-input tokens
are recorded separately and are not added to total tokens twice.

Reproduce from the repository checkout with development dependencies:

```bash
python -m tests.fixtures.skill_eval_improvement_demo --output <new-output-dir>
```

The generated JSON includes retained-plan/report digests for that invocation.
Temporary Git commit identities, file digests and wall times can differ between
runs. The scripted call/token/outcome values above are reproducible. Model
efficacy, complete authoring-plus-execution cost and engine benefits remain
`INCONCLUSIVE`; this example is not a campaign `PASS`.
