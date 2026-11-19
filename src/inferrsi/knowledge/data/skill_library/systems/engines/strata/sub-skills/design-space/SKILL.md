---
name: design-space
description: "Analyze Strata's inference architecture and define constrained search spaces for AI-generated inference engines, separating supported settings, replaceable algorithms, and new capabilities."
license: MIT
metadata:
  disco-role: operating
---

# Strata design space

Use this leaf when the task is to explain Strata, design a similar inference engine, or decide what an AI optimization loop may change. Read [the design-space reference](references/design-space.md) for the architecture, evidence, and parameter dependencies.

1. Fix the model family and numerical contract, hardware topology, workload distribution, and objective before proposing candidates. Model dimensions are kernel contracts, not ordinary tuning parameters.
2. Label each candidate **existing setting**, **algorithm replacement**, or **new capability**. Keep exact implementation changes separate from approximations that change logits or output distributions.
3. Specify dependencies and rejection conditions with each candidate. Account jointly for weights, expert residency, KV/state, MTP, prompt workspace, batch slots, and memory reserve.
4. Return a decision table with the candidate, expected bottleneck, applicable conditions, correctness gate, performance metric, and supporting code evidence. Report evidence gaps explicitly.

For an existing installation's parameter sweep, continue with [tune-execution](../tune-execution/SKILL.md). For implementation validation or a correctness dispute, continue with [validate-engine](../validate-engine/SKILL.md).

This is a portable profile: it does not assume a local checkout, install software, download weights, or run benchmarks. Verify code differences against the requested revision before applying its recorded facts. Automatic skill discovery remains enabled.
