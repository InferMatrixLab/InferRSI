---
name: tune-execution
description: "针对确定的模型、硬件与负载设计并解释 Strata 对照调优实验，覆盖专家驻留、CPU/PCIe 分工、预填充、KV、推测解码及并发。"
license: MIT
metadata:
  disco-role: operating
---

# 调优执行路径

阅读[调优流程](references/tuning.md)。从已能运行的配置出发，保留模型路径及必要选项。通过启动日志记录实际生效值；传入参数并不能证明对应路径确实启用。

硬件、负载或可接受质量损失未知时，先给出条件化实验计划。选择一个瓶颈和少量有意义的候选。架构修改使用 [design-space](../design-space/SKILL.md)；接受候选之前必须使用 [validate-engine](../validate-engine/SKILL.md)。

交付基线、候选差异、可行条件、正确性门槛、原始结果位置、重复测量与决策。保留失败和回退记录，不将其他硬件的公开加速比移用到当前设备，不让数值错误候选进入排名。
