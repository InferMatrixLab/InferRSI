# Extension and validation contracts

## Select the owner before editing

| Change | Primary owner | Contract to preserve |
|---|---|---|
| New model decomposition | Model `pipeline.py`, registry, input processors, deploy default | Stage identity, supported modality and exact conditioning/weight semantics |
| Stage placement or replica lifecycle | Stage runtime, stage pool, membership and clients | Readiness, affinity, liveness, failure propagation and idempotent shutdown |
| Cross-stage progression | Orchestrator | Request/segment identity, stage completion, abort and upstream/downstream ordering |
| Payload transfer | OmniConnector and transfer adapter | Shape/dtype/device, lifetime, get deadline, consumed acknowledgement and cleanup |
| Diffusion step integration | Protocol, runner and per-request step state | Preparation once, independent RNG/latent/scheduler state, final decode, cancel/release |
| Output representation | Output modality, payload and accumulation | Named field semantics, delta vs snapshot, concatenation axis and terminal output |

`OutputModality.from_string` accepts canonical lowercase `text`, `image`, `audio`, `latent`, `token_ids` and `+`/`,` compositions; `None` means text. Aliases (`wav`, `speech`, `tokens`), whitespace, case variants and empty strings fail. `video` is not a canonical value in this particular engine output enum; video serving uses its own media contract. Token IDs and continuous latents are distinct even if a legacy producer has a historical contract. Audio defaults to last-axis concatenation; image/latent/token-ID defaults to dimension 0; named conditioning snapshots can override this with REPLACE. A renamed tensor key can therefore silently break accumulation.

Transport success must mean the consumer may safely use the data, not merely that a send was enqueued. Do not cancel an in-flight DMA read by freeing its source buffers. Deadline/failure/cancel paths must retire bookkeeping and release resources with correct ownership; test races as well as steady state.

## Native test recipes

Run from the pinned engine checkout after installing its compatible development environment. These are selected recipes, not claims of local execution:

```bash
python -m pytest tests/config/test_config_merge.py tests/config/test_pipeline_registry.py -q
python -m pytest tests/engine/test_output_modality.py tests/engine/test_multimodal_accumulation.py -q
python -m pytest tests/engine/test_orchestrator_error_handling.py tests/engine/test_async_omni_engine_abort.py -q
python -m pytest tests/diffusion/test_diffusion_step_pipeline.py tests/diffusion/test_step_request_lifecycle.py -q
python -m pytest tests/distributed/omni_connectors/test_chunk_transfer_adapter.py tests/distributed/omni_connectors/test_shm_connector.py -q
```

The test tree loads package fixtures; a CPU marker does not promise a stdlib-only environment. Real RDMA/native connector tests additionally need their actual hardware/services. Choose model/backend tests for changed components, then a real checkpoint request.

## Gate sequence and observations

1. **Source/static**: inspect changed fields and call sites, parse config, verify supported combinations. Reject topology-in-YAML mistakes and incompatible modes early.
2. **Contract**: run parser/output/merge/runner tests relevant to the change; include invalid input and cancellation. Use fake tensors/transports only for the behavior they model.
3. **Required backend**: run GPU/accelerator kernels, graph capture/replay, native transport and multi-rank parity on the affected deployment. Record `BLOCKED_REQUIRED_BACKEND` if unavailable.
4. **Real model**: compare single/multi-request and streamed/non-streamed output; verify prompt/conditioning isolation, deterministic settings with numerical tolerances, task quality, audio text agreement/continuity, video timing/quality and no resource growth after abort/repeated requests.
5. **Performance**: only after prior gates, run matched repeated measurements; preserve errors and quality failures. Compilation cache, warmup, workload and resolved backend must be comparable.

The portable package's local probe loads the real stdlib-only output enum by file path, checks valid/invalid strings, retention sets and accumulation rules, and parses a concrete deployment as YAML. It does **not** import the full engine, run its pytest suite, validate schema resolution or execute GPU inference. This narrow probe can catch guidance drift but cannot certify an engine.

See [source evidence](../../../references/evidence.md) and [serving recovery](../../omni-serving/references/serving.md).
