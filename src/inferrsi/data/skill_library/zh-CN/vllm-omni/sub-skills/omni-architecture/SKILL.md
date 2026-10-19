---
name: omni-architecture
description: "梳理 vLLM-Omni 阶段归属并建立带约束的架构与执行搜索空间。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 架构与搜索

用于源码理解或 AI 生成推理引擎设计。读取[架构与搜索维度](references/architecture.md)，再按需查[证据索引](../../references/evidence.md)。

先沿选定流水线追踪一个真实请求，再做归纳。记录各阶段输入输出契约、状态归属、调度单位、设备、通信和终止条件。候选项分别归为已有配置、实现修改或研究扩展。

产出带依赖约束的搜索表：合法取值、可行性检查、质量约束和测量项。执行优化时固定工作负载和模型语义；降分辨率、减少 denoise 步数、量化和近似缓存需要单独的质量预算。

源码缺少字段/能力时，标为拟新增能力。文档冲突时核对固定提交的实现和测试，并保留未解决的不确定性。部署问题转到[服务](../omni-serving/SKILL.md)，代码修改转到[验证](../omni-validation/SKILL.md)。
