---
name: strata
description: "基于源码证据分析、开发和调优 Strata 式异构 MoE 推理引擎，构建带条件约束的搜索空间，并用正确性门槛筛选实验。适用于 Strata 架构、CPU/GPU 专家放置、缓存与推测解码取舍，以及引擎验证。"
license: MIT
metadata:
  disco-role: operating
---

# Strata 推理引擎工程

将仓库已有机制作为引擎设计和调优的起点。本 Skill 从固定提交提炼，属于候选版本，不代表已完成 GPU 运行验证或取得性能提升。使用其他提交或模型族时先读[来源记录](references/repo-provenance.md)。

## 按任务选择分支

- 分析架构或构建 AI 生成引擎的搜索空间：读 [design-space](sub-skills/design-space/SKILL.md)。
- 针对硬件和负载设计调优实验：读 [tune-execution](sub-skills/tune-execution/SKILL.md)。
- 声明正确性或性能之前，以及处理构建、基准失败时：读 [validate-engine](sub-skills/validate-engine/SKILL.md)。
- 共性故障：读[排障指南](references/troubleshooting.md)。

## 明确实验约定

记录模型族、权重与量化版本、源码提交、后端与硬件拓扑、可用显存和内存、输入输出长度、并发、采样规则、质量阈值及优化目标。硬件未知时输出条件化候选，不臆测最优配置。

区分固定模型语义、运行参数、可替换算法与新增能力。Strata 的 Flash-Next 和 Qwen3.6 路径不能混用。CPU/GPU 数值差异、KV 量化和路由专家跳过均需质量验证。原生引擎与 Python 服务层需分别验证；`setup.py` 不是供 `pip install .` 使用的包安装入口。

## 形成可复查结果

1. 先说明瓶颈假设和证据，再修改一个机制或有明确关系的一组参数。
2. 测量前排除不兼容或超预算配置；记录引擎实际启用的配置及回退日志。
3. 先验证数值和状态正确性，再做性能排名。分别报告静态、CPU 和 GPU 原生验证。
4. 保持实验条件一致，保存原始日志和反例，说明不确定性及未验证后端。

汇总实测记录时使用捆绑的 [CSV 约定](references/trial-format.md)和[汇总脚本](scripts/summarize_trials.py)。脚本依据输入的有效性和质量标签筛选并计算中位数，不能代替质量验证，也不能证明统计显著性。
