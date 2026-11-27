# Source notes: vLLM admission pressure

Evidence origin: Dot's supplied 2026-10-15 implementation bundle. The ledgers below retain the supplier's pinned code/documentation inspection; local integration did not repeat those upstream reads. These are code/docs-derived contracts and proposed procedures, not paper-derived mechanisms or empirical results.

## Provenance and limits

- Upstream: [vllm-project/vllm](https://github.com/vllm-project/vllm).
- Immutable revision: [`7f730b4cea9a66520a9200265928ebe016b48a39`](https://github.com/vllm-project/vllm/commit/7f730b4cea9a66520a9200265928ebe016b48a39).
- Source retrieved through the GitHub connector on 2026-10-15. Scheduler blob SHA: `a6ca6074dfda0ac56e3b8f49adae58bc199cd324`; connector-base blob SHA: `8997571407d5c327fb9e35d709c2e43a1942f537`.
- Attribution: both files identify `SPDX-License-Identifier: Apache-2.0` and `Copyright contributors to the vLLM project`. Excerpts below retain that provenance; this is a candidate procedure, not an upstream-authored skill.
- Bounded read set: `vllm/v1/core/sched/scheduler.py`, focused on initialization, `schedule`, preemption, deferred freeing, stats, and connector completion/failure handling; `vllm/distributed/kv_transfer/kv_connector/v1/base.py`, focused on matching, ownership, and completion contracts. Whole-file retrieval was used to locate these symbols. No concrete transport, worker invocation path, cache-manager internals, configuration schema, or tests were inspected.
- F = source fact about code or an explicitly identified source contract. P = proposed diagnostic action or verification experiment. A source branch is not proof of observed runtime behavior or a performance result. Empirical validation: **not_run**.

## F evidence ledger

### F1 — Separate budgets and admission caps (implementation)

[`Scheduler.__init__`, lines 128–141](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L128-L141) derives running slots from `max_num_seqs`, active admission from `max_num_active_seqs` with a fallback, and scheduling-token capacity from `max_num_scheduled_tokens` with a fallback. [`schedule`, lines 609–617](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L609-L617) initializes independent token/input budgets; [lines 850–857](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L850-L857) charge draft slots to the input budget.

Bounded excerpt:

```python
token_budget -= num_new_tokens
input_budget -= num_new_tokens + draft_slots
```

Scope limit: these reads establish consumption in this scheduler, not CLI spellings, supported ranges, or safe target values.

### F2 — Early constraints and conditional long-prefill cap (implementation)

[`schedule`, lines 634–773](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L634-L773) handles DP prefill throttling, eligible-request counts, adaptive long-prefill caps, RUNNING-first selection, draft/input budget, decode cadence, encoder readiness, model-length bounds, Mamba alignment, and zero-token skips.

Bounded excerpt, lines 645–649:

```python
long_prefill_token_threshold = (
    self.scheduler_config.long_prefill_token_threshold
    if num_eligible_reqs > 1
    else 0
)
```

The adaptive branch uses the maximum of the configured threshold and `input_budget // num_eligible_reqs`. Zero-token `continue` permits later requests; this is not a strict FCFS execution guarantee.

### F3 — Allocation failure does not imply immediate preemption (implementation)

[`schedule`, lines 775–848](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L775-L848) retries allocation, checks connector pending frees, selects a victim by maximum `(priority, arrival_time)` or the tail of `running`, and checks whether its blocks can be freed. A previously scheduled priority victim has token/input budget and relevant encoder budget restored.

Bounded excerpt, lines 788–792:

```python
if (
    self.connector is not None
    and self.connector.has_pending_block_frees()
):
    break
```

[`_preempt_request`, lines 1571–1614](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1571-L1614) frees/defer-frees blocks, resets computed-token state, tracks stale in-flight output, increments preemption count, and prepends the request to waiting. This supports investigating recomputation; it does not quantify its cost.

### F4 — Waiting admission has independent gates (implementation)

[`schedule`, lines 899–952](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L899-L952) enters waiting admission only without new preemptions and without `PAUSED_ALL`, drains KV holders before ordinary waiting, permits only KV holders under `PAUSED_NEW`, counts paused streaming sessions toward active requests, and checks blocked status, stale output, and LoRA capacity.

Bounded excerpt, lines 922–924:

```python
num_running = len(self.running) + self.num_waiting_for_streaming_input
if num_running >= self.max_num_active_reqs:
    break
```

[`_handle_blocked_waiting_request`, lines 3178–3210](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L3178-L3210) distinguishes unfinished remote loads, grammar readiness, and streaming-input waits.

### F5 — External-hit lookup, allocation, and readiness are different (implementation plus contract)

[`schedule`, lines 969–1048](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L969-L1048) queries a block-aligned local boundary, skips unknown matches, reconciles partial local tails and hybrid hits, and checks total computed tokens. [`KVConnectorBase_V1.get_num_new_matched_tokens`, lines 516–548](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L516-L548) documents `None` as undecided and requires asynchronous=False when the count is zero. Availability of the prefix is a connector obligation, not verified here.

[`schedule`, lines 1109–1112](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1109-L1112):

```python
if load_kv_async:
    # KVTransfer: loading remote KV, do not allocate for new work.
    assert num_external_computed_tokens > 0
    num_new_tokens = 0
```

[Lines 1221–1293](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1221-L1293) defer speculative lookahead for async loads, pass in-flight reservations to allocation, delay cache blocks, and call `update_state_after_alloc`. [Lines 1320–1341](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L1320-L1341) mark `WAITING_FOR_REMOTE_KVS` and assign `num_computed_tokens` before the data arrives. Actual memory arithmetic remains delegated to the unread cache manager.

### F6 — Deferred freeing fences in-flight writes (implementation)

[`Scheduler.__init__`, lines 186–194](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L186-L194) enables deferred free for multiple in-flight batches with a KV consumer. [`_request_blocks_can_be_freed` through `_drain_deferred_frees`, lines 2762–2804](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2762-L2804) uses scheduled/processed sequence fences. [`update_from_output`, lines 2047–2051](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2047-L2051) advances the processed counter and drains deferred frees for nonempty steps. This is distinct from connector-owned asynchronous send completion.

### F7 — Observations exist conditionally (implementation)

[`make_stats`, lines 2918–2962](https://github.com/vllm-project/vllm/blob/7f730b4cea9a66520a9200265928ebe016b48a39/vllm/v1/core/sched/scheduler.py#L2918-L2962) returns `None` without `log_stats`. Otherwise it emits running/waiting/skipped counts, KV-fetch stages, KV usage, prefix-cache data, and optional connector data. The waiting count subtracts `len(deferred_waiting)`; do not sum incompatible snapshots or call it total waiting without accounting for skipped requests. No Prometheus series names or performance thresholds are established here.

## P operational extraction and verification boundary

The candidate converts F1–F7 into a branch/accounting diagnosis and a conditional one-variable hypothesis. It does not introduce a scheduler algorithm or recommend cap values. Proposed replay fixtures in SKILL.md are unimplemented, unrun, and must first be matched to pinned test infrastructure. Worker ordering, allocator arithmetic, production configuration legality, fairness, and speedup remain open.

## Resource scope

Accelerator / Serving / Runtime / KV: conditional observation, admission diagnosis and configuration hypotheses; verification is proposed, not executed. No RAM/Host, SSD, Network or OS-priority coverage follows from these branches.
