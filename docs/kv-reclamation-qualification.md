# Synthetic CPU KV-block reclamation qualification (retired)

The synthetic CPU mechanism-transfer tooling for
[Issue #248](https://github.com/InferMatrixLab/InferRSI/issues/248) was removed.
This page is the reference linked by the frozen evidence.

## What was removed

The qualification scripts, live launchers, Harness KV workbench, workflow and
task fixtures can be inspected at
[`v0.1.4`](https://github.com/InferMatrixLab/InferRSI/releases/tag/v0.1.4).

```bash
git show v0.1.4:tools/qualify_kv_reclamation.py
git show v0.1.4:tests/fixtures/kv_reclamation/candidate.py
```

## What was kept

- [CPU contract and replay qualification](../evidence/kv-reclamation-20261030/README.md)
- [October 30 actor qualification](../evidence/kv-actor-qualification-20261030/README.md)
- [October 31 actor qualification](../evidence/kv-actor-qualification-20261031/README.md)
- [Live pilot inputs and results record](../evidence/kv-live-pilot-20261031/results/README.md)

The bundles retain eleven references to removed paths. Resolve those paths at
`v0.1.4`. To verify the retained hashes, run `python -m tools.validate_evidence`.

## What the evidence does and does not show

The qualification receipts cover software and scripted controls. The frozen
live pilot records inputs and an unexecuted pair. It contains no completed arm,
per-arm outcome, A/A variance or efficacy verdict. The
[budget record](../evidence/kv-live-pilot-20261031/plan/second-attempt-budget.json)
records reserved upper bounds and contains no observed spend.

Both authorized live attempts on 2026-10-31 ended `INCONCLUSIVE`. The second
stopped at the first transport call (A0, HTTP 403), before A3. The run records
report orchestration and evidence retention. See
[run 41159550621](https://github.com/InferMatrixLab/InferRSI/actions/runs/41159550621),
[run 41194057284](https://github.com/InferMatrixLab/InferRSI/actions/runs/41194057284)
and the [issue disposition](https://github.com/InferMatrixLab/InferRSI/issues/248#issuecomment-6648189616).
