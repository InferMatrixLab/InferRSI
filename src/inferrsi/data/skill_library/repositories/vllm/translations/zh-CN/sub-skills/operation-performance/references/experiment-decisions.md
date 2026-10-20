# 实验决策

## 现象 → 假设 → 有界比较

| 观测 | 首个能区分假设的比较 | 关注及拒绝条件 |
|---|---|---|
| TTFT 高且队列增长 | 固定流量，改变准入/batch 工作量和长 prefill 上限；拆开排队与 prefill 时间 | 吞吐增加却使尾部 TTFT、饥饿或 HTTP 拒绝率恶化 |
| 长 prompt 到达时 ITL 差 | 相同混合流量下比较 chunked-prefill 预算 | chunk 变小使 prefill 过慢或调度开销主导 |
| 反复抢占 | 先比较更低 active sequence/token 上限，再看显存预算和真实上下文需求 | 重算与排队抵消容量收益；保持真实最大上下文需求 |
| 相似 prompt 仍昂贵 | 相同 tokenization/cache identity 下比较冷前缀和明确预热的前缀 | 命中率仍低；输出主导的负载很难获得 prefill 收益 |
| Decode 疑似带宽受限 | 比较兼容的 speculation 开关和小范围 draft 数 | 接受率下降、draft/verify 成本增加、质量变化或高峰吞吐下降 |
| 模型放不下或分布式扩展停滞 | 建立最小合法拓扑；按模型和互联比较 TP/PP，再看 DP/EP | 通信/不均衡主导、拓扑不支持或设备数量计算错误 |
| Prefill 影响尾部 ITL | 比较调优后的同实例基线与计入传输成本的 P/D | 网络/序列化/代理/排队抵消 SLO 收益或故障增多 |
| Launch/CPU 开销主导 | 同后端、相同预热 shape 下比较 compile/graph 模式 | 启动、capture 显存、重编译或未测 shape 失败超过预算 |
| 权重或 KV 显存受限 | 分别比较兼容的权重量化或 KV 量化 | 质量下降、scale/layout 不匹配、kernel 更慢或转换成本增加 |

这些是待验证假设，不是普遍有效的设置。同次比较保持请求语料、模型版本、tokenizer、生成设置和硬件分配一致。不能通过缩短输出或静默降低最大上下文宣称加速。

## 显存与缓存控制

当前源码声明 `gpu_memory_utilization=0.92`，并非普遍推荐值。它是每实例限制，不为共享设备的所有进程做全局预留。显式 `kv_cache_memory_bytes` 在 KV 定容时优先于 utilization；其他分配仍需考虑。记录 profiling/启动容量与真实显存峰值。增加 KV 可减少抢占，但可能挤占 graph、activation 或其他进程所需空间。[cache_config](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L102-L155) [cache_bytes](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L255-L272)

区分权重、KV 驻留、临时 activation、graph 和通信 buffer。简单 dense attention 估算仅作规划边界，不能保证 MLA、sliding-window、hybrid/state-space groups、量化 scales、复制或后端 padding 下的容量。使用实际每组 KV specification 和 profiling 分配。prefix 收益依赖 token 相同的可复用前缀；冷、暖状态分开测量。[kv_alloc](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/kv_cache_manager.py#L371-L470) [cache_match](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L74-L100)

## 并行与 P/D

TP 可降低单 rank 模型工作/显存，但增加 collective。PP 切分层并引入 stage 平衡和 pipeline 效应。DP 在资源允许时扩展 replica/请求容量。EP 面向 MoE，增加 dispatch/combine 通信，专家分布与 routing 偏斜很重要。PCP/DCP 是另有约束的上下文轴。计算 rank 或显存前，确认目标模型、后端和 launcher 支持。[parallel](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L139-L163) [ep](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L189-L233) [context_parallel](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L591-L629) [world_size](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L946-L965)

P/D 固定模型/tokenizer/dtype 与 KV layout 兼容性，统计传输字节和时延，测试请求关联、取消、延迟释放、远端错误与选定失败策略。该功能仍属实验性。启动前读具体 connector 的测试和文档；ExampleConnector 运行不能作为生产传输验证。[pd](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/disagg_prefill.md#L1-L33) [kv_transfer](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/kv_transfer.py#L56-L91) [connector_finish](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L371-L408)

## 投机、编译与量化

投机是依赖负载的 draft/verification 权衡。记录接受 token 数或接受长度、draft 时间、verify 时间、端到端输出速率和质量；同时包含低负载与饱和区间。synthetic acceptance 可描述指定接受率下成本，但不能用于准确性或真实模型加速结论。[spec_docs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/speculative_decoding/README.md#L1-L62) [synthetic](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/speculative.py#L529-L549)

以实际选中的 attention/量化 kernel 为实验对象。编译与 graph 可减少 host/launch 工作，同时改变启动、显存和 shape 敏感性。仅在诊断问题需要时比较 eager；它可能同时关闭多个机制，需说明混杂因素。量化必须使用支持的模型/checkpoint/backend 组合，并明确数值或任务质量容差。[attention](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/attention/selector.py#L105-L225) [graphs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/compilation.py#L610-L654) [quant_docs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/quantization/README.md#L25-L99)

## 恢复

OOM：区分权重加载、profiling、graph capture 或运行阶段；恢复最近正常设置，降低对应压力。反复抢占：先降低准入并发，不假设增大 token batch 会更好。prefix 命中低：检查 tokenization/template、adapter、多模态 hash 和 salt。传输停滞：检查 request ID、role、peer 就绪、完成/释放信号和策略。不支持 kernel：检查 selector 条件并选择支持的路径，保留故障而不掩盖。输出异常：先停性能比较，验证受影响语义。
