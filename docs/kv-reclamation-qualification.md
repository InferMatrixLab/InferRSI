# Synthetic CPU KV-block reclamation qualification (retired)

The tooling this page documented has been removed. It described a bounded,
model-free mechanism-transfer task built for the task-efficacy pilot in
[issue 248](https://github.com/InferMatrixLab/InferRSI/issues/248): a synthetic
CPU reclamation contract with an independently authored frozen oracle, an
isolated input-only replay and trusted event-by-event comparison through the
existing AB/BA runner.

This page is kept because the retained evidence links to it, and that evidence
is hash-pinned and must not be edited.

## What was removed

`tools/qualify_kv_reclamation.py`, `tools/qualify_kv_edit_actor.py`,
`tools/qualify_kv_actor_cleanup.py`, the `tools/kv_*` live-launcher and
admission modules, `src/inferrsi/harness/kv_reclamation.py`,
`src/inferrsi/harness/kv_edit_workbench.py`, their tests and task fixtures,
the `kv-edit-pilot` workflow and the `kv-task-qualification` job in the ready
lane. None of the commands named on this page can be run from the repository
any more.

Every path named above still exists at
[`e843b9d3`](https://github.com/InferMatrixLab/InferRSI/commit/e843b9d31cb86e1fd12d00890c89798b0bedd1fe),
the last revision this branch shared with `main` before the removal, which
remains an ancestor of `main`. Read any of them from history:

```
git show e843b9d3:tools/qualify_kv_reclamation.py
git show e843b9d3:tests/fixtures/kv_reclamation/candidate.py
```

## What was kept

The retained evidence stays in place and unmodified:

- [`evidence/kv-reclamation-20261030/`](../evidence/kv-reclamation-20261030/README.md)
- `evidence/kv-actor-qualification-20261030/`
- `evidence/kv-actor-qualification-20261031/`
- `evidence/kv-live-pilot-20261031/`

Their entries in `tools/evidence_inventory.json` are unchanged, so
`python -m tools.validate_evidence` still verifies them.

Because that evidence is hash-pinned, it still names paths and modules that the
removal deleted. Eleven files do so:

| Bundle | Files | Reference |
| --- | --- | --- |
| `kv-live-pilot-20261031` | `patch/README.md` | `tests/fixtures/kv_reclamation/candidate.py` |
| `kv-live-pilot-20261031` | `plan/plan.json`, `plan/A2.json`, `plan/A3.json`, `plan/second-attempt/{plan,A2,A3}.json`, `plan/second-attempt-1200/plan.json` | `tools.qualify_kv_reclamation`, `tools.kv_live_job` |
| `kv-actor-qualification-20261030` | `results/hosted-41154288295/qualification.json`, `results/hosted-41182807900/qualification.json` | `kv_edit_workbench` |
| `kv-reclamation-20261030` | `patch/README.md` | `tests/fixtures/kv_reclamation/candidate.py` |

Each of those references resolves at `e843b9d3` through the command above. None
resolves in the working tree, which is the expected result of the removal rather
than a broken bundle.

## What the evidence does and does not show

The qualification receipts record **software and scripted-control execution**
only.

| Claim | Where to check it |
| --- | --- |
| No completed arm, per-arm outcome or A/A variance exists | [`evidence/kv-live-pilot-20261031/results/README.md`](../evidence/kv-live-pilot-20261031/results/README.md): "Prospective pair: not executed … No paid model output, timing result or efficacy verdict exists in this bundle" |
| The dollar figures are reserved upper bounds, not observed spend | `evidence/kv-live-pilot-20261031/plan/second-attempt-budget.json`: `worst_case` 162,720,000 microUSD against the PR and pilot lifetime caps |
| Both authorized attempts on 2026-10-31 ended `INCONCLUSIVE`, the second stopping at its first transport call on HTTP 403 with A3 never started | Runs [41159550621](https://github.com/InferMatrixLab/InferRSI/actions/runs/41159550621) and [41194057284](https://github.com/InferMatrixLab/InferRSI/actions/runs/41194057284), assessed in [issue 248](https://github.com/InferMatrixLab/InferRSI/issues/248#issuecomment-6648189616) |

The third row is not recorded inside the retained bundles: they hold the frozen
inputs and the not-executed marker, while the attempt outcomes live in the run
records. A workflow conclusion of `success` on those runs means orchestration
and evidence retention finished, not that a request was delivered or charged.

Nothing here is a model-effect, knowledge-effect or hardware result.

The general SkillEval capability is unaffected: nothing in
`src/inferrsi/harness/skill_eval*.py`, the runner, the evaluator or
`tools/skill_eval_*.py` referenced the removed modules. The dependency ran one
way only, from this slice onto those shared parts.
