# 运行时契约与优化面

## 所有权与执行流

| 层 | 负责内容 | 首先检查的源码 |
|---|---|---|
| 流水线配置 / 拓扑 / 放置 | 逻辑阶段与路由、进程归属、副本、rank、显存预算 | `config/schema.py`、`config/topology.py`、`config/placement.py` |
| Coordinator | 准入、请求状态、固定的进程副本绑定、终端结果汇总、取消广播 | `pipeline/coordinator.py`、`pipeline/replicas.py` |
| Stage | IO、完整载荷汇聚、流式接收和输出路由、调度器生命周期 | `pipeline/stage/runtime.py`、`pipeline/stage/input.py` |
| Scheduler | 请求准备/批处理、inbox/outbox、计算循环、请求或会话生命周期 | `scheduling/message.py`、`simple_scheduler.py`、`session.py`、`omni_scheduler.py` |
| Worker / runner | SGLang 基础设施、模型 forward、采样/输出处理、模型专有 embedding/反馈 | `scheduling/bootstrap.py`、`model_runner/model_worker.py`、`model_runner/base.py` |
| Comm / relay | 本地性选择、载荷打包、张量移动、缓冲区生命周期/完成 | `comm/router.py`、`comm/engine.py`、`comm/stage_io.py`、`relay/` |

表中路径均位于 `sglang_omni/`。`StageScheduler` 包括 `inbox`、`outbox`、`warm_up_serving_thread`、`start`、`stop`、`abort`。入站消息包含新请求/数据块/完成/取消/admin；出站包含结果/流/错误/KV transfer/admitted。不要缩减成旧文档示意中的三种消息。

`OmniScheduler` 通过未绑定方法调用/委托组合上游 SGLang 调度行为，并非继承。它复用批处理与缓存机制，同时管理 Omni 请求和流式行为。`event_loop_overlap` 明确抛错，因为延迟更新 `Req.inflight_middle_chunks` 会破坏分块 prefill 的边界。已经实现的模型专有 async-decode 路径是另一种能力，不能据此认为 overlap 循环可用。`SimpleScheduler` 适用于普通计算/局部批处理，不提供 AR KV 调度；`SessionScheduler` 管理每个会话内有序操作，可对就绪会话进行批处理。流式 vocoder 必须正确累积、flush 并发出终端结果。

检查具体 DAG。Qwen3-Omni 预处理向编码器分发，请求相关的汇聚为 thinker/talker 准备输入；thinker 可向 talker 和 decode 发送流，talker 向 code2wav 发送 codec 数据块。文本和语音变体不同，不要假设所有变体都经过同一 `mm_aggregate`。Qwen3-TTS 的 preprocessing、engine、vocoder 默认归属 `pipeline` 进程；修改 `process` 会改变进程内准备状态能否共享。`PreparedRequestQueue` 在锁内管理 prepared/inflight/aborted 转换；准备期间取消会阻止后续 publish。

## 通信与生命周期

不存在公开的传输后端选择器。`CommRouter` 根据本地性、放置、平台和张量设备选择：

- 同进程且满足条件的载荷/数据块通过 Python 对象引用传递（`LOCAL_OBJECT`）。消费完成前，嵌套容器、张量和元数据均按只读处理。fan-out 的投影必须提供独立 `data` 容器；张量叶子可只读共享。
- 同一放置、CUDA ordinal 兼容的不同进程可直接使用 PyTorch CUDA IPC。所有权遵循 CUDA IPC storage 生命周期，此类 envelope 不使用 relay ACK。
- 其他满足条件的同节点 GPU 边使用平台的节点内传输（CUDA 上为 CUDA IPC 池，含可用性检查/回退）；主机边使用 SHM；配置为远端的跨节点边使用 Mooncake。存在 NCCL/NIXL 文件不代表可通过公开参数任意选择。
- relay 传输使用类型化 `DataRef`、张量打包和完成/ACK 跟踪。不能发送控制元数据后就释放发送缓冲区。等待基于 credit 的传输完成前先发布流式控制消息，使接收方能启动读取。
- 接收端 `StreamQueue` 无界；背压属于发送方/调度器边界。关闭请求会唤醒阻塞接收方；迟到块不能复活已取消状态。修改流控时一起检查 EOS、汇聚与清理。

## 带证据边界的搜索空间

| 候选方向 | 已有接口 | 约束 / 可观测决策 |
|---|---|---|
| 并发/准入 | engine 运行与排队上限、factory 请求构造并发、coordinator 容量 | 同时检查 503、排队和 p95/p99，不只看成功 QPS |
| KV/计算图 | engine 显存比例、token 上限、`kv_cache_bytes`、图/compile 字段 | `kv_cache_bytes` 与显存比例及 max-total-tokens 冲突；图增加显存/启动开销 |
| 阶段布局 | `process`、`gpu`、`tp_size`、阶段 GPU 比例；`processes` 副本/devices | TP 与进程副本不同；保持状态共享及每块 GPU 预算有效 |
| 同 GPU 容量 | 模型/平台允许时的 `mps` 与 `weight_share` | MPS 影响调度；权重共享减少不可变权重内存，不共享 KV/图/请求状态；不保证吞吐提升 |
| 流式延迟 | 模型专有分块、部分启动、vocoder 批处理/异步参数 | 核对真实工厂；一起测首音频、连续性和质量，不虚构全局 chunk 参数 |
| 精度/媒体处理 | 受支持的 engine 量化、模型媒体预处理 | 需要模型/后端支持并比较质量；降低视频 FPS 会改变负载与质量 |
| 新调度/传输策略 | 代码扩展 | 保持状态和传输契约；不虚构参数或承诺加速 |

固定版本证据：

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
