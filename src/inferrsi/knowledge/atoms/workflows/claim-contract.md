---
name: claim-contract
description: Enforce ThinkFlowLab claim contract wording and verdict rules without embedding campaign-specific revision pins.
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "profile": "local-skill-v1",
      "kind": "skill",
      "status": "candidate",
      "origin": [
        "first-party"
      ],
      "consumption_mode": "packaged",
      "tags": [
        "claim",
        "wording",
        "verdict",
        "evidence",
        "portable"
      ],
      "empirical_validation": "not_run",
      "applicability": {
        "scope": "Wording and verdict rules for any public performance or quality claim produced from an RSI campaign",
        "prerequisites": "A completed campaign with pinned baseline and candidate SHAs and an evidence tree; the rules themselves carry no numeric threshold",
        "input_contract": "A claim draft, the campaign RunSpec and its evidence tree under evidence/<campaign-id>/",
        "produced_artifact": "A claim sentence in the pinned form, or a refusal when the campaign verdict is not PASS",
        "failure_modes": [
          "Claim asserted before the campaign reaches PASS with artifacts",
          "Baseline or candidate SHA written into a shared template, skill or default CI environment",
          "Microbenchmark result presented as end-to-end completion",
          "A lesson transferred across an unverified repo x revision x backend x device x model x scenario tuple"
        ],
        "refusal_point": "Refuses any public claim lacking a PASS verdict and artifacts under evidence/, and refuses numeric thresholds because thresholds belong to the campaign"
      },
      "recommendations": [
        "Keep campaign SHAs in the acceptance issue; a shared template that carries them will be wrong for the next campaign.",
        "Write the verdict from the evidence tree before writing the claim sentence.",
        "Treat each repo x revision x backend x device x model x scenario tuple as an independent claim."
      ],
      "limitations": [
        "States wording and verdict rules only; it selects no numeric gate and validates no measurement.",
        "SIAS plane boundaries constrain where a change belongs, not whether it is correct."
      ],
      "provenance_readsets": []
    }
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
