# Source evidence / 源码证据

All anchors use one immutable source commit. / 所有锚点指向同一固定提交。

| ID | Source / 来源 | Supports / 用途 |
|---|---|---|
| schema | [vllm_omni/config/stage_config.py:229–399](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/config/stage_config.py#L229-L399) | Frozen model topology / 固定模型拓扑 |
| deploy | [vllm_omni/config/stage_config.py:399–674](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/config/stage_config.py#L399-L674) | Stage and pipeline deployment fields / 阶段与全局部署字段 |
| merge | [vllm_omni/config/stage_config.py:1242–1325](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/config/stage_config.py#L1242-L1325) | Async edges and merge / 异步边与配置合并 |
| orchestrator | [vllm_omni/engine/orchestrator.py:1–12](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/engine/orchestrator.py#L1-L12) | Cross-stage request progression / 跨阶段请求推进 |
| affinity | [vllm_omni/engine/stage_pool.py:465–509](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/engine/stage_pool.py#L465-L509) | Request replica affinity / 请求副本亲和性 |
| transport | [vllm_omni/distributed/omni_connectors/connectors/base.py:12–103](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/distributed/omni_connectors/connectors/base.py#L12-L103) | Transfer and cleanup contract / 传输与清理契约 |
| qwen | [vllm_omni/model_executor/models/qwen3_omni/pipeline.py:22–84](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/model_executor/models/qwen3_omni/pipeline.py#L22-L84) | Thinker/Talker/Code2Wav topology |
| qwen-deploy | [vllm_omni/deploy/qwen3_omni_moe.yaml:1–102](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/deploy/qwen3_omni_moe.yaml#L1-L102) | Concrete stage/chunk budgets / 阶段及分块配置 |
| steps | [vllm_omni/diffusion/models/interface.py:87–153](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/diffusion/models/interface.py#L87-L153) | Stateful diffusion step protocol / 扩散单步协议 |
| runner | [vllm_omni/diffusion/worker/diffusion_model_runner.py:772–813](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/diffusion/worker/diffusion_model_runner.py#L772-L813) | Request-batch capability check / 请求批处理能力检查 |
| modality | [vllm_omni/outputs/output_modality.py:15–178](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/outputs/output_modality.py#L15-L178) | Output types and accumulation / 输出类型与累积 |
| quickstart | [docs/getting_started/quickstart.md:1–114](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/getting_started/quickstart.md#L1-L114) | Pinned installation/serving recipe / 固定版本安装及服务入口 |
| modes | [docs/user_guide/diffusion/execution_modes.md:1–162](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/user_guide/diffusion/execution_modes.md#L1-L162) | Request/step/streaming limits / 执行模式边界 |
| deps | [requirements/common.txt:1–26](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/requirements/common.txt#L1-L26) | Dependency constraints / 依赖约束 |
| package | [pyproject.toml:1–25](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/pyproject.toml#L1-L25) | Package metadata / 包元数据 |
| cli | [vllm_omni/entrypoints/cli/main.py:12–72](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/vllm_omni/entrypoints/cli/main.py#L12-L72) | Omni CLI dispatch / Omni CLI 分派 |
| benchmark | [docs/cli/bench/serve.md:1–20](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/cli/bench/serve.md#L1-L20) | Omni benchmark help / Omni benchmark 帮助 |
| metrics | [docs/design/architecture_overview.md:44–59](https://github.com/vllm-project/vllm-omni/blob/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1/docs/design/architecture_overview.md#L44-L59) | Modality-specific metrics / 分模态指标 |

Design documents marked draft or current-plus-in-flight are supporting context, not proof that every proposed invariant/feature is implemented. Where overview and detailed execution documentation diverge (for example H3 step execution), inspect the model protocol and runner at this SHA.

标记 draft / current-plus-in-flight 的设计文档只作背景，不能把提议写成已实现。概览与详细执行文档不一致时（例如 H3 单步执行），核对该提交的模型协议和 runner。
