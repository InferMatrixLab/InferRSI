# Source notes: vLLM KV lifetimes

Evidence origin: Dot's supplied 2026-10-15 implementation bundle. The ledgers below retain the supplier's pinned code/documentation inspection; local integration did not repeat those upstream reads. These are code/docs-derived contracts and proposed procedures, not paper-derived mechanisms or empirical results.

## Provenance and limits

- Upstream: [vllm-project/vllm](https://github.com/vllm-project/vllm), immutable revision [`7f730b4cea9a66520a9200265928ebe016b48a39`](https://github.com/vllm-project/vllm/commit/7f730b4cea9a66520a9200265928ebe016b48a39).
- Retrieved through the GitHub connector on 2026-10-15. `vllm/distributed/kv_transfer/kv_connector/v1/base.py` blob: `8997571407d5c327fb9e35d709c2e43a1942f537`; `vllm/v1/core/sched/scheduler.py` blob: `a6ca6074dfda0ac56e3b8f49adae58bc199cd324`.
- Both files state Apache-2.0 licensing and copyright to contributors to the vLLM project. Bounded excerpts are attributed to that project. The operational procedure is proposed here, not an upstream endorsement.
- Read scope: connector-base contracts/defaults and their scheduler-side matching/allocation/metadata, completion, preemption, failure, and freeing consumers. No concrete connector subclass, worker/model-runner invocation, transport, configuration schema, or test was inspected. No hardware, benchmark, AREX, or DisCo execution occurred. Empirical validation: **not_run**.
- F means code behavior at this pin or a specifically marked contract/documentation statement. P means an unvalidated operational procedure/test idea. The base class explicitly warns that its API is experimental at [lines 220–223](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L220-L223). Do not extend these facts to other pins or backend stacks.

## F evidence ledger

### F1 — Match/allocation/metadata contract (contract with scheduler consumer)

[`base.py` module contract, lines 6–21](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L6-L21) says matching may repeat and should be side-effect free. [`get_num_new_matched_tokens`, lines 516–548](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L516-L548) distinguishes unknown, zero, and positive matches and limits claims to an actually available prefix.

[`update_state_after_alloc`, lines 569–592](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L569-L592) documents two allocation callbacks for an async request and says:

```text
Decide whether to load based on ``num_external_tokens``, not on
whether ``blocks`` is empty
```

[`Scheduler.schedule`, lines 1284–1293](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1284-L1293) supplies actual request blocks and the external-token count. [Lines 1524–1530](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1524-L1530) build connector metadata. [`build_connector_meta`, lines 595–605](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L595-L605) documents state reset and a narrow exception to not mutating scheduler output: synchronous READ connectors may remove fully overwritten attention blocks from zeroing only with completed loads before use and step failure on load error.

### F2 — Async counted tokens are not readiness (implementation)

[`Scheduler.schedule`, lines 1109–1112](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1109-L1112) schedules zero new tokens for async loading. [Lines 1320–1341](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1320-L1341) sets `WAITING_FOR_REMOTE_KVS`, computed-token accounting, and an in-progress fetch stage before the transfer completes.

[`_handle_blocked_waiting_request`, lines 3181–3192](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3181-L3192) returns false until the request is in `finished_recving_kv_req_ids`, then updates cache state and promotes it to WAITING or PREEMPTED. [`_update_from_kv_xfer_finished`, lines 3212–3238](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3212-L3238) records receive completion and a completed-waiting stage. Promotion does not itself prove immediate forward execution.

### F3 — Worker ordering is an interface obligation, not traced execution

[`bind_connector_metadata` / `clear_connector_metadata`, lines 249–280](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L249-L280) set/clear metadata and document before/after execution placement. [`handle_preemptions`, `start_load_kv`, `wait_for_layer_load`, `save_kv_layer`, lines 326–383](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L326-L383) document pre-overwrite handling and load/save hooks.

[`wait_for_save`, lines 386–396](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L386-L396), bounded contract excerpt:

```text
Called once per step, including empty steps, after any target and draft
forwards. Metadata remains bound during this call.
```

Its contract requires retaining async save source blocks until scheduler completion reporting, or waiting for saves before return. These methods include abstract/no-op implementations: their presence does not show any backend satisfies their ordering.

### F4 — Connector retention and write fencing are separate (contract plus implementation)

[`request_finished`, lines 631–650](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L631-L650) promises one finish callback before freeing and allows returning true for asynchronous retention. [`get_finished`, lines 398–414](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L398-L414) requires send/save completions to belong to current/prior finished-request notifications. The default `get_transfer_results` wraps that method at lines 416–424.

[`Scheduler._free_request`, lines 2717–2747](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2717-L2747) combines delayed-free flags before `_free_blocks`; [`_update_from_kv_xfer_finished`, lines 3235–3238](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3235-L3238) frees finished sends. [`_connector_finished`, lines 3008–3061](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3008-L3061) chooses the single-group or `SupportsHMA.request_finished_all_groups` path and combines partial-tail retention.

Separately, [`Scheduler.__init__`, lines 186–194](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L186-L194) activates deferred freeing for multiple concurrent batches with a KV consumer. [`_request_blocks_can_be_freed`, lines 2762–2767](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2762-L2767):

```python
return not self.defer_block_free or (
    request.last_sched_seq <= self.processed_step_seq
)
```

[Lines 2769–2804](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2769-L2804) retain blocks behind a sequence fence; [`update_from_output`, lines 2047–2051](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2047-L2051) advances processed sequence and drains eligible blocks. No concrete GPU-stream execution was observed.

### F5 — Reliable delivery affects stale-output policy (contract and implementation)

[`KVConnectorBase_V1.requires_kv_delivery`, lines 198–207](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L198-L207) defaults to producer role and distinguishes required handoff from best-effort caching. [`Scheduler.schedule`, lines 836–840](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L836-L840) passes this flag into preemption. [`_preempt_request`, lines 1571–1614](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1571-L1614) resets computed state and records stale output; [`update_from_output`, lines 2084–2106](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2084-L2106) drains stale shares and discards drop-mode output. Concrete subclass overrides must be checked.

### F6 — Failure reporting must also release the receive wait (contract and implementation)

[`KVConnectorTransferResults`, lines 88–98](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L88-L98), bounded contract excerpt:

```text
Failed receives also appear in ``finished_recving`` so the scheduler can
release the request from its transfer wait state.
```

[`get_block_ids_with_load_errors`, lines 426–444](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L426-L444) requires async block errors no later than receive-completion reporting; sync errors belong to their detection pass.

[`Scheduler.update_from_output`, lines 2060–2074](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2060-L2074) processes request-level and block-level errors before normal output handling; [lines 2331–2333](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2331-L2333) process completion later. [`_handle_failed_recving`, lines 3344–3357](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3344-L3357) handles waiting failed requests according to the configured recompute policy.

[`_handle_invalid_blocks`, lines 3368–3377](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3368-L3377) raises for multiple KV groups because flat IDs are not globally unique; its message requires `KVConnectorTransferResults.failed_recving`. Single-group handling at lines 3381–3439 and `_update_requests_with_invalid_blocks` at lines 3240–3342 adjusts affected-prefix accounting; `_update_waiting_for_remote_kv` at [lines 3126–3176](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3126-L3176) caches valid data, handles zeroing/release, and applies replay/full-hit token adjustment. These branches are source facts, not tested recovery guarantees.

### F7 — Graph requirement and resource classification are conditional (contract/defaults)

[`requires_piecewise_for_cudagraph`, lines 710–729](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L710-L729) documents overriding the default false when layerwise asynchronous load/save hooks require Python synchronization between graph pieces. No concrete override or graph caller was inspected.

[`_cache_hit_source`, lines 184–186](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L184-L186) defaults to external-unspecified and allows host/disk/P2P attribution. [`set_host_xfer_buffer_ops`, lines 311–315](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L311-L315) is a no-op hook despite its host/device-copy documentation. Neither names nor interfaces establish an inspected Network, host-memory, SSD, H2D, or IPC data path.

## P extraction boundary and open uncertainties

The candidate proposes event-ledger reconstruction and conformance questions, not automatic repair. Before any correctness assertion or regression execution, inspect the selected concrete connector, its worker/model-runner consumer, and matching tests at the same pin. Unknowns include aggregation across workers, completion delivery guarantees, physical cache tier/transport, tested graph modes, exact configuration legality, and target-backend compatibility. No script is supplied because no justified executable procedure or test harness was established.

## Resource scope

Accelerator / KV lifecycle: request/block event-ledger requirements, ownership diagnosis and proposed conformance checks. No concrete connector, caller or transport was traced; no RAM/Host, SSD, Network or OS coverage is established.
