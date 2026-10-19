# 架构与受约束搜索

## 职责和执行流

`Omni` / `AsyncOmni` 及服务入口把公共请求映射到已注册流水线。模型代码通过 `PipelineConfig` 固定拓扑，部署数据选择资源，解析后得到阶段配置。orchestrator 推进请求；stage pool 负责副本选择与亲和性；client 连接执行阶段；阶段 scheduler/runner 管理本地工作；connector 传输数据并同步就绪状态；输出处理器组成最终结果。

Qwen3-Omni 可用作具体追踪：Thinker → Talker → Code2Wav，依次涉及文本/条件、codec token、波形块。本提交阶段 0/1 声明 `latent`，阶段 2 为 `audio`；不能仅凭 dtype 重新解释历史 latent 载荷。扩散模型即使内部含文本编码、denoiser 和 VAE，也可能只是一个注册阶段；这些是可测量的组件阶段，不自动等于独立部署阶段。

## 搜索维度

E = 已有字段/能力；I = 实现修改；R = 研究扩展。E 仍需核对模型/后端支持。

| 维度 | 类别及源码接口 | 耦合与合法性 | 测量/门槛 |
|---|---|---|---|
| 阶段放置/副本 | E：`devices`、`num_replicas` | 阶段身份固定；同卡共享容量；保持状态亲和性 | 各阶段队列/利用率、端到端 p95、显存与清理 |
| 拓扑拆分/融合 | I：注册 `PipelineConfig` 变体 | 保留权重、输入、处理器和终态输出；传输可能超过节省的计算 | 参考输出、传输开销、启动与故障隔离 |
| AR 调度 | E：`max_num_seqs`、`max_num_batched_tokens`、`max_model_len`、异步调度 | KV 容量、prefill 大小、下游容量共同约束准入 | TTFT、TPOT、p95、饥饿和内存上界 |
| 分块重叠 | E：`async_chunk`、受支持 connector 的分块字段 | 模型上下文和边界语义限制块大小；等待中的状态仍占资源 | 首音频包、块间隙、RTF、接缝与取消 |
| 活跃流窗口 | E：`active_stream_window` | 下游容量策略，不是任意音频长度参数 | 公平性、停滞流、首包长尾 |
| runner/计算图 | E（限受支持路径）：`model_runner`、`enforce_eager`、编译配置 | 模型/数据面兼容、形状和图显存；不能假设 v1/v2 任意互换 | eager 一致性、capture/replay、冷/热耗时 |
| 扩散请求批处理 | E：容量及受支持的请求批处理 | 形状、guidance、输出数量、LoRA 要兼容；流水线须声明支持 | 请求输出/RNG 隔离、延迟与吞吐 |
| 扩散单步调度 | E：`step_execution`；I：实现单步协议 | `prepare_encode`、`denoise_step`、`step_scheduler`、`post_decode`；单请求支持不等于批处理支持 | 单步一致性、取消边界、状态清理 |
| 媒体流式输出 | E：仅限可输出中间结果的流水线 | 单步执行不保证中间输出；只产终态的模型仍只产终态 | 首个可用媒体包、块顺序/重复、最终覆盖 |
| 并行执行 | E（依模型）：TP、EP、Ulysses/ring/allgather、CFG、VAE patch、HSDP | 模型布局整除、rank group、互联拓扑及内存 | 集合通信正确性、扩展性、通信量及质量 |
| 卸载/加载 | E：CPU/layerwise/DLO/host-weight 配置 | 主存、pinned 生命周期、互联带宽、组件常驻和量化兼容 | GPU/主存峰值、传输停顿、加载与推理耗时 |
| 缓存/精度 | E：限兼容模型/后端 | AR KV/prefix cache 与近似扩散复用不同；dtype/量化可能改变输出 | 命中收益及严格或模型特定的质量容差 |
| 新调度/传输算法 | I/R：coordinator、pool、connector | 编码前明确策略/传输边界、故障语义、状态归属 | 压力/取消/rank 丢失、泄漏及同条件 A/B |

## 约束和目标

每个设备都需满足实测峰值：权重 + KV/状态 + activation + 通信/workspace + 图内存 + 余量 ≤ 可用显存。utilization 比例相加仅是规划提示，启动顺序、可用内存和实际分配会影响结果；还需约束主存、网络/PCIe 带宽和队列稳定性。

先过质量和正确性门槛，再在 p95 首输出、p95 端到端延迟、吞吐、内存和成本上取可行 Pareto 前沿。音频 RTF = 处理墙钟时间 / 生成音频时长，必须说明是否包含排队/传输；文本一致性、音色和连续性与延迟分开评估。视频固定时长/FPS/分辨率，并检查时序一致性及感知/任务质量。

搜索顺序：受支持串行基线 → 排除内存不可行组合 → 分阶段定位计算/传输瓶颈 → 小范围已有参数搜索 → 检查交互项 → 再考虑实现/算法变更。不能把降低媒体质量或减少工作量算作无代价的执行优化。

## 依据

参见[证据索引的 schema、deploy、merge、orchestrator、affinity、transport、qwen、steps、runner 和 modes](../../../references/evidence.md)。搜索表是据这些接口形成的工程归纳，不代表上游保证所有组合可用。
