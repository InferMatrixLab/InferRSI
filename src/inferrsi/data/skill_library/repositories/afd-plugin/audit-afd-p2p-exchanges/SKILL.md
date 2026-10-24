---
name: audit-afd-p2p-exchanges
description: Audit CUDA P2pNccl Attention/FFN rank namespaces and per-stage, per-peer hidden-state ownership when uneven worker counts or a mismatched return slice make an AFD exchange ambiguous.
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
[benchmark design](../../../methods/inference-benchmark-design/SKILL.md) and
[evidence classification](../../../methods/dense-performance-evidence/SKILL.md)
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
