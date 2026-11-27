# xLLM on Ascend: accounting for prefill reuse and decode transfer

At [xLLM revision `90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4`][version] (`0.12.0` in
`version.txt`), a prefill-side prefix hit can reduce the tokens computed in a
chunk. A separate operation prepares the decode instance to serve the next
token. Account for both before estimating how much of a request can get faster.
This source inspection extends the [prefix-reuse cost comparison](mooncake-prefix-reuse-feasibility.md)
with one engine's actual scheduling and transfer boundaries.

## Trace one request

| Decision | What the pinned source shows | How to use it |
| --- | --- | --- |
| Which scheduler runs? | [Selection][factory] tests `enable_disagg_pd`. [Construction][create] picks `PDScheduler` or the continuous scheduler. The [batch policy][mode] disables mixed batches on a disaggregated `PREFILL` instance. | Check the effective flag and role on each instance. Chunking by itself also exists on the continuous path. |
| Which prompt tokens need compute? | [Prefill allocation][chunk] normally looks up shared blocks before computing the number of new tokens in the chunk. It bounds the end by both the prompt length and the cached-token count plus the budget. Linear-attention models can introduce an alignment step. Redistribution can skip a shared lookup to avoid matching the sequence's own published blocks. | Record matched tokens, newly scheduled tokens and the chunk budget separately. Block capacity can include reserved but uncomputed tokens. A cold prompt has no reusable prefix. |
| Is decode ready? | The [decode admission RPC][admit] first tries to allocate the destination blocks and prepares the transfer metadata, then publishes a reservation. It distinguishes an overlong prompt from transient cache pressure. The [first-generation handler][id] also checks the request and reservation identity. | Trace one request across both roles. Refuse the handoff on a stale reservation, even if the request identifier matches. |
| Did the KV arrive? | On native `PULL`, the [restore path][pull] checks group identities and local/remote block counts, then checks transfer success before normal enqueue. The same code describes a different ordering for heterogeneous `PUSH`, in which writes precede the first-generation message. | Record the transport mode, both endpoints, rank mapping and restore outcome. A prefix hit on prefill or an accepted reservation on decode establishes neither transfer completion nor interoperability. |

The [P/D example][pd] uses etcd for instance metadata and an external xLLM
Service for routing. Its example launches separate prefill and decode roles
with both chunking and prefix caching disabled. Its later note describes
enabling both on the prefill path. The [Ascend guide][ascend] separately
documents compatible drivers, a model-supported NPU image and an example
using HCCL. Its single-service health check cannot test a cross-instance handoff.

## Recheck and reject

1. On the pinned source, follow the factory into the batch policy. With
   disaggregation off, the factory must select the continuous path. With it on
   and role `PREFILL`, confirm the policy disables mixed batches.
2. Compare a prompt with no match against one with a matched prefix. Read
   `allocate_for_prefill` and check that new compute is the difference between
   the target position and the sequence's current KV token count (including any shared prefix and earlier computed chunks). Follow the allocation
   target separately if full-prompt reservation is enabled.
3. Inspect the upstream [failed-pull test definition][test]. A fake worker
   returns failure after decode has reserved blocks. Its assertions require the
   free-block count to recover and the decode queue to stay empty. The test
   body is an oracle for this failure path. It supplies no hardware result.
4. For a future service comparison, hold weights, tokenizer, KV representation,
   device budget, arrival trace and prompt/output lengths fixed. Include cold
   and repeated-prefix requests. Capture queue time per role, actual prefix
   tokens, bytes transferred, restore time, TTFT, token-gap distribution and
   failed requests. With unknown topology or cache representation, or with only
   a health response or a prefix-hit counter, leave service impact unresolved.

**Evidence.** `empirical_validation: not_run`. The deployment commands are
upstream examples. No scheduler tests, service, external router, transport
or NPU result was executed or qualified for this source note.

**License.** The pinned [root license][license] is Apache-2.0. The inspected
implementation and test carry xLLM Authors' Apache-2.0 notices. The
[third-party notice][notices] assigns component-specific terms, including
BSD-3-Clause for etcd-cpp-apiv3 and Apache-2.0 for bRPC. This note includes
original analysis and links only. External xLLM Service, dependencies, images
and model weights are outside the inspected source scope.

[version]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/version.txt
[factory]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/xllm/core/scheduler/scheduler_factory.cpp#L26-L32
[create]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/xllm/core/scheduler/scheduler_factory.h#L42-L70
[mode]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/xllm/core/scheduler/scheduler_policy.cpp#L1150-L1193
[chunk]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/xllm/core/scheduler/scheduler_policy.cpp#L584-L653
[admit]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/xllm/core/disaggregation/pd_service_impl.cpp#L229-L299
[id]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/xllm/core/disaggregation/pd_scheduler.cpp#L999-L1079
[pull]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/xllm/core/disaggregation/pd_scheduler.cpp#L1140-L1228
[pd]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/docs/src/content/docs/en/features/disagg_pd.md
[ascend]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/docs/src/content/docs/en/hardware/ascend_npu.md
[test]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/tests/core/scheduler/pd_scheduler_test.cpp#L1141-L1186
[license]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/LICENSE
[notices]: https://github.com/xLLM-AI/xllm/blob/90f6f13ea3d94334d4b5bd73d9fb23fc66bef1e4/THIRDPARTYNOTICES.md
