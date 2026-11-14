---
name: tune-execution
description: "Design and interpret controlled Strata tuning experiments for a specified model, hardware and workload, including expert residency, CPU/PCIe balance, prefill, KV, speculation and concurrency."
license: MIT
metadata:
  disco-role: operating
---

# Tune execution

Read the [tuning procedure](references/tuning.md). Start with an existing working configuration and preserve its model paths and required options. Record resolved settings from startup logs; requested flags alone do not establish which path ran.

If hardware, workload or acceptable quality loss is missing, give a conditional experiment plan. Select one bottleneck and a small, meaningful candidate set. Use [design-space](../design-space/SKILL.md) for architectural changes; require [validate-engine](../validate-engine/SKILL.md) before accepting a candidate.

Deliver the baseline, candidate differences, feasibility conditions, correctness gates, raw-result locations, repeated measurements and decision. Report failures and regressions. Never transplant a documented speedup to different hardware or rank a numerically invalid candidate.
