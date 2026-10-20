# 五个推理仓库的双语 Skill 知识包

这份产物把五个官方仓库的固定源码快照整理成**可操作知识**：从哪里查、哪些可以改、变量之间如何耦合、什么会破坏正确性，以及如何验证优化。英文和中文都是完整版本，不只是翻译标题。

最值得抽取的共性是：先按**工作单位、状态归属、调度、内存、通信、验证**组织知识，再映射到具体引擎。vLLM 和 SGLang 提供了深入的 token 执行与服务实现；两个 Omni 仓库进一步处理模型特定的阶段组合和异构输出生命周期。Strata 进一步提供异构 MoE 专家放置、内存与推测执行知识。它们的能力存在交集，具体支持路径需按提交确认。

## 阅读入口

| 仓库 | 重点知识 | English | 中文 |
|---|---|---|---|
| Strata | 异构 MoE、CPU/GPU 放置、内存与推测执行 | [Skill](../../../../../repositories/strata/SKILL.md) | [Skill](../../../../../repositories/strata/translations/zh-CN/SKILL.md) |
| vLLM | token/准入/输入预算、KV 归属与前缀复用、scheduler/runner/attention、并行服务 | [Skill](../../../../../repositories/vllm/SKILL.md) | [Skill](../../../../../repositories/vllm/translations/zh-CN/SKILL.md) |
| SGLang | scheduler 与缓存复用、Radix/HiCache、prefill/decode 和并行、扩展及调优 | [Skill](../../../../../repositories/sglang/SKILL.md) | [Skill](../../../../../repositories/sglang/translations/zh-CN/SKILL.md) |
| SGLang-Omni | pipeline/stage runtime、scheduler IO 边界、流式/背压/传输、模型接入 | [Skill](../../../../../repositories/sglang-omni/SKILL.md) | [Skill](../../../../../repositories/sglang-omni/translations/zh-CN/SKILL.md) |
| vLLM-Omni | 固定拓扑与部署资源、阶段亲和性/connector、AR/扩散模式、输出和状态契约 | [Skill](../../../../../repositories/vllm-omni/SKILL.md) | [Skill](../../../../../repositories/vllm-omni/translations/zh-CN/SKILL.md) |
| 总入口 | 跨引擎分析及统一的受约束搜索流程 | [Skill](../../../SKILL.md) | [Skill](../SKILL.md) |

## 从多个仓库共同提取什么

| 设计问题 | 可迁移知识 | 重要边界 |
|---|---|---|
| 调度单位是什么？ | 请求、prefill 块、decode token、推测工作、媒体块、扩散 step | 调大 batch 参数不能证明模型支持该调度单位 |
| 谁持有状态？ | 请求生命周期、KV block、前缀引用、RNG、中间 tensor、阶段/副本亲和性 | 取消、抢占、复用、流式不能随意丢弃或重放状态 |
| 内存预算由什么组成？ | 权重 + KV/模型状态 + activation + workspace + 传输 buffer + 图内存 | utilization 比例本身不能证明可行，还要看主存和生命周期 |
| 瓶颈在哪里？ | 准入/排队、CPU 预处理、kernel、集合通信、跨阶段传输、输出编码 | 局部 kernel 变快可能使服务 p95 变差或转移瓶颈 |
| 哪种并行合法？ | TP/PP/DP/EP、阶段副本，以及模型特定扩散并行组 | 仓库间名称和含义可能不同，需要布局、通信组和拓扑约束 |
| 复用了什么？ | prefix/KV 状态、embedding、权重、近似扩散中间结果 | 精确复用与近似计算需要不同的有效性键和质量门槛 |
| 流式输出如何影响执行？ | 重叠、块大小、上下文窗口、就绪、背压、完成状态 | 首文本 token 不等于首个可用音视频，块吞吐也可能掩盖间隙 |
| 如何证明改进？ | 同条件基线、固定语料/输出契约、重复测量、质量门槛、失败记录 | CPU/mock 不能认证加速器或原生传输行为 |

## AI 生成推理引擎：三层搜索空间

1. **已有配置**：搜索该模型/后端已经公开且支持的参数。先排除不可行组合，再定位并调节实测瓶颈。
2. **实现修改**：在保持模型语义的条件下，改变 scheduler、缓存策略、kernel/后端选择、runner、传输路径或阶段边界；先验证状态、数值和并发契约，再测速度。
3. **研究扩展**：新增调度、传输、分解方式或近似计算，明确新增假设、对比基线和质量预算。

先建立约束系统，再选优化算法。候选配置必须满足显存/主存、通信、支持的布局、模型语义、终止/取消和任务质量要求。在可行候选中比较延迟分位数、吞吐、内存及成本；目标冲突时保留 Pareto 前沿，本包不编造通用最优参数。

## 快照与复用边界

五个 HEAD 独立获取，**它们是知识快照，不是一套经过测试的兼容依赖栈**。尤其 Omni 仓库会固定或采用特定基础引擎版本，不能因为本包也提供了基础引擎 HEAD，就直接拿它替换依赖。

| 快照 | 固定提交 |
|---|---|
| strata | [`296b59d2f73c`](https://github.com/Niko1221/Strata/tree/296b59d2f73c8f04a805df29c2fa97655adace78) |
| vllm | [`2521446ac8c9`](https://github.com/vllm-project/vllm/tree/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5) |
| sglang | [`16176278d018`](https://github.com/sgl-project/sglang/tree/16176278d0180f1a1a578e53e6eef432577876c2) |
| sglang-omni | [`2cfb3b67becb`](https://github.com/sgl-project/sglang-omni/tree/2cfb3b67becb437b70751defe37e63d3af4eedb0) |
| vllm-omni | [`52194f24fa42`](https://github.com/vllm-project/vllm-omni/tree/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1) |

已有 AREX Skill 作为前期产物进行了检查，并根据源码更新，没有当作当前事实直接复制。例如：vLLM 的 Python 要求与调度预算、SGLang 的 benchmark/cache 路径与 DP 参数含义、vLLM-Omni 从 0.26 到 0.31 的快速开始依赖变化。SGLang-Omni 的队列实现也需要越过模块标题检查代码。具体源码依据与更新边界见各仓库 references。

## 本次如何使用 AREX

按 AREX-Skill `distill-ml-knowledge` 的 **scope → ground → construct → verify** 流程，采用 direct 构建策略，保留来源/路由格式、operating 元数据和复核要求。产物是可移植候选预览；没有运行 DisCo 托管 CLI/importer，也没有宣称完成完整环境准备或 GPU 验收。详见[构建记录](../../../references/import.md)和[验证报告](../../../references/import.md)。

每个仓库可独立阅读，含根入口及按需加载的参考/子 Skill。可选总入口从 `workflows/inference-engine-research/` 链接到 `repositories/` 下的五个引擎知识包，使用它时保留这一知识库目录布局。中英文共享 canonical skill ID，同一安装位置选择一种语言；本次未安装或覆盖全局 Skill。

## 使用示例

```text
请从知识库根目录读取 workflows/inference-engine-research/translations/zh-CN/SKILL.md。参考这五个仓库，为新推理引擎建立受约束搜索空间。区分已有参数、实现修改、研究扩展；每个维度给出源码锚点、兼容约束、正确性测试和测量指标。硬件：[填写]；模型与版本：[填写]；负载与 SLO：[填写]。
```

只分析单仓库时直接读取对应 SKILL.md。本库不含引擎源码和模型权重，保留不可变源码链接及验证配方。GPU 正确性、原生分布式行为和性能需要在目标环境继续验证。
