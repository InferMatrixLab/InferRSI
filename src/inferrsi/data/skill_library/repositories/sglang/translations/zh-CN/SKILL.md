---
name: sglang
description: "基于固定版本源码理解、调优或扩展 SGLang 推理运行时，覆盖调度、KV/HiCache、并行执行、内核及受控验证。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# SGLang 推理工程

本技能图用于 SGLang 引擎分析、有限范围调优和实现审查。使用前先将当前 checkout 与[来源记录](references/repo-provenance.md)比较。这是基于一个固定提交的可移植候选包，不代表任何 GPU 配置已验证通过。

先选择一个主路径；涉及另一边界时再组合读取：

| 任务 | 读取 |
|---|---|
| 跟踪请求；排查准入、前缀复用、KV 压力、分块或投机解码 | [运行时与内存](sub-skills/sglang-runtime-memory/SKILL.md) |
| 选择 TP/DP/EP/PD 拓扑；增加模型、注意力后端或内核 | [并行与扩展](sub-skills/sglang-parallel-extension/SKILL.md) |
| 设计有限实验、正确性门槛或基准对比 | [调优与验证](sub-skills/sglang-tuning-validation/SKILL.md) |

记录模型/tokenizer 版本、硬件与互连、SGLang 提交、依赖版本、负载形态和期望结果。提出方案前，区分**现有配置**、**实现修改**和**研究扩展**。单个参数存在，并不能证明任意参数组合受支持。

明确请求路径：HTTP/Engine → TokenizerManager → Scheduler/ScheduleBatch → TpModelWorker/ForwardBatch → ModelRunner/backend → 结果 → DetokenizerManager → 调用方。重叠调度和分布式角色会改变时序与所有权；[架构参考](references/architecture-and-memory.md)标出这些边界。

优先提出最小因果假设及其可观察检查。保持缓存身份、请求生命周期、分配所有权和集合通信参与关系正确。接受性能收益前先验证输出正确性；未测量的效果只能标为假设。检查失败时保留复现用例，回到已知基线后再增加下一项优化。

[原生候选映射](references/native-candidates.md)指出代码修改时可读取的仓库专项技能，不会自动导入或执行它们。[源码映射](references/source-map.md)保留经检查的提交固定证据；[路由元数据](references/repo-routing-metadata.json)记录 AREX 分类。

范围不包含 SGLang 前端语言教程、扩散模型流水线、完整部署自动化或全部加速器的任意组合。超出已取证路径时应继续读取对应原生实现。
