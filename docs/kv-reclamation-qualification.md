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

## What was kept

The retained evidence stays in place and unmodified:

- [`evidence/kv-reclamation-20261030/`](../evidence/kv-reclamation-20261030/README.md)
- `evidence/kv-actor-qualification-20261030/`
- `evidence/kv-actor-qualification-20261031/`
- `evidence/kv-live-pilot-20261031/`

Their entries in `tools/evidence_inventory.json` are unchanged, so
`python -m tools.validate_evidence` still verifies them.

## What the evidence does and does not show

The qualification receipts record **software and scripted-control execution**
only. Both live A2/A3 attempts on 2026-10-31 ended `INCONCLUSIVE`, the second
stopping at its first transport call on HTTP 403, so no completed arm, per-arm
outcome or A/A variance exists. The recorded dollar figures are reserved upper
bounds, not observed spend. Nothing here is a model-effect, knowledge-effect or
hardware result.

The general SkillEval capability is unaffected: nothing in
`src/inferrsi/harness/skill_eval*.py`, the runner, the evaluator or
`tools/skill_eval_*.py` referenced the removed modules. The dependency ran one
way only, from this slice onto those shared parts.
