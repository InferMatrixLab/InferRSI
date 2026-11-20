---
name: cite-check-downstream-pr
description: Review a downstream PR description for correct acceptance issue links, SHA pins, and artifact citations.
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
        "review",
        "downstream",
        "citation",
        "evidence",
        "verdict"
      ],
      "empirical_validation": "not_run",
      "applicability": {
        "scope": "Review of a downstream PR description that cites RSI acceptance work for a performance or quality improvement",
        "prerequisites": "The PR description, the acceptance issue it cites, and the evidence paths it names; reviewing is read-only and needs no local run",
        "input_contract": "One PR description plus the cited acceptance issue and its evidence tree; the reviewer reads claims and citations, not the candidate code",
        "produced_artifact": "A per-checklist review result that either accepts the citation or marks the summary unverified, using only PASS/FAIL/INCONCLUSIVE vocabulary",
        "failure_modes": [
          "No acceptance issue URL, only a chat thread",
          "Branch names instead of full baseline and candidate SHAs",
          "Microbenchmark evidence offered for an end-to-end latency claim",
          "A threshold restated or invented relative to the acceptance issue",
          "Evidence path absent, stale or on a different SHA than the cited candidate"
        ],
        "refusal_point": "Refuses to restate a performance or quality claim whose artifacts are missing, stale or off-SHA; reports the summary as unverified instead"
      },
      "recommendations": [
        "Read the cited acceptance issue before the PR description so an invented threshold is visible immediately.",
        "Resolve every listed evidence path and compare its SHA with the candidate SHA the PR names.",
        "Report an unverifiable claim as unverified rather than repeating its number."
      ],
      "limitations": [
        "Checklist-only procedure; it validates citation discipline, not the measurement behind an artifact.",
        "A passing review does not establish that the campaign evidence itself is correct."
      ],
      "provenance_readsets": [],
      "searchspace_not_applicable": "SKILL.md §§ Checklist and Red flags check acceptance links, revision/artifact citations and claim wording; they provide no hardware-resource mechanism."
    }
---

# Cite-check a downstream PR

Use when reviewing external PRs that claim performance or quality improvements tied to RSI acceptance work.

## Checklist

- [ ] Links an acceptance issue URL (not only a chat thread)  
- [ ] States **baseline SHA** and **candidate SHA** matching that issue  
- [ ] Points to `evidence/<campaign-id>/results/` (or equivalent published mirror)  
- [ ] Does **not** invent new thresholds or restate bars differently  
- [ ] Marks summaries **unverified** if artifacts are missing, stale, or off-SHA  
- [ ] Uses verdict vocabulary only: `PASS` / `FAIL` / `INCONCLUSIVE`  

## Red flags

- “X% faster” without artifact path  
- Branch names instead of full SHAs  
- Microbench-only support for e2e latency claims  

## Reference

[docs/contributing.md#evidence-and-claims](https://github.com/InferMatrixLab/InferRSI/blob/b2f60f913a949f9073686a23476f752e11d709a4/docs/contributing.md#evidence-and-claims)
