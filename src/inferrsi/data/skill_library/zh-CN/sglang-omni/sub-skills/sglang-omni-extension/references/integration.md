# 集成与测试映射

## 新增最小模型适配器

确定权重 architecture 和匹配的调度模式。模型 `config.py` 导出 `EntryClass`；`models/registry.py` 发现流水线类/architecture alias 并报告导入问题。模型缺失可能是依赖导入失败。需要时，在 SGLang model-runner 集成中注册真实 AR architecture；流水线发现与模型执行注册是不同层。

拓扑放在配置类中，通过类型化的 stage/engine/factory 字段开放已有阶段的覆盖。动态路由/wait 函数只能选择已声明静态边的子集。验证唯一普通路由选择（`next` 或 terminal）、真实阶段名、入口/终端行为、进程归属、TP rank 放置及预算。定义 YAML 键不等于实现工厂参数。

在 request builder 中规范化 API 请求，并区分显式采样参数与接口默认值。用类型化载荷/状态保留参考输入和 usage/finish reason。GPU 工厂使用仓库的设备解析器，不硬编码 CUDA 后宣称支持其他后端。模型采用 SGLang AR 时优先使用共享 engine builder/bootstrap；模型专有 forward 预处理/反馈留在 runner。跨阶段反馈需要明确的传输/状态设计，不能仅靠 runner hook。

状态所有权是适配器契约的一部分。进程本地 prepared/reference cache 不能静默变成跨进程状态。取消时要清理 prepared/inflight 注册项、调度槽/KV、流缓冲和模型自有 cache，同时不能破坏仍活跃的其他请求。保持发送方张量生命周期和 vocoder flush/EOS，覆盖取消与 publish 竞态，以及清理后的迟到块。

## 按风险选择原生检查

| 改动 | 原生候选测试 / 证据 |
|---|---|
| 配置优先级/路径 | `tests/unit_test/config/test_config_patch.py`、`test_config_path.py`、`test_config_resolver.py` |
| schema/放置/进程拓扑 | `tests/unit_test/pipeline/test_runtime_schema.py`、`test_placement.py`、`test_replicas.py`；模型 colocation 测试 |
| prepared 请求生命周期 | `tests/unit_test/scheduling/test_prepared_request_queue.py` |
| 阶段流式/取消与 relay 生命周期 | `tests/unit_test/pipeline/test_stage_streaming.py`、`test_stage.py`、`test_comm_engine_ack.py`、`test_comm_router.py`；相关 `tests/unit_test/relay/` |
| 会话批处理/状态 | `tests/unit_test/scheduling/test_session.py`、`test_session_batch.py`、`test_session_gather_window.py` |
| 模型适配/质量 | 对应 `tests/unit_test/<family>/` 的请求/配置/流水线/流式测试，再选 `tests/test_model/` GPU 用例和模型 cookbook 基准 |

运行前检查 import、fixture 和 marker。目录名含 unit_test 不保证无需 GPU 或依赖。不要替换缺失 torch/SGLang 为替身后宣称原生通过。以下确切测试在 Creator 的 Windows Python 3.12 环境中运行，未安装新包：

```bash
python -m pytest tests/unit_test/config/test_config_patch.py tests/unit_test/config/test_config_path.py tests/unit_test/config/test_config_resolver.py -q
python -m pytest tests/unit_test/scheduling/test_prepared_request_queue.py -q
```


结果：75 项配置测试通过，9 项 prepared queue 测试通过。尝试的 pipeline runtime-schema 命令因缺少 `pytest_asyncio` 无法收集。环境也缺少 torch、SGLang、ZMQ、msgpack、msgspec，因此不声称已验证运行时/传输/模型测试或服务。这些结果覆盖固定版本原生契约，不代表 AREX CLI 验收或性能收益。

在准备完备的目标环境中，运行受影响的原生测试，并覆盖一个接口完整返回、流式/取消/重试场景、代表性质量样本和负载点。保存包版本、最终配置、失败日志、输出产物和覆盖情况。测试失败时缩小到受影响边界并保留失败记录，新实验前恢复基线。源码修改还应遵循上游 pre-commit 约定。

固定版本证据：

- [docs/developer_reference/tts_model_integration.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/tts_model_integration.md)
- [sglang_omni/models/registry.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/models/registry.py)
- [sglang_omni/scheduling/message.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/message.py)
- [sglang_omni/scheduling/pipeline_state.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/pipeline_state.py)
- [sglang_omni/scheduling/prepared_request_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/scheduling/prepared_request_queue.py)
- [sglang_omni/model_runner/sglang_model_runner.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/model_runner/sglang_model_runner.py)
- [tests/unit_test/config/test_config_resolver.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/tests/unit_test/config/test_config_resolver.py)
- [tests/unit_test/scheduling/test_prepared_request_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/tests/unit_test/scheduling/test_prepared_request_queue.py)
- [tests/README.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/tests/README.md)
