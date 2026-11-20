---
name: plan-activation-residency
description: Propose training activation and gradient memory reductions by distinguishing lifetime reordering, address packing and selective rematerialization from supplied evidence.
metadata:
  inferrsi: |
    {
      "status": "candidate",
      "empirical_validation": "not_run",
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "applicability": {
        "scope": "Proposing training activation and gradient memory reductions when pressure appears to come from live tensors or allocator-reserved memory, by distinguishing lifetime reordering, address packing and selective rematerialization; covers activation checkpointing for recomputation, not persistent recovery checkpoints",
        "prerequisites": "The packaged evidence and limits are read before citing paper results; installing or running a solver or framework, modifying allocation or checkpoint policies, reproducing workloads or provisioning hardware needs separate authorization",
        "input_contract": "The actual forward/backward/update DAG, shapes and precision, tensor sizes and consumer lifetimes; resident versus reserved peak bytes; operator, workspace and temporary-output peaks; batch and accumulation policy; optimizer and collective barriers; representative compute and transfer costs; whether the goal is fit, step time or time to a fixed training objective",
        "produced_artifact": "A preferred candidate, simpler fallback, resource ledger, critical-path prediction, assumptions, counter-signals and unresolved-evidence list, with source claims kept apart from proposed decisions, plus a proposed matched comparison; a reviewable proposal, not an implementation",
        "failure_modes": [
          "Fragmentation and live-byte excess are not distinguished at the same phase",
          "OLLA address packing is read as tensor placement across CPU/SSD tiers",
          "Reordering moves a release or update past a dependency such as shared weights, accumulation, gradient clipping, optimizer state or collectives",
          "A static packing plan ignores alignment, aliasing, workspace, asynchronous overlap or shape variability",
          "Added recomputation consumes the compute window that previously hid transfers",
          "Checkmate's rounding is taken to guarantee the memory cap, or its 10% allowance is used as a portable safety margin",
          "A solver timeout is read as proof of infeasibility"
        ],
        "refusal_point": "Returns the missing classification instead of a preferred checkpoint interval when only total OOM memory is known, and escalates when a legal dependency graph, memory margin or correctness model is unavailable"
      },
      "recommendations": [
        "Where ordering is legal, try earlier last-use and gradient release before adding computation or transfer.",
        "Check dependency validity and memory feasibility separately for an approximate schedule.",
        "Account for planning cost over the expected number of repeated steps."
      ],
      "limitations": [
        "Source-derived candidate; no local efficacy validation.",
        "Original typed source inventory is not normalized; retain source identities and limits in the procedure/readsets."
      ],
      "provenance_readsets": [
        "references/source-notes.md"
      ],
      "consumption_mode": "packaged"
    }
---

# Plan activation residency

Use when training memory pressure appears to come from live tensors or allocator-reserved memory. This is an unvalidated paper-derived planning procedure, not an implementation recipe. It covers activation checkpointing for recomputation, not persistent recovery checkpoints. Read [evidence and limits](references/source-notes.md) before citing paper results.

## Evidence needed

Use the actual forward/backward/update DAG, shapes/precision, tensor sizes and consumer lifetimes; resident versus reserved peak bytes; operator/workspace and temporary-output peaks; batch/accumulation policy; optimizer/collective barriers; and representative compute/transfer costs. Record whether the goal is fit, step time, or time to a fixed training objective. If only total OOM memory is known, return the missing classification rather than a preferred checkpoint interval.

## Decision procedure

- Distinguish live-byte excess from fragmentation at the same phase. OLLA's location optimization packs addresses in one memory space; it is not tensor placement across CPU/SSD tiers.
- When legal ordering flexibility exists, propose earlier last-use/gradient release before adding computation or transfer. Preserve all dependencies, including shared weights, accumulation, gradient clipping, optimizer state and collectives. An update may be moved only if the complete graph permits it.
- For stable lifetimes with large reserved-minus-live overhead, consider an address-packing candidate. Include alignment, aliasing, workspace, asynchronous overlap and shape variability; a static plan is infeasible if these cannot be represented.
- If retained activations still dominate, compare selective retention/recomputation with any already-supported offload candidate. Use hardware- and shape-specific costs; include simultaneous dependency/output residency. More recomputation can relieve capacity but consume the compute window previously hiding transfers.
- For a proposed approximate schedule, check dependency validity and memory feasibility separately. Checkmate's rounding repairs dependencies but does not guarantee the memory cap; its 10% allowance is not a portable safety margin.
- Return a preferred candidate, simpler fallback, resource ledger, critical-path prediction, assumptions, counter-signals and an explicit unresolved-evidence list. Keep source F claims separate from P decisions.

## Verification proposal and stopping point

Propose, but do not execute in paper-only mode, a matched comparison holding model, precision, global batch and numerical semantics fixed. Desired evidence: actual peak live/reserved/workspace bytes, whole-step latency, extra evaluations/transfers, and correctness for stateful/random operators. Record solver status, feasible incumbent and bound separately; timeout does not prove infeasibility. Account for planning cost over the expected number of repeated steps.

Stop at the reviewable proposal. Do not install/run a solver or framework, modify allocation or checkpoint policies, reproduce workloads, or provision hardware without separate authorization. Escalate when a legal dependency graph, memory margin or correctness model is unavailable. Historical GPU results establish no current engine or NPU compatibility.
