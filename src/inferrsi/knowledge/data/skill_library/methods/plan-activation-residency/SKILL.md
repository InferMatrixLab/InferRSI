---
name: plan-activation-residency
description: Propose training activation and gradient memory reductions by distinguishing lifetime reordering, address packing and selective rematerialization from supplied evidence.
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
