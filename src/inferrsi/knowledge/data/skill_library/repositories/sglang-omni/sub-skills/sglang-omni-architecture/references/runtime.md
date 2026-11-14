# Runtime contracts and optimization surface

## Ownership and flow

| Layer | Owns | First source to inspect |
|---|---|---|
| Pipeline config / topology / placement | Logical stages and routes; process membership; replicas, ranks and memory budgets | `config/schema.py`, `config/topology.py`, `config/placement.py` |
| Coordinator | Admission, request state and sticky process-replica bindings; terminal result collection; abort broadcast | `pipeline/coordinator.py`, `pipeline/replicas.py` |
| Stage | IO, full-payload fan-in, stream ingress and output routing; scheduler lifecycle | `pipeline/stage/runtime.py`, `pipeline/stage/input.py` |
| Scheduler | Request preparation/batching, inbox/outbox, compute loop, per-request or per-session lifecycle | `scheduling/message.py`, `simple_scheduler.py`, `session.py`, `omni_scheduler.py` |
| Worker / runner | SGLang infrastructure, model forward, sampling/output processing and model-specific embeddings/feedback | `scheduling/bootstrap.py`, `model_runner/model_worker.py`, `model_runner/base.py` |
| Comm / relay | Locality selection, payload packing, tensor movement, buffer lifetime/completion | `comm/router.py`, `comm/engine.py`, `comm/stage_io.py`, `relay/` |

Paths in the table are under `sglang_omni/`. `StageScheduler` includes `inbox`, `outbox`, `warm_up_serving_thread`, `start`, `stop`, `abort`. Incoming messages include new request/chunk/done/abort/admin; outgoing messages include result/stream/error/KV transfer/admitted. Do not narrow the contract to the older three-message documentation sketch.

`OmniScheduler` composes upstream SGLang scheduler behavior using unbound calls/delegation rather than inheritance. It reuses batching and cache mechanics while owning Omni requests/streaming. The `event_loop_overlap` entry explicitly raises because delayed `Req.inflight_middle_chunks` accounting corrupts chunked-prefill boundaries. An implemented model-specific async-decode path is a separate capability; its existence does not make this overlap loop supported. `SimpleScheduler` is for ordinary compute/local batching without AR KV scheduling; `SessionScheduler` owns ordered per-session operations, optionally batched across ready sessions. Streaming vocoders must accumulate, flush, and emit a terminal result.

Inspect each actual DAG. For Qwen3-Omni, preprocessing fans to encoders, request-dependent joins feed thinker/talker, thinker can stream to talker and decode, and talker streams codec chunks to code2wav. Text and speech variants differ. Do not force every variant through the same `mm_aggregate` stage. For Qwen3-TTS, preprocessing, engine and vocoder default to process `pipeline`; changing `process` changes whether process-local prepared state can be shared. The `PreparedRequestQueue` owns prepared/inflight/aborted transitions under a lock; an abort during preparation prevents subsequent publish.

## Communication and lifetime

There is no public transport backend selector. `CommRouter` uses locality, placement, platform and tensor device:

- Same-process eligible payloads/chunks use Python object references (`LOCAL_OBJECT`). Treat nested containers, tensors and metadata as read-only until consumers finish. For fan-out, projection must supply independent `data` containers; tensor leaves may be shared read-only.
- Compatible same-placement CUDA processes can use direct PyTorch CUDA IPC. Ownership follows CUDA IPC storage lifetime; these envelopes do not use relay ACKs.
- Other eligible same-node GPU edges use the platform's intra-node transport (CUDA IPC pool on CUDA, with availability checks/fallback); host edges use SHM. Cross-node configured remote edges use Mooncake. NCCL/NIXL implementation files are not evidence of arbitrary public selection.
- Relay-backed transfers use typed `DataRef`s, packed tensors and completion/ACK tracking. Do not free sender buffers after merely sending control metadata. Publish stream control before waiting for credit-based transfer completion so the receiver can start the read.
- Receiver `StreamQueue` is unbounded; backpressure belongs at sender/scheduler boundaries. Closing a request wakes a blocked receiver; late chunks cannot resurrect aborted state. Review EOS, fan-in and cleanup together when changing flow control.

## Search space with evidence boundaries

| Candidate | Existing surface | Constraint / observable decision |
|---|---|---|
| Concurrency/admission | Engine running/queued limits; factory request-build concurrency; coordinator capacity | Check 503, queueing and p95/p99, not only successful QPS |
| KV/graphs | Engine memory fraction, token limit, `kv_cache_bytes`, graph/compile fields | `kv_cache_bytes` conflicts with memory fraction and max-total-tokens; graphs add memory/startup cost |
| Stage layout | `process`, `gpu`, `tp_size`, stage GPU fractions; `processes` replicas/devices | TP and process replicas are distinct; keep state sharing and all per-GPU budgets valid |
| Same-GPU capacity | `mps` and `weight_share` where model/platform allows | MPS affects scheduling; weight sharing saves immutable weight memory, not KV/graphs/request state; no throughput guarantee |
| Stream latency | Model-specific chunking, partial startup, vocoder batching/async options | Inspect the exact factory; measure first audio plus continuity/quality, do not invent a global chunk flag |
| Precision/media work | Supported per-engine quantization and per-model media preprocessing | Requires model/backend support and output quality comparison; reduced video FPS changes workload/quality |
| New scheduling/transport policy | Code extension | Preserve state and transfer contracts; no undocumented flag or promised speedup |

Pinned evidence:

- [sglang_omni/config/schema.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/config/schema.py)
- [sglang_omni/config/topology.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/config/topology.py)
- [sglang_omni/pipeline/coordinator.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/pipeline/coordinator.py)
- [sglang_omni/scheduling/message.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/message.py)
- [sglang_omni/scheduling/omni_scheduler.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/omni_scheduler.py)
- [sglang_omni/pipeline/stage/runtime.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/pipeline/stage/runtime.py)
- [sglang_omni/pipeline/stage/stream_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/pipeline/stage/stream_queue.py)
- [sglang_omni/comm/router.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/comm/router.py)
- [docs/developer_reference/communication.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/communication.md)
- [sglang_omni/scheduling/prepared_request_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/prepared_request_queue.py)
- [sglang_omni/models/qwen3_omni/config.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/models/qwen3_omni/config.py)
- [docs/basic_usage/process_topology.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/basic_usage/process_topology.md)
