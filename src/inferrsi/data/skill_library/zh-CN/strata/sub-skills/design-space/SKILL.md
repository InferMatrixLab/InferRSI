---
name: design-space
description: "分析 Strata 的推理架构，并为 AI 生成推理引擎定义带约束的搜索空间，区分已有配置、可替换算法和需要新增的能力。"
license: MIT
metadata:
  disco-role: operating
---

# Strata 设计搜索空间

解释 Strata、设计类似推理引擎或决定 AI 优化循环可修改哪些内容时，使用此子技能。阅读[搜索空间参考](references/design-space.md)，获取架构、证据和参数依赖。

1. 提出候选方案前，固定模型家族与数值契约、硬件拓扑、工作负载分布和目标函数。模型维度是内核契约，不能当作普通调优参数。
2. 将每个候选标记为**已有配置**、**算法替换**或**新增能力**。将保持数值契约的实现改动与改变 logits 或输出分布的近似方法分开。
3. 为每个候选写明前提和拒绝条件；联合计算权重、专家驻留、KV/状态、MTP、prompt 工作区、batch slot 和内存预留。
4. 输出决策表：候选、预期瓶颈、适用条件、正确性门槛、性能指标和代码证据。明确证据缺口。

对现有部署执行参数搜索，转到 [tune-execution](../tune-execution/SKILL.md)。验证实现或处理正确性争议，转到 [validate-engine](../validate-engine/SKILL.md)。

这是可移植配置：不假设本地已有 checkout，不安装软件、下载权重或运行 benchmark。应用记录的事实前，核对所请求版本的代码差异。保留默认的自动技能发现能力。
