---
name: claim-contract
description: Enforce ThinkFlowLab claim contract wording and verdict rules without embedding campaign-specific revision pins.
---

# Claim contract (portable)

## Public claim wording

Use: “on {repo}@{candidate} vs baseline@{baseline}, under {RunSpec}, we observed …”

Only after acceptance **`PASS`** with artifacts under `evidence/`.

## Rules (not numbers)

| Verdict | When |
| --- | --- |
| PASS | Pinned SHAs, artifact tree on candidate tip, gates satisfied |
| FAIL | Gates failed with complete evidence |
| INCONCLUSIVE | Cannot defend comparison (env, partial run, missing validator freeze) |

## What not to do

- Do not bake baseline/candidate SHAs into shared repo templates, skills, or default CI env.
- Do not treat microbench alone as e2e campaign completion.
- Do not auto-transfer lessons across unverified repo × revision × backend × device × model × scenario tuples.

## SIAS

Respect plane boundaries: `harness/` orchestrates, `model/` defines quality, `infra/` supplies execution. Cross-plane deps belong in RunSpec.
