# Source evidence

All anchors use one immutable source commit.

| ID | Source | Supports |
|---|---|---|
| schema | [vllm_omni/config/stage_config.py:229–399](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/config/stage_config.py#L229-L399) | Frozen model topology |
| deploy | [vllm_omni/config/stage_config.py:399–674](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/config/stage_config.py#L399-L674) | Stage and pipeline deployment fields |
| merge | [vllm_omni/config/stage_config.py:1242–1325](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/config/stage_config.py#L1242-L1325) | Async edges and merge |
| orchestrator | [vllm_omni/engine/orchestrator.py:1–12](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/engine/orchestrator.py#L1-L12) | Cross-stage request progression |
| affinity | [vllm_omni/engine/stage_pool.py:465–509](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/engine/stage_pool.py#L465-L509) | Request replica affinity |
| transport | [vllm_omni/distributed/omni_connectors/connectors/base.py:12–103](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/distributed/omni_connectors/connectors/base.py#L12-L103) | Transfer and cleanup contract |
| qwen | [vllm_omni/model_executor/models/qwen3_omni/pipeline.py:22–84](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/model_executor/models/qwen3_omni/pipeline.py#L22-L84) | Thinker/Talker/Code2Wav topology |
| qwen-deploy | [vllm_omni/deploy/qwen3_omni_moe.yaml:1–102](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/deploy/qwen3_omni_moe.yaml#L1-L102) | Concrete stage/chunk budgets |
| steps | [vllm_omni/diffusion/models/interface.py:87–153](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/diffusion/models/interface.py#L87-L153) | Stateful diffusion step protocol |
| runner | [vllm_omni/diffusion/worker/diffusion_model_runner.py:772–813](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/diffusion/worker/diffusion_model_runner.py#L772-L813) | Request-batch capability check |
| modality | [vllm_omni/outputs/output_modality.py:15–178](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/outputs/output_modality.py#L15-L178) | Output types and accumulation |
| quickstart | [docs/getting_started/quickstart.md:1–114](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/getting_started/quickstart.md#L1-L114) | Pinned installation/serving recipe |
| modes | [docs/user_guide/diffusion/execution_modes.md:1–162](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/user_guide/diffusion/execution_modes.md#L1-L162) | Request/step/streaming limits |
| deps | [requirements/common.txt:1–26](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/requirements/common.txt#L1-L26) | Dependency constraints |
| package | [pyproject.toml:1–25](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/pyproject.toml#L1-L25) | Package metadata |
| cli | [vllm_omni/entrypoints/cli/main.py:12–72](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/entrypoints/cli/main.py#L12-L72) | Omni CLI dispatch |
| benchmark | [docs/cli/bench/serve.md:1–20](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/cli/bench/serve.md#L1-L20) | Omni benchmark help |
| metrics | [docs/design/architecture_overview.md:44–59](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/design/architecture_overview.md#L44-L59) | Modality-specific metrics |

Design documents marked draft or current-plus-in-flight are supporting context, not proof that every proposed invariant/feature is implemented. Where overview and detailed execution documentation diverge (for example H3 step execution), inspect the model protocol and runner at this SHA.
