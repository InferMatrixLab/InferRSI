---
name: choose-parallel-training-plan
description: Compare stage, device-mesh and operator-sharding candidates for static distributed training while accounting for memory, topology, resharding and planning cost.
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
        "scope": "Comparing stage, device-mesh and operator-sharding candidates for static distributed training when heterogeneous stage memory or work, or communication cost, makes a uniform data/tensor/pipeline plan suspect; derived from historical Alpa, not a current compiler configuration guide",
        "prerequisites": "The packaged source notes are read; the skill authorizes no compiler or solver install or run, parallelism reconfiguration, repository edit, hardware task or benchmark",
        "input_contract": "Model operator graph and shapes; global batch, microbatch and accumulation; precision and optimizer; physical links and contention; candidate shard layouts; stage latency, workspace and in-flight activation memory; the objective and expected run length. A device count without topology is insufficient",
        "produced_artifact": "The best supported candidate and a simpler fallback with a memory and critical-path ledger, planning cost and amortization, semantic invariants, counter-signals, missing evidence and a proposed matched comparison; a plan, not a reconfiguration",
        "failure_modes": [
          "Equal arithmetic work is taken to mean equal kernel time, carrying over Alpa's zero compute-cost simplification",
          "Mean memory replaces the largest per-rank peak with multiple in-flight activation sets",
          "Inter-stage transfer and microbatch count stay outside the objective, as in historical Alpa, without the gap being reported",
          "Repeated slow-link sends to replicated destination tiles are not compared with one cross-mesh transfer plus local allgather",
          "Inter-node Network traffic is merged with intra-node accelerator links",
          "Static cost estimates are applied to dynamic shapes, asymmetric devices or changing communication contention"
        ],
        "refusal_point": "Rejects infeasible stage/mesh pairs, claims no global optimality outside the declared search space, and stops at the plan in paper-only mode"
      },
      "recommendations": [
        "Keep a simple reference plan with the same training semantics and global batch as the comparison point.",
        "Separate fixed-model scaling from model-size weak scaling before quoting a speedup; Alpa's 9.7x MoE ratio belongs to a specific weak-scaling workload, baseline and 25-Gbps cluster.",
        "Weigh planning cost against the expected run length; a shorter job may not amortize it."
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

# Choose a parallel training plan

Use when heterogeneous stage memory/work or communication cost makes a uniform data/tensor/pipeline plan suspect. This candidate is derived from historical Alpa, not a current compiler configuration guide. Read [source notes](references/source-notes.md).

## Evidence and decision

Require model/operator graph and shapes; global batch, microbatch and accumulation; precision/optimizer; physical links and contention; candidate shard layouts; stage latency, workspace and in-flight activation memory; and the objective/expected run length. A device count without topology is insufficient.

1. Preserve a simple reference plan and the same training semantics/global batch. Distinguish fixed-model scaling from model-size weak scaling.
2. Compare sharding at the operator level, including input/output layout conversions. Equal arithmetic work does not imply equal kernel time; Alpa's zero compute-cost simplification is not a measured fact for this workload.
3. Consider uneven stage boundaries and mesh sizes where activation/weight intensity changes. Include multiple in-flight activation sets and the largest per-rank peak, not just mean memory. Reject infeasible stage/mesh pairs.
4. Evaluate first-microbatch cost and repeated bottleneck-stage time with actual cross-stage transfers and overlap limits. Historical Alpa omits inter-stage transfer from its optimization and takes microbatch count externally; report these gaps rather than treating its objective as complete.
5. Where destinations replicate tiles, compare repeated slow-link sends with one necessary cross-mesh transfer plus local allgather. Count local collective/staging cost and correctness of destination shards. Separate inter-node Network traffic from intra-node accelerator links.
6. Return the best supported candidate and a simpler fallback, memory/critical-path ledger, planning cost/amortization, semantic invariants, counter-signals and missing evidence. Do not claim global optimality outside the declared search space.

## Limits and future verification

A homogeneous model may already favor equal stages; a shorter job may not amortize planning; dynamic shapes, asymmetric devices or changing communication contention may invalidate static cost estimates. Historical Alpa's reported 9.7× MoE ratio reflects a specific weak-scaling workload and baseline without inter-op parallelism on a 25-Gbps cluster.

Propose a later authorized comparison with matched model/global batch/precision and topology. Check numerical correctness, full-step time, per-rank memory and exposed resharding/collective time. Stop at the plan in paper-only mode; no compiler/solver install or run, parallelism reconfiguration, repository edit, hardware task or benchmark is authorized by this skill. Current engine/NPU support requires separate evidence.
