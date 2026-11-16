# Integration and test map

## Add the smallest model adapter

Find the checkpoint architecture and a matching scheduler pattern. A model's `config.py` exports `EntryClass`; `models/registry.py` discovers pipeline classes/architecture aliases and reports import problems. A missing model can be a dependency import failure. Register the actual AR architecture in the SGLang model-runner integration when required; pipeline discovery and model execution registration are different layers.

Keep topology in the config class, with existing-stage overrides exposed via typed stage/engine/factory fields. Dynamic routing/wait functions choose subsets of declared static edges. Validate exactly one normal routing choice (`next` or terminal), actual stage names, entry/terminal behavior, process membership, TP rank placement and budgets. Defining a YAML key does not implement a factory parameter.

Normalize API requests and explicit-vs-default sampling settings in the request builder. Preserve reference input and usage/finish reasons in typed payload/state. Build GPU factories with the repository device resolver; do not hardcode CUDA and claim other backends. Prefer the shared engine builder/bootstrap when the model uses SGLang AR; keep model-specific forward preprocessing/feedback in its runner. Cross-stage feedback requires an explicit transport/state design, not just a runner hook.

State ownership is part of the adapter contract. Process-local prepared/reference caches cannot silently become inter-process state. Abort must clean prepared/inflight registry entries, scheduler slots/KV, stream buffers and model-owned caches without invalidating active siblings. Preserve sender-held tensor lifetime and vocoder flush/EOS, including abort racing publish and chunks arriving after cleanup.

## Native checks by risk

| Change | Candidate native tests / evidence |
|---|---|
| Config precedence/path | `tests/unit_test/config/test_config_patch.py`, `test_config_path.py`, `test_config_resolver.py` |
| Schema/placement/process topology | `tests/unit_test/pipeline/test_runtime_schema.py`, `test_placement.py`, `test_replicas.py`; model colocation tests |
| Prepared request lifecycle | `tests/unit_test/scheduling/test_prepared_request_queue.py` |
| Stage streaming/abort and relay lifetime | `tests/unit_test/pipeline/test_stage_streaming.py`, `test_stage.py`, `test_comm_engine_ack.py`, `test_comm_router.py`; relevant `tests/unit_test/relay/` |
| Session batching/state | `tests/unit_test/scheduling/test_session.py`, `test_session_batch.py`, `test_session_gather_window.py` |
| Model adapter/quality | Model's `tests/unit_test/<family>/` request/config/pipeline/streaming tests, then selected `tests/test_model/` GPU cases and the model cookbook benchmark |

Inspect imports, fixtures and markers before executing. Unit-test directory names do not guarantee GPU-free or dependency-free execution. Do not replace unavailable torch/SGLang with stand-ins and report a native pass. These exact tests ran in the Creator's Windows Python 3.12 environment without new packages:

```bash
python -m pytest tests/unit_test/config/test_config_patch.py tests/unit_test/config/test_config_path.py tests/unit_test/config/test_config_resolver.py -q
python -m pytest tests/unit_test/scheduling/test_prepared_request_queue.py -q
```


Observed: 75 config tests passed; 9 prepared-queue tests passed. The attempted pipeline runtime-schema command could not collect because `pytest_asyncio` was absent. Torch, SGLang, ZMQ, msgpack and msgspec were also absent, so runtime/transport/model tests and serving were not claimed. These results test the pinned native contracts, not acceptance by AREX CLI or a performance win.

On a prepared target environment run the affected source-native suites plus one endpoint completion, streaming/abort/retry case, representative quality case and load point. Capture package versions, effective config, failure logs, output artifacts and coverage. If a test fails, reduce to the affected boundary and retain the failure; restore baseline before a new experiment. Source changes should also follow the upstream pre-commit guidance.

Pinned evidence:

- [docs/developer_reference/tts_model_integration.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/tts_model_integration.md)
- [sglang_omni/models/registry.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/models/registry.py)
- [sglang_omni/scheduling/message.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/message.py)
- [sglang_omni/scheduling/pipeline_state.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/pipeline_state.py)
- [sglang_omni/scheduling/prepared_request_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/prepared_request_queue.py)
- [sglang_omni/model_runner/sglang_model_runner.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/model_runner/sglang_model_runner.py)
- [tests/unit_test/config/test_config_resolver.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/tests/unit_test/config/test_config_resolver.py)
- [tests/unit_test/scheduling/test_prepared_request_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/tests/unit_test/scheduling/test_prepared_request_queue.py)
- [tests/README.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/tests/README.md)
