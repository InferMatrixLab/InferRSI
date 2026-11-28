---
name: omni-architecture
description: "Map vLLM-Omni stage ownership and derive constrained architecture or execution search spaces."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Architecture and search

Use for source understanding or AI-generated engine design. Read [architecture and search dimensions](references/architecture.md), then the [evidence map](../../references/evidence.md).

Trace one concrete request through its chosen pipeline before generalizing. Record each stage's input/output contract, state owner, schedule unit, device, communication and terminal condition. Classify each candidate as an existing setting, implementation change or research extension.

Produce a dependency-constrained search table with legal domains, feasibility checks, quality constraints and measurements. Hold workload and model semantics fixed for execution experiments. Lower resolution, fewer denoise steps, quantization and approximate caches require their own quality budget.

If a field or capability is absent from this snapshot, mark it as a proposed extension. If two documents disagree, inspect their pinned implementation and tests; report residual uncertainty. Route runnable deployment questions to [serving](../omni-serving/SKILL.md) and proposed code changes to [validation](../omni-validation/SKILL.md).
