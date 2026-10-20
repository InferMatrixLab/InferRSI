# 扩展与验证契约

## 修改前确定职责归属

| 变更 | 主要归属 | 需要保持的契约 |
|---|---|---|
| 新模型分解 | 模型 `pipeline.py`、registry、输入处理器、默认部署 | 阶段身份、支持模态、条件输入/权重语义 |
| 放置/副本生命周期 | stage runtime、pool、membership、client | 就绪、亲和性、存活、故障传播、幂等关闭 |
| 跨阶段推进 | orchestrator | 请求/片段身份、阶段完成、取消和上下游顺序 |
| 载荷传输 | OmniConnector、transfer adapter | 形状/dtype/设备、生命周期、接收 deadline、消费确认和清理 |
| 扩散单步接入 | 协议、runner、每请求 step state | 只准备一次、独立 RNG/latent/scheduler、最终解码、取消/释放 |
| 输出表示 | output modality、payload、accumulation | 字段语义、delta/快照区别、拼接轴、终态输出 |

`OutputModality.from_string` 接受小写标准值 `text`、`image`、`audio`、`latent`、`token_ids` 及 `+`/`,` 组合；`None` 默认为 text。`wav`、`speech`、`tokens` 等别名、空白、大小写变体及空字符串会失败。此引擎输出枚举不接受 `video`，视频服务有自己的媒体契约。token ID 与连续 latent 语义不同，历史生产者的特殊契约需单独核对。音频默认沿最后一维拼接；image/latent/token-ID 默认沿第 0 维拼接；具名条件快照可用 REPLACE 覆盖，因此重命名字段可能悄悄改变累积行为。

传输成功应表示消费者能够安全使用数据，不能仅表示发送已入队。不能通过释放源缓冲区来取消进行中的 DMA 读取。deadline/失败/取消路径必须按正确归属清理记录和资源，同时测试竞态与稳态。

## 原生测试命令

在固定提交源码根目录、匹配的开发环境下执行。以下是选定验证配方，不是本地已运行的结论：

```bash
python -m pytest tests/config/test_config_merge.py tests/config/test_pipeline_registry.py -q
python -m pytest tests/engine/test_output_modality.py tests/engine/test_multimodal_accumulation.py -q
python -m pytest tests/engine/test_orchestrator_error_handling.py tests/engine/test_async_omni_engine_abort.py -q
python -m pytest tests/diffusion/test_diffusion_step_pipeline.py tests/diffusion/test_step_request_lifecycle.py -q
python -m pytest tests/distributed/omni_connectors/test_chunk_transfer_adapter.py tests/distributed/omni_connectors/test_shm_connector.py -q
```

测试树会加载包级 fixture，标记 CPU 不代表只需标准库。真实 RDMA/原生 connector 测试还需要对应硬件/服务；按变更组件选择模型/后端测试，再验证真实 checkpoint 请求。

## 验证顺序和观察项

1. **源码/静态**：检查字段及调用方、配置可解析性和能力组合，提前拒绝在 YAML 中任意定义拓扑或不兼容模式。
2. **契约**：执行受影响的 parser/output/merge/runner 测试，包含无效输入和取消；假 tensor/transport 只证明其模拟的行为。
3. **必需后端**：在目标部署运行 GPU/加速器 kernel、图 capture/replay、原生传输和多 rank 一致性；不可用则记 `BLOCKED_REQUIRED_BACKEND`。
4. **真实模型**：比较单/多请求、流式/非流式输出；验证 prompt/conditioning 隔离、带数值容差的确定性、任务质量、音频文本一致性/连续性、视频时序/质量，以及取消/重复请求后资源不持续增长。
5. **性能**：前述门槛通过后做同条件重复测量；保留错误和质量失败，保证编译缓存、预热、负载及实际后端可比。

本包本地探针通过文件路径加载真实、仅依赖标准库的输出枚举，检查有效/无效字符串、保留集合及累积规则，并解析具体部署 YAML。它没有导入完整引擎、执行该引擎 pytest 套件、验证完整配置合并或运行 GPU 推理。该窄范围检查可发现指南漂移，不能认证引擎。

参见[源码证据](../../../references/evidence.md)与[服务恢复步骤](../../omni-serving/references/serving.md)。
