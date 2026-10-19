---
name: vllm-omni
description: "解释、调优和扩展 vLLM-Omni 多阶段 AR、扩散与媒体输出推理，建立有源码依据的搜索空间和验证方案。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# vLLM-Omni 推理引擎知识

用于解释、配置、调优或扩展 **vLLM-Omni** 的分阶段自回归、生成与扩散执行。仅有多模态输入不足以选择本 Skill；其重点是异构输出及模型定义的执行流水线。

这是一份基于源码提交 `52194f24fa42e14d1c5e096f4bea4dc7f95cffa1` 的可移植候选 Skill，不代表 GPU 验证通过，也不是完整模型目录。仓库或安装包不同时，先检查[来源记录](references/repo-provenance.md)。

## 按决策选择入口

| 需要解决的问题 | 读取 |
|---|---|
| 解释数据流/控制流，建立带约束的引擎搜索空间 | [架构与搜索](sub-skills/omni-architecture/SKILL.md) |
| 选择部署、阶段放置、流式输出和性能实验 | [服务与调优](sub-skills/omni-serving/SKILL.md) |
| 新增/修改流水线、runner 或 connector，验证正确性 | [扩展与验证](sub-skills/omni-validation/SKILL.md) |

只加载相关分支。[源码证据](references/evidence.md)中的链接固定到该提交；操作判断依据已包含在 Skill 内。原生测试命令需要匹配的引擎源码及环境。

## 共用流程

1. 明确模型版本、任务/输出模态、参考实现、GPU 拓扑、软件版本、输入输出形状、并发及延迟/质量要求；显式列出未知项，不编造最优配置。
2. 沿 `PipelineConfig` → 部署解析 → orchestrator → stage pool/client → scheduler/runner → connector/输出处理器追踪；区分拓扑归属与放置/资源参数。
3. 把每个建议标为**已有配置**、**实现修改**或**研究扩展**。dataclass 存在字段不等于所有模型/后端都支持。
4. 用最小受支持并发建立真实模型基线；执行调优期间固定模型、采样、生成时长/分辨率、随机种子及质量目标。
5. 先核对正确性，再比较队列、阶段、传输时间、显存峰值及分模态端到端指标；保留失败实验与实际回退路径。

## 会改变决策的约束

- `PipelineConfig` 与 `StagePipelineConfig` 定义模型语义及固定拓扑；改变它们需要注册模型变体并重新验证，部署 YAML 不能任意新建模型阶段。
- 副本、模型阶段和 tensor-parallel rank 是不同概念；有状态分块需保持请求/副本亲和性，直到完成、取消或明确的故障处理。
- 异步块传输、AR 连续批处理、扩散请求批处理、扩散单步调度和最终媒体流式输出是不同能力。
- Thinker 量化方案不能直接用于 Talker、codec 或 VAE，必须核对实现支持并验证质量。
- YAML 可解析、可导入、CPU 探针或 mock 测试通过，都不能证明 GPU 执行、媒体质量或吞吐。

输出应包含决策及源码依据、可行备选、假设、验证门槛和恢复步骤。Skill 本身不提供已实测的加速结论。
