# AFD P2P source notes

## Identity, evidence classes and license

Canonical repository: [vllm-project/afd-plugin](https://github.com/vllm-project/afd-plugin),
repository ID `1238474765`, commit [`df8d6a0c403c3ca1b4ed9cf1687e7204908bebec`](https://github.com/vllm-project/afd-plugin/commit/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec),
tree `923a712f6976ce883395f55b03aeb43e50964a19`. Sources were retrieved at that
fixed revision on 2026-10-23. The original six-file intake cache was reused;
eight caller/metadata files at the same pin supplied the bounded extension.
Retrieval of a complete file is not a semantic audit of its unread portions.

**F** denotes inspected implementation; **D** an upstream description;
**T** unexecuted native-test source; **P** the proposed audit/verification rules.
No F/D/T entry is a locally executed exchange or model result. The
[historical intake](https://github.com/InferMatrixLab/InferRSI/blob/48e0d5894117be7c57f8b4ce793c0ec986f219e8/docs/reviews/issue91-afd-plugin-intake.md)
is retained as intake-only history.

The selected Python files carry `SPDX-License-Identifier: Apache-2.0` and
copyright attribution to contributors to the AFD plugin project. The complete
[upstream LICENSE and retained notice](afd-plugin-LICENSE.md) is preserved
without changing its bytes. Its [MIT notice](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/LICENSE#L203-L229)
specifically covers imported NPU routed-only asynchronous CAM operator sources
and adapted bindings. Those implementations are excluded; do not infer a common
license for every dependency, model or repository file.

## Exact bounded readset

Each range below identifies evidence used, with complete-file retrieval kept
separate. The README ranges are carried intake evidence; the source extension
does not re-audit its performance/deployment claims.

| Fixed source / inspected ranges | Git blob | Use |
| --- | --- | --- |
| [README.md:11–25,57–65,302–309,337–339](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/README.md#L11-L25) | `95f7a9b4b611eaee75fa6d168f444e118eddb722` | D, carried intake compatibility/connector/activation/license statements |
| [LICENSE:1–12,203–229](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/LICENSE#L203-L229) | `ecad9322682f406d448bb428ffeb7a2e2531195c` | License/notice boundary; complete original file retained locally |
| [config.py:311–350](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/config.py#L311-L350) | `2e004e572f9ad7cc7d0fc297ee6a63edc2a2ae7b` | F, connector-specific validation and positive counts; original intake read file in full |
| [topology.py:1–183](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/distributed/topology.py#L61-L183) | `20be8f64c6e2108f40df2bfbc3c86b0b01bf5362` | F1, rank producer/mapping |
| [connectors/factory.py:1–105](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/factory.py#L50-L105) | `6e94e1ac1d36fbdff90c8eb4161f5cb7156060ce` | F1, real resolver caller and concrete P2pNccl registration |
| [connectors/metadata.py:1–23,172–284](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/metadata.py#L172-L284) | `f8c23bd02bdf679f2618f9158b1ed3a3281a4fd3` | F3, per-peer lengths, leading-dimension validation and transfer context |
| [connectors/gpu/p2p.py:1–205,207–426,428–618,620–884,930–1015](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L243-L312) | `a0be75ed8bacc6fde8734f46e5208676a5d5fa90` | F1–F4, mapping consumers, control/data calls, buffers, split and cleanup; D module limitations |
| [attention_metadata.py:1–116,211–269](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/attention_metadata.py#L211-L269) | `6f87ffb145c7470a7cbef4ec5da06f3fde72ad26` | F1/F3, native ranks, eager sidecar and control producer |
| [attention_model_runner_v2.py:1–2,128–170,317–357,369–465,570–597](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/attention_model_runner_v2.py#L369-L465) | `a4061f84d294161620d2987ad7c77c26407db9d5` | F1–F3, constructor/factory, connector initialization and execution-scoped metadata-provider call |
| [ffn_worker.py:1–3,107–226](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/ffn_worker.py#L107-L226) | `b657da8f056b49c2e79d9248cdfe626525a5b688` | F2–F4, control-driven loop, synchronization and shutdown calls |
| [ffn_model_runner.py:1–115,153–288,438–464](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/ffn_model_runner.py#L186-L268) | `e31d6c239efdbdb0e3d8ee600dbff7f310b6aec7` | F1/F3/F4, factory, layer/stage payload consumer, compute entry, return and cleanup |
| [deepseek_v2.py:1–3,117–160,430–463,480–524,649–705,865–878,930–945](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/model_executor/models/deepseek_v2.py#L117-L158) | `5e40c05b89a04e3b78e48d0128b2e981edae4a38` | F3, selected dense proxy, branch conditions and FFN model forwarding |
| [models/forward_context.py:1–73](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/model_executor/models/forward_context.py#L18-L66) | `0cdd3a0aa88acfd44d63c6d4094f1d242b1dd95c` | F3, actual provider wrapper and proxy getter over `additional_kwargs` |
| [test_topology_partition.py:1–112](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/tests/unit/distributed/test_topology_partition.py#L21-L112) | `9fc955dde26f59972671d7349313412c71a520f6` | T, literal uneven and divisible layouts, partition completeness and role agreement |

The README targets vLLM v0.30.0 / `ced6857a` and vllm-ascend `8d4409d6`.
These carried short references are upstream compatibility statements, not a
locally frozen dependency tuple. The README recommends Decode; the P2P module
describes prefill/decode and restricted graph support. The module's
[2A2F cross-node verification statement](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L43-L58)
is an author statement whose original runtime artifacts were not examined.
This candidate qualifies neither that deployment nor the broader described modes.

## F1 — Derive role rank, then communication namespaces

The Attention runner obtains native world/local ranks through
`attention_metadata._resolve_world_ranks`; the FFN runner has the same helper.
Both read `get_world_group().rank/local_rank` and call the factory.
[Factory:50–68](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/factory.py#L50-L68)
separately calls `resolve_role_rank` and passes the result to the concrete
connector. Worker rank is not the AFD communication-world rank.

[Resolver:61–105](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/distributed/topology.py#L61-L105)
linearizes `(global_dp_rank * pcp_size + local_pcp_rank) * tp_size + local_tp_rank`.
Its comment identifies global DP as already including start rank; the resolver
does not add a second offset. The PCP/TP accessors are imported only
when their size exceeds one. The result must be in the selected role's range.

[Mapping:108–183](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/distributed/topology.py#L108-L183)
requires A >= F and maps Attention role rank a to world F+a and subgroup
floor(aF/A). FFN role rank i is world/subgroup i. Its Attention block is
`[ceil(iA/F), ceil((i+1)A/F))`, so uneven counts are supported. The FFN world
rank leads the subgroup roster; each local rank is its index in that roster.

| A=3,F=2 worker | Role | AFD world | Subgroup world roster | Local rank | Stored metadata-plane rank | Metadata participation |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| F0 | 0 | 0 | (0,2,3) | 0 | 0 | Receive from A0 |
| F1 | 1 | 1 | (1,4) | 0 | 1 | Receive from A1 |
| A0 | 0 | 2 | (0,2,3) | 1 | 2 | Send to F0 |
| A1 | 1 | 3 | (0,2,3) | 2 | 3 | Send to F1 |
| A2 | 2 | 4 | (1,4) | 1 | 4 | Does not join metadata group |

A2's stored value does not authorize participation in the four-member metadata
group. A1's data peer is F0 while its control destination is F1. These are
different namespace/ownership questions.

## F2 — Mapping consumers and initialization boundary

[P2P construction/initialization](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L157-L312)
builds the mapping, joins an FFN-first AFD world, uses a subgroup-specific
PrefixStore, and supplies the subgroup-local rank to StatelessProcessGroup.
Two PyNcclCommunicator instances serve the two payload directions; a separate
NCCL process group carries DP control only on participating ranks.
[Control send/receive](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L829-L884)
selects its designated Attention sender independently of data fan-in.

Attention initialization is deferred until after native weight loading;
FFN `initialize_from_config` initializes the connector before starting its loop.
These source call sites require matching collective participation and
configuration; they are not an observed successful rendezvous or physical
network topology. Native process-group and communicator internals are not audited.

## F3 — Selected eager dense-FFN round trip

The Attention runner's [execute_model scope](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/attention_model_runner_v2.py#L317-L355)
wraps native execution with `use_afd_metadata_provider`. The
[provider and getter](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/model_executor/models/forward_context.py#L18-L66)
install the sidecar after native context creation, restore the original factory
on scope exit, and read `additional_kwargs["afd_metadata"]` for model wrappers.

The selected branch disables Attention-side gating and uses a dense layer:
[the constructor](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/model_executor/models/deepseek_v2.py#L480-L524)
installs RemoteFFNProxy when the remote-expert and Attention-gate branches do
not apply. CUDA MoE selects another branch and is excluded.

1. [The metadata mixin](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/attention_metadata.py#L211-L257)
   attaches the ordinary eager forward sidecar and publishes DP control before
   model/data-plane forward. [send_dp_metadata:75–116](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/attention_metadata.py#L75-L116)
   updates local connector state before sending. Per-stage control derives wire
   tensor metadata; the complete token-count projection helper is not audited.
2. [The FFN loop](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/ffn_worker.py#L160-L199)
   receives control and drives the FFN runner. The ordinary scheduler entry
   explicitly rejects FFN work. [The runner](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/ffn_model_runner.py#L186-L268)
   updates connector state, loops over layer/stage pairs and receives the payload.
3. [RemoteFFNProxy](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/model_executor/models/deepseek_v2.py#L117-L158)
   constructs layer/stage/token metadata and calls
   [send_attn_output](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L320-L387).
   Its payload peer is subgroup rank 0. Eager leading-dimension validation is
   skipped while compiling. Optional router logits/input IDs have their own
   alignment constraints; the selected dense payload does not require them.
4. [recv_attn_output](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L428-L552)
   receives subgroup peers 1..group_size-1 and concatenates along token rows.
   It constructs a context containing their individual lengths in that order.
   The runner retains this context, sets its layer/stage, computes the FFN result
   and passes the context to the return send.
   [Model forwarding](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/model_executor/models/deepseek_v2.py#L865-L874)
   reaches the selected layer's
   [non-gated MLP entry](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/model_executor/models/deepseek_v2.py#L649-L700).
   External native transformer dispatch and numerical MLP kernels are not audited.
5. [send_ffn_output](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L554-L618)
   uses the retained lengths to slice the result for subgroup-local peers.
   If the number of lengths differs from the number of peers, it attempts an
   even split only when divisible. Correct total shape or a possible fallback
   does not establish original per-peer ownership.

The transfer metadata checks that lengths are positive and their sum matches
the leading dimension. It does not itself detect a row permutation that
preserves total shape. The proposed audit must retain peer/stage provenance,
rather than calling scalar shape validation a numerical or ownership oracle.

## F4 — Receive buffers, stream calls and cleanup limits

The proxy invokes its DBO-yield helper between send and receive, then passes
that returned tensor as the receive reference. DBO helper semantics are unread;
DBO qualification is excluded.
[recv_ffn_output](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L389-L423)
receives from subgroup rank 0. [The helper](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L649-L697)
reuses a reference matching its derived shape/dtype/device, otherwise allocates.
A matching receive can therefore write into the supplied tensor.

[Real custom-op implementations](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L940-L974)
call PyNcclCommunicator send/recv on the current CUDA stream. The adjacent fake
implementations support compiler tracing and are not actual transfers.
The FFN loop contains a step-end CUDA synchronization. The underlying
communicator's full completion contract, cross-stream buffer reuse and achieved
overlap were not established by this readset.

[close](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/connectors/gpu/p2p.py#L221-L240)
unregisters communicator IDs and invokes communicator shutdown.
[FFN stop/shutdown](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/ffn_worker.py#L207-L223)
sets an event, calls runner shutdown and joins its thread with a timeout;
[runner shutdown](https://github.com/vllm-project/afd-plugin/blob/df8d6a0c403c3ca1b4ed9cf1687e7204908bebec/afd_plugin/v1/worker/ffn_model_runner.py#L442-L455)
closes the connector after cleanup. These call sites do not establish guaranteed
drain/cancellation of a receive already blocked in control or data communication.

## T and P verification boundary

The native partition test enumerates A/F pairs in 1..8 for A >= F, checks complete
balanced membership and agreement between roles, and retains literal uneven and
historical divisible layouts. It was inspected, not executed. It does not assert
a NCCL transfer, numerical FFN result, graph replay, early cancellation or gain.

Proposed rank and payload cases live in the repository's construction review
artifact, not as reported native/agent results. A later real exchange needs an
independent per-peer numerical oracle and its actual dispatch/dependency tuple.
Upstream imports/tests, distributed/device/model execution, multi-host transport,
quality, performance and agent efficacy are **not_run**. Static/readability checks
and installed-resource checks do not promote the candidate or fill those gaps.
