# 内存与 KV 管理：先复用回收任务，再增加分配任务

**任务例子：给定请求结束、保存完成和写入完成事件，Agent 改进待回收队列，既不能提前释放块，也不能遗漏已经可以释放的块。**

当前状态：设计候选；本次只调查和说明来源，没有新增执行、硬件资格或收益证据。

## 放在现有 SearchSpace 的哪里

引用既有 [SearchSpace Matrix](../../../searchspace-matrix.md) 的资源与生命周期说明：队列元数据和 CPU 管理开销属于 host 侧；实际设备 KV 容量属于相应加速器资源。这里不创建另一份权威分类，也不因加入任务而提升矩阵成熟度。

先区分三个问题：回收逻辑是否正确、管理操作是否更快、真实模型的显存/容量是否改善。CPU 任务只能直接回答前两者；第三个问题需要目标设备和模型实验。

## 已有基础与固定来源

| 来源 | 可复用内容与身份 |
| --- | --- |
| InferRSI 既有 KV 任务 | [资格说明](../../../kv-reclamation-qualification.md)、[可见契约](../../../../evidence/kv-reclamation-20261030/validator/independent/CONTRACT.md)和[原始证据](../../../../evidence/kv-reclamation-20261030/README.md)；属于既有 #248 工作，不算本次新造题 |
| vLLM | commit `af261bab7f717b6ece30f5ed3213c43974e4a6c4`；[Apache-2.0](https://github.com/vllm-project/vllm/blob/af261bab7f717b6ece30f5ed3213c43974e4a6c4/LICENSE)；[BlockPool](https://github.com/vllm-project/vllm/blob/af261bab7f717b6ece30f5ed3213c43974e4a6c4/vllm/v1/core/block_pool.py)、[延迟回收测试](https://github.com/vllm-project/vllm/blob/af261bab7f717b6ece30f5ed3213c43974e4a6c4/tests/v1/core/test_deferred_block_free.py)提供后续真实语义参考 |
| Mooncake | commit `e5ef0e427a49cd2f8ad5b4356b09435095030439`；[Apache-2.0](https://github.com/kvcache-ai/Mooncake/blob/e5ef0e427a49cd2f8ad5b4356b09435095030439/LICENSE-APACHE)；[分配 benchmark](https://github.com/kvcache-ai/Mooncake/blob/e5ef0e427a49cd2f8ad5b4356b09435095030439/mooncake-store/benchmarks/README.md)与[正确性测试](https://github.com/kvcache-ai/Mooncake/blob/e5ef0e427a49cd2f8ad5b4356b09435095030439/mooncake-store/tests/offset_allocator_test.cpp)是下一道实际新题候选 |

既有 KV verifier 的冻结文件 SHA-256 为 `163c21134a8155da2a6469d9dbddb6ea71cb162e14f53e1c4266fe8ce75126f7`。任务、工作负载、补充 oracle 和数值计划各有原记录；复用时逐项检查身份，不能重新解释或改写冻结字节。

历史本地隔离不可用，留存结果为 **INCONCLUSIVE**。可信控制直接导入通过与隔离回放是不同证据；之后的新环境结果要另存，不能覆盖旧结果或倒推旧环境通过。

## 第一阶段：复用既有合成 KV 回收题

- Agent 只修改 `candidate.py` 的 `Reclaimer`；输入事件、oracle、grader 和工作负载受保护。
- 实现 `apply(event)` 和 `pending()`，保留事件结构校验、请求 generation、重复通知幂等性、无效输入原子性及确定的返回顺序。
- 回收要求 finish、所需 save_complete 和 processed frontier 三项条件同时满足；允许优化查找与排队数据结构，不允许跳过事件或缓存预定答案。
- **既有题明确不含共享块、引用计数、前缀匹配、取消、超时、真实线程/异步执行、字节内容或资源容量策略。** 不能借 vLLM 来源把这些写成已覆盖功能。
- 它是围绕特定知识机制构造的合成近迁移任务，不是历史缺陷复现、自然抽样 holdout，也不是 vLLM 兼容性测试。

正确性沿用独立 temporal oracle，逐事件核对回收列表和 pending 状态；原有非法输入、generation 重用、提前释放等控制保持原身份。

现有计时是宿主测得的**整条 CPU 任务命令耗时**，包括解释器和 sandbox 启动；不能改称核心队列延迟或显存收益。若另测核心操作，应建立新版本边界和独立资格记录。

Profiling 单独分析可信控制的扫描、索引和队列开销，不混入计时，不推断设备 timeline。真实生产者和不可信产物的权限边界仍按原入口处理。

## 第二阶段：Mooncake 混合尺寸分配题

任务例子：固定内存池容量和 allocate/free 请求序列，改进分配器，使分配更快或更少因碎片失败，同时保持请求完成量和正确的容量不足语义，不发生越界或重叠。

- 借鉴 `allocation_strategy_bench` 的 `size_class_churn`、容量预填充和尺寸分布；Agent 修改 allocator/placement 数据结构，不能改请求序列、容量、统计或副本要求。
- 正确性独立检查地址范围、活动分配不重叠、分配大小、释放恢复和容量守恒；不能靠拒绝困难请求或返回部分副本来获得速度优势。
- 分别记录完整/部分/失败分配、碎片率、延迟分布和完成量；先定义质量/容量约束，再评价速度，不能只报最快的一项。
- CPU profiling 查分配、锁和数据结构开销；实际 RSS、设备显存、RDMA 和端到端 KV 命中收益都是不同实验。
- 上游 [CMake target](https://github.com/kvcache-ai/Mooncake/blob/e5ef0e427a49cd2f8ad5b4356b09435095030439/mooncake-store/benchmarks/CMakeLists.txt)链接 `mooncake_store`、cachelib allocator、gflags/glog 等；尚未验证可独立构建，不能承诺零依赖或跨平台立即可跑。

## 怎样接入 InferRSI

先复用 [现有 KV 资格入口](../../../../tools/qualify_kv_reclamation.py)及其独立 oracle/隔离回放，不新建另一套 KV runner。它不是当前 `numpy-axis1-v2` 的一种 operation，也未因列入本文就接上新的正式两臂 adapter。

Mooncake 待构建和测量资格明确后，用目标拥有的脚本输出结构化结果，接既有 RunSpec/Workbench；质量脚本和候选分开冻结。不能直接把不可信 C++/Python 交给可信执行入口。

若比较 skill/Agent，另固定模型、预算和任务条件，保留两边真实产物及全部尝试；已有合成控制不能证明 skill 收益。

## 最小资格实验与采用理由

1. KV：核对原冻结身份，在合格 Linux 隔离环境执行既有正/负控制与同码对照，保存新的完整 receipt；历史 INCONCLUSIVE 保持原样。
2. Mooncake：先证明最小 target 可构建，再固定小规模混合分配 trace，用简单独立区间模型拒绝越界、重叠、漏释放和部分分配伪成功。
3. 性能：固定容量、预填充、请求量和环境，先检验同码对照；正确但测量不可分辨时保持证据不足，不选速度赢家。
4. 设备外推：只有实际模型/设备上的容量、质量和性能验收，才能补充显存或服务结论。

采用顺序是“复用已有 KV → 资格验证 Mooncake 新题”，因为两者有具体可改对象和明确正确性义务。暂不直接引入完整分布式 KV 服务：部署、网络、模型和存储因素太多，难以在硬件未定时隔离单次改动。
