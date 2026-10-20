# 架构与内存

调度、KV 压力、前缀复用、分块或投机问题时读取。证据编号链接到[固定源码映射](source-map.md)。本参考描述已检查的快照，不保证其他版本兼容。

## 跟踪一个请求

| 边界 | 检查位置 | 观测与不变量 |
|---|---|---|
| HTTP/Engine → TokenizerManager | `entrypoints/engine.py`、`managers/tokenizer_manager.py` | 请求身份、token ID、采样、多模态展开；固定 prompt/tokenizer 版本。Engine 说明三进程流程。[E01](source-map.md#e01) |
| Scheduler 准入 | `event_loop_normal`、`event_loop_overlap`、`get_next_batch_to_run`、`schedule_policy.PrefillAdder` | 区分排队与已准入请求；可用 token 预算和 prefill 分块。重叠模式会围绕当前 GPU 工作处理上一批结果，因此对象生命周期和 barrier 很关键。[E02](source-map.md#e02)、[E03](source-map.md#e03) |
| 构建前向 | `TpModelWorker.forward_batch_generation` | `ScheduleBatch` 转为 `ForwardBatch`，携带 HiCache 消费顺序并进入 `ModelRunner.forward`。调度结构不等于 GPU 张量布局。[E04](source-map.md#e04) |
| 模型/后端 | `ModelRunner._forward_raw` | 区分图重放、注意力规划以及 extend/decode/verify/split 模式。后端必须支持实际模式和布局。[E05](source-map.md#e05) |
| 结果/完成 | Scheduler 结果处理 → DetokenizerManager → TokenizerManager | 流式文本和结束原因；在正确完成边界释放请求锁/槽位，包含取消和回撤。[E01](source-map.md#e01)、[E02](source-map.md#e02) |

尾延迟事件中，先定位时间花在哪条路径再调整 batch size。长队列、长 prefill 和 KV 传输停滞需要不同处理。这是诊断流程，不是对当前瓶颈的断言。

## 内存具有多个层次

源码区分 `allocation.py`（批次分配）、`allocator/`（空闲槽位）、`pool/`（物理 KV/SSM 张量）、`hybrid_cache/`（层到池路由）、`pool_host/`（主机副本）及 `storage/`（L3 字节）。Radix cache 决定保留内容，不等同分配器。构建由 `kv_cache_configurator.py` 和 `kv_cache_builder.py` 等负责。[E06](source-map.md#e06)

可将 dense KV 字节数粗估为：tokens × layers × 本地 KV heads × head dimension × 2(K,V) × 元素字节，再考虑真实分片/复制、page padding、元数据、workspace 和图池。这是推导出的规划估计，不是分配器实际公式；MLA、量化 KV、SWA 和 Mamba 必须使用真实布局。设定容量前读取选中的 pool 和 builder。

普通 RadixCache 匹配最长、按 page 对齐的前缀。`RadixKey.extra_key` 提供额外命名空间；相同 token ID 但不同 extra key 不共享。活动引用计数使节点在 protected/evictable 计数间移动，驱逐释放物理 segment。修改时保持 page 对齐、节点拆分元数据、锁平衡和命名空间身份。[E07](source-map.md#e07)、[E08](source-map.md#e08)

UnifiedRadixCache 将逻辑 tree/core 与组件、controller I/O 分离。Full、SWA、Mamba 组件分别持有设备/主机状态和锁。有效前缀边界要求所有相关组件校验通过；Mamba 状态可能需要写时复制，SWA 有效性依赖窗口。旧说明写“HiRadixTree”时，应以当前组件/controller 源码为实现依据。[E09](source-map.md#e09)

## HiCache

L1 GPU 与 L2 主机缓存属于单个推理实例。增大主机缓存不会汇聚其他节点的内存。只有后端、命名空间和存储配置提供共享范围时，L3 才能跨实例复用。局部匹配查找可复用前缀，主机/存储数据必须在消费前恢复，backup/prefetch 策略在传输工作与重计算之间权衡。[E09](source-map.md#e09)、[E10](source-map.md#e10)

现有控制项包括 `--enable-hierarchical-cache`、`--hicache-ratio`、`--hicache-size`、`--hicache-host-memory-mode`、`--hicache-write-policy`、`--hicache-storage-backend`。显式 host size 覆盖 ratio。`buffer_only` 将主机内存作为 staging，且需要存储后端。主机容量与 rank/进程拓扑有关；增大前检查实际解析容量和 cgroup 约束。[E11](source-map.md#e11)

分别检查前缀匹配长度、设备/主机/存储命中、预取等待、传输字节/时间、主机容量，以及 protected/evictable 空间。若传输或等待成本超过节约的 prefill，即使命中率增加，TTFT 仍可能变差。这应作为目标负载上的待验证假设。

## 准入、分块与投机

| 现有控制项 | 源码含义 | 需要测量的权衡 |
|---|---|---|
| `--mem-fraction-static` | 权重与 KV 静态分配比例 | KV 容量与 activation/workspace/图余量 |
| `--max-running-requests` | 同时准入请求上限 | 饱和程度与排队/KV 压力 |
| `--chunked-prefill-size` | 单个 prefill chunk 最大 token 数；`-1` 禁用分块 | 长 prefill 干扰与额外调度/launch 工作 |
| `--max-prefill-tokens` | 带源码 context-length 规则的 prefill batch token 边界 | prefill 效率、workspace 与 decode 延迟 |
| `--schedule-policy` | 从源码选项中选择调度策略 | 前缀局部性、公平性与排队延迟 |

这些是声明含义，不是通用推荐值。默认/解析值随模型、后端、拓扑变化。Scheduler 不会把未结束 chunk 按普通 prefill 合入 running batch。需显式测试最终 chunk 和取消路径。[E12](source-map.md#e12)、[E03](source-map.md#e03)

投机解码包含算法、兼容的 draft/target 状态、draft steps/token 预算和验证路径。`--speculative-algorithm`、`--speculative-draft-model-path`、`--speculative-num-steps`、`--speculative-eagle-topk`、`--speculative-num-draft-tokens` 是不同控制项。必须读取算法专属字段和兼容性钩子，不能从参数名推断 draft 可任意互换。[E13](source-map.md#e13)

测量每次 target 验证接受的 token、接受分布、draft 工作、verify 成本、图覆盖和内存，再看端到端延迟/吞吐。高接受率本身不能证明加速。按目标采样方式以及 cache-hit/分块情形验证基线等价性；改变接受/验证逻辑的研究扩展必须提出明确正确性论证。

## 恢复矩阵

| 症状 | 下一项区分检查 | 恢复 |
|---|---|---|
| 启动/capture OOM | 权重、静态 KV、图/workspace 峰值、拓扑 | 降低相关预算，恢复受支持基线，保留启动日志 |
| 仅负载下 OOM/回撤 | 并发长上下文、受保护 page、准入 | 降低准入工作量，检查清理和压力，不关闭不变量检查 |
| 命中缓存后输出损坏 | 命名空间/token ID、部分 page、组件状态、锁生命周期 | 比较 cold/hit logits，性能实验前缩小 restore/evict 序列 |
| HiCache 命中但 TTFT 高 | L2/L3 传输及预取等待与节省计算之比 | 固定或关闭缓存策略比较相同 trace，保留后端错误 |
| chunk/投机回归 | 边界状态与 verify/reject 清理 | 恢复不分块/非投机基线，再逐一启用 |

具体门槛见[调优与验证](tuning-and-validation.md)。
