# 运行路径与不变量

## V1 的一次迭代

实际 `EngineCore.step` 调用 `scheduler.schedule`，提交 `execute_model`，必要时采样，处理执行期间到达的取消，再调用 `update_from_output`。邻近的 batch-queue 路径涉及异步重叠时也必须检查。前端 → engine → scheduler → runner 是有用的概念图，但改动必须沿实际选中的 executor 和 model runner 追踪。[engine](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/engine/core.py#L657-L687)

调度器以 `num_tokens_with_spec` 和 `num_computed_tokens` 之间的未完成工作建模，并非两套分离的 prefill/decode 调度器。prompt、已生成和 draft tokens 参与计数。本快照中，`token_budget` 来自 `max_num_scheduled_tokens`，`input_budget` 来自 `max_num_batched_tokens`；drafting 还预留额外槽位。output placeholders 也影响未完成工作。启用投机或异步执行时，不能只用一个 token 数表示批容量。[sched](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/sched/scheduler.py#L591-L628) [budget](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/sched/scheduler.py#L703-L721)

`max_num_seqs` 决定 runner 容量；`max_num_active_seqs` 可降低 RUNNING 准入而不缩小 runner/graph 容量。`max_num_queued_reqs` 则限制 API server 所路由的全部 DP rank 上的在途请求。它们解决不同问题。dataclass 默认值明确用于测试便利，可能被 EngineArgs 设置。[sched_config](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/scheduler.py#L48-L103)

调度还依赖 KV 分配。分配失败可能抢占运行请求，但 connector 延迟释放的块不能视为立即可复用。priority 与 FCFS 的受害请求选择不同。末尾检查已调度 token、非负 token/input 预算及准入上限。修改策略必须保留这些约束并确保显存压力下仍能前进。[preempt](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/sched/scheduler.py#L775-L857) [invariants](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/sched/scheduler.py#L1403-L1415)

## KV 分配、身份和生命周期

`KVCacheManager` 协调 cache groups、前缀查找和分配；`BlockPool` 管理物理块复用与引用计数。cache hit 不等于空闲显存：touch 可复用块时，必要时将其移出淘汰队列并增加引用。请求释放后仅当引用降为零才能将块返还 free queue，null block 特殊处理。共享缓存内容和可写尾块要分别推理。[kv_hit](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/kv_cache_manager.py#L249-L321) [kv_alloc](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/kv_cache_manager.py#L371-L470) [kv_lifetime](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/block_pool.py#L666-L795)

前缀身份包括父前缀、tokens，以及 LoRA 身份、多模态内容、cache salt 等 extra hashes。文本相似不等于缓存等价。salt 可把复用限制在信任组。默认 SHA-256 使用 Pickle 序列化；`sha256_cbor` 使用 canonical CBOR 以支持跨环境复现。权重等语义输入改变时必须失效对应缓存。[prefix](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/design/prefix_caching.md#L15-L31) [salt](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/design/prefix_caching.md#L84-L100)

不能把旧设计说明中的“full blocks”泛化到当前所有物理 KV group。`prefix_match_unit` 控制 hash/匹配粒度，可以小于物理块，但必须整除 group 的 block size。对 hybrid Mamba，细粒度匹配本身不会保存中间状态。共享前缀 checkpoint 另有条件：prefix cache、Mamba EAGLE/MTP、更细 match unit、无 multi-module MTP；需检查所选模型与 group 实现。[cache_match](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L74-L100) [hybrid](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/automatic_prefix_caching.md#L15-L38)

## 分页 KV 与实际 attention kernel

分页存储把逻辑 token 位置映射到物理 KV 块；所选 kernel 必须遵守布局、block table、query 长度和支持的 dtype。仓库旧 PagedAttention 设计文档已明确警告不再描述当前代码，仅可用于历史概念理解。[paged_history](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/design/paged_attention.md#L1-L13)

当前 `get_attn_backend` 根据 head size、模型/KV dtype、指定 block size、MLA/sparse/sliding-window、KV transfer、context parallel 等能力构造选择条件，再交给 platform；还支持按 cache kind 覆盖。代码树存在某个 kernel 不代表本模型使用它。优化历史 CUDA kernel 前，应验证启动选择并 profile 实际路径。[attention](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/attention/selector.py#L105-L225)

## 并行与传输所有权

TP 切分张量计算，PP 切分 stage，DP 复制并路由请求，EP 对 MoE 层分布专家而非做张量切分。当前 PCP 增加进程轴；普通非 external-launcher 拓扑每个 DP replica 为 TP × PCP × PP。配置另有 external launcher 处理，需核对 rank 计算而非盲目相乘。PCP=1 时 DCP 复用 TP ranks，要求 TP 可整除 DCP；启用 PCP 后 DCP 限于 1、PCP 或 TP×PCP。MoE sharding 也涉及 TP×PCP×DP。[parallel](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L139-L163) [world_size](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L946-L965) [context_parallel](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L591-L629) [ep](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L189-L233)

P/D 分离在不同实例运行 prefill/decode，通过 connector 传递 KV。scheduler hooks 规划匹配 token、分配和 metadata；worker hooks 启动 load/save 并同步传输。异步传输完成前，request completion 可能仍不能释放块。保持 token/model/layout 一致，并遵循具体 connector 兼容矩阵。`kv_load_failure_policy` 当前区分默认 `fail` 和 `recompute`；回退必须有意配置且可观测。[pd](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/disagg_prefill.md#L1-L33) [connector](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L1-L41) [connector_finish](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L371-L408) [kv_transfer](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/kv_transfer.py#L56-L91)
