## When to use this skill

Use this skill before modifying an inference serving system when you need to
answer: *does meaningful headroom exist, where is it, and is a requested
speedup such as 2× plausible?*

When preparing a task, preserve user-provided acceptance criteria. If none were
supplied, follow [acceptance-criteria preparation](references/acceptance-criteria.md)
to derive and freeze targets from this analysis. Preserve partial requirements,
label derived fields and retain evidence gaps; a theoretical ceiling alone does
not establish an attainable target or a quality tolerance.

Do not use it to benchmark or compare two already-built candidates — that is
the job of InferRSI's AB/BA harness and `rsi-evidence` skill.

For whole-model prefill and decode composition, use [model-sol-analysis](../model-sol-analysis/SKILL.md).

