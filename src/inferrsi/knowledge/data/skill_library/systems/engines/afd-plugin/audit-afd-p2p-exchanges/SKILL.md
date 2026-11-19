---
name: audit-afd-p2p-exchanges
description: Audit CUDA P2pNccl Attention/FFN rank namespaces and per-stage, per-peer hidden-state ownership when uneven worker counts or a mismatched return slice make an AFD exchange ambiguous.
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "Apache-2.0",
      "tags": [
        "afd-plugin",
        "cuda",
        "p2p",
        "rank-mapping",
        "hidden-states",
        "ownership"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/vllm-project/afd-plugin",
          "commit": "df8d6a0c403c3ca1b4ed9cf1687e7204908bebec",
          "paths": [
            "README.md",
            "LICENSE",
            "afd_plugin/config.py",
            "afd_plugin/distributed/topology.py",
            "afd_plugin/connectors/factory.py",
            "afd_plugin/connectors/metadata.py",
            "afd_plugin/connectors/gpu/p2p.py",
            "afd_plugin/v1/worker/attention_metadata.py",
            "afd_plugin/v1/worker/attention_model_runner_v2.py",
            "afd_plugin/v1/worker/ffn_worker.py",
            "afd_plugin/v1/worker/ffn_model_runner.py",
            "afd_plugin/model_executor/models/deepseek_v2.py",
            "afd_plugin/model_executor/models/forward_context.py",
            "tests/unit/distributed/test_topology_partition.py"
          ],
          "readset": "references/source-notes.md"
        }
      ],
      "applicability": {
        "scope": "Source-based CUDA P2pNccl rank/payload audit; selected eager dense-FFN path with compute_gate_on_attention=false. Repository identity afd_plugin; runtime/backend compatibility unverified.",
        "prerequisites": "Access to the pinned source ledger and caller-level evidence for the selected eager dense FFN path with Attention-side gating disabled; any proposed cross-stream reuse needs an established communicator completion contract.",
        "input_contract": "Plugin and dependency revisions, connector and role, A/F worker counts, DP/PCP/TP coordinates, worker/device ranks, subgroup roster, stage, per-peer token counts, payload shape/dtype/device, transfer context and returned slices.",
        "produced_artifact": "A bounded rank-namespace and per-peer payload ownership ledger, the earliest evidenced mismatch or missing edge, and a proposed verification plan.",
        "failure_modes": "Inferring data peers from control senders, accepting equal total row counts despite a peer permutation, or treating an even-split fallback or Python return as proof of ownership/completion can produce a wrong exchange diagnosis.",
        "refusal_point": "Stop on A < F, invalid role ranks, duplicate/missing assignments or an unresolved rank namespace; return the conflicting callers and ledger entries without inventing ranks or attributing the fault to networking."
      },
      "limitations": [
        "Source-derived candidate; native exchange, model quality, backend compatibility, performance and agent efficacy not_run.",
        "Selected Python readset is Apache-2.0; the retained MIT notice concerns excluded NPU async CAM implementation and adapted bindings.",
        "No qualification of graph/DBO, remote-expert MoE, multi-host transport, complete token-count projection or underlying communicator completion semantics."
      ],
      "provenance_readsets": [
        "references/source-notes.md"
      ],
      "references": [
        "../../vllm/audit-vllm-kv-lifetimes/SKILL.md",
        "../../../../playbooks/measurement/inference-benchmark-design/SKILL.md",
        "../../../../playbooks/measurement/dense-performance-evidence/SKILL.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Record role, world and subgroup-local ranks separately; reconstruct the actual subgroup roster before interpreting send/receive peers.",
        "Track distinct row identities and stage-specific peer lengths through concatenation and splitting; use same-total swapped lengths as a countercheck.",
        "Establish the last communicator/stream completion obligation before reusing or releasing a receive buffer."
      ]
    }
---

# Audit AFD P2P exchanges

Use this source-derived candidate to reconstruct a CUDA P2pNccl exchange before
changing ranks, blaming a transport or reusing a receive buffer. Its selected
payload path is **eager dense FFN with Attention-side gating disabled**
(`compute_gate_on_attention=false`), where the Attention layer selects
`RemoteFFNProxy`. The rank mapping is shared connector code; the payload
procedure does not qualify CUDA remote-expert MoE, DBO, NPU CAM, graph replay or
another plugin/dependency revision.

Source pin: `vllm-project/afd-plugin`
`df8d6a0c403c3ca1b4ed9cf1687e7204908bebec`.
Read the [source ledger and call chain](references/source-notes.md) before using
the two rules. **F1–F4** below are bounded source observations; the procedure is
**proposed**, status **candidate**, empirical validation **not_run**.

## Select the actual owner

This owner concerns Attention/FFN hidden-state exchanges, not KV-block release.
Use [vLLM KV lifetimes](../../vllm/audit-vllm-kv-lifetimes/SKILL.md) for
scheduler/connector KV retention at its separate pin. Use
[benchmark design](../../../../playbooks/measurement/inference-benchmark-design/SKILL.md) and
[evidence classification](../../../../playbooks/measurement/dense-performance-evidence/SKILL.md)
for a separately authorized comparison; a source call graph is not a measurement.

The existing repository identity is `afd_plugin`. Its runtime descriptor stays
caller-command driven and backend compatibility stays unverified. This candidate
does not launch workers or supply a validated deployment recipe.

## Required input

Collect the plugin and actual vLLM/PyTorch/CUDA/NCCL revisions, selected connector,
role, A/F worker counts, global DP rank and local PCP/TP coordinates, native worker
rank/local device rank, and the actual eager dense-layer dispatch. For one
layer/stage, obtain control-derived peer token counts, subgroup roster, payload
shape/dtype/device, transfer context and returned peer slices. Mark an unobserved
edge missing rather than filling it from another rank namespace.

## Rule 1 — Resolve the peer's rank namespace

1. Follow runner construction → `AFDConnectorFactory.create_connector` →
   `resolve_role_rank` → `build_rank_mapping` (F1). Native worker rank is passed
   separately; the factory derives role rank from DP/PCP/TP. The resolver treats
   global DP as already including its configured start-rank offset.
2. Write a ledger for **role rank, AFD world rank, subgroup index/local rank and
   metadata-plane participation**. At this pin, FFN world ranks precede
   Attention; each FFN leads its subgroup at local rank 0. Attention role rank
   `a` joins `floor(a*F/A)`. A >= F is required; an integral A/F ratio is not.
3. Check each role rank is in range and every worker agrees on the counts and
   rendezvous. Reconstruct the actual subgroup roster before reading a send/recv
   argument: payload peers use subgroup-local ranks. Collective initialization
   call sites do not prove the rendezvous succeeded (F2).
4. Keep control distribution separate from data ownership. For A=3,F=2,
   subgroup world rosters are `(0,2,3)` and `(1,4)`: A1 sends hidden states to
   F0, while A1 distributes DP control to F1. A2 has no metadata-group
   participation (F1/F2). Do not infer a data peer from the control sender.

Stop on A < F, invalid role rank, duplicate/missing assignments or an unresolved
namespace. Return the conflicting ledger entries and their actual callers;
do not invent a replacement rank or attribute the mismatch to physical networking.

## Rule 2 — Preserve stage and per-peer token ownership

1. Confirm the selected eager dense-layer path, gating flag and initialized
   connector. Match the Attention forward-context sidecar and the FFN control
   payload for the same stage before following data-plane calls (F3).
2. Follow `RemoteFFNProxy` → `send_attn_output` → FFN
   `recv_attn_output` → FFN model entry → `send_ffn_output` →
   `recv_ffn_output` (F3). Record the subgroup-local peer and stage on each edge.
   This selected trace does not audit every native model dispatcher or MLP kernel.
3. Preserve each peer's rows and sequence length in subgroup order through
   concatenation and output splitting. For A=3,F=2 with resolved peer lengths
   A0=2,A1=5,A2=3, F0 handles 7 rows and returns lengths 2,5; F1 handles 3.
   A matching total does not establish that each peer gets its own rows.
4. Check the matching receive context was retained through FFN compute. The
   source has an even-split fallback when the count of recorded peer lengths is
   unusable; that fallback does not prove original ownership. Eager token-shape
   validation is skipped during compile tracing and does not detect a permutation
   that preserves the total (F3).
5. Record receive-buffer identity as well as shape/dtype/device. The proxy passes
   its post-yield tensor as a receive reference; the helper reuses a matching
   reference, otherwise allocates (F4). Do not mutate or release a buffer based
   only on a Python call return. Establish the actual communicator/stream
   completion contract before proposing reuse across streams.
6. Return the earliest evidenced missing/mismatched stage, peer, length or
   ownership edge, plus the smallest missing observation. A blocked receive
   requires its real control/data peer evidence; the shutdown call sites alone
   do not establish drain or cancellation (F4).

## Verification proposal and counter-signals

Proposed checks, not executed: retain the literal A=3,F=2 and divisible A=4,F=2
rank ledgers; reject A<F and out-of-range role ranks. For the selected real
eager exchange, compare distinct per-peer row identities and actual FFN outputs
against a separately specified numerical oracle while preserving layer, stage,
dtype and peer lengths. Include swapped lengths with the same total and a
mismatched-stage control payload. A formula-only check, fake custom-op path or
scalar token-sum assertion cannot verify a real exchange.

The source reaches real `PyNcclCommunicator.send/recv` on the current CUDA stream;
the FFN loop contains a step-end `torch.cuda.synchronize()` (F4). These are source
observations, not completion, graph, transport or performance qualification.
The underlying communicator completion contract and the complete DP/PCP/TP
token-count projection are outside this readset. Native execution, full-model
quality, multi-host placement, hardware compatibility and agent efficacy remain
unverified.

Available action: produce the bounded rank/payload ledger and a proposed
verification plan. Benefit sought: distinguish namespace or peer/stage mismatch
from an unproven transport diagnosis. Cost: caller-level tracing and per-peer
reference comparison; concatenation, buffers and synchronization may affect
memory or exposed waits, but their cost is not measured here. Keep a working
baseline and obtain separate authorization before runtime experiments or changes.
