---
name: sglang-parallel-extension
description: "规划 SGLang TP、副本 DP、注意力 DP、EP 与 PD 拓扑，或在所有权和正确性约束下扩展模型、注意力后端与内核。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 并行与扩展

读取[并行与扩展参考](../../references/parallelism-and-extension.md)，仅针对本次组件使用[原生候选映射](../../references/native-candidates.md)。[返回根路由](../../SKILL.md)。

规划拓扑时，记录 rank、通信组大小、模型维度、专家布局、加速器显存、互连和负载。区分副本 DP 与注意力 DP，并在固定 checkout 中确认整除关系及模型/后端限制。PD 调整容量前，应在两种角色中跟踪路由、bootstrap 身份、目标分配、传输完成以及超时/取消。

实现修改选择最小责任边界：

- 模型：配置/架构解析、前向语义、分片权重加载、必要的多模态预处理，以及 logits/采样衔接。
- 注意力后端：注册工厂、支持的 forward 模式和布局、元数据规划、缓存写入/读取、图捕获与重放。
- 内核：算子契约、数值参考、支持的形状/dtype/stride/设备、延迟注册及正确的源码/测试目录。

运行时配置会发布到命名空间配置对象；原始 ServerArgs 记录不代表最终生效决策。修改配置读取、override 或每个 runner 的状态前，先读取当前原生 runtime-context 契约。

预期交付：拓扑/所有权图或精确的补丁边界，以及基线比较。适合时先验证单 rank，再验证目标通信组和 PD 对端。分布式检查需包含空闲 rank、负载不均、取消和错误传播。

分布式 hang 需要各 rank 证据及集合通信顺序检查。内核数值错误需要缩小输入并与参考实现比较。将相关后端/特性恢复到基线，不能从导入成功、启动成功或微基准变快推断正确性。接受扩展前先制定[验证门槛](../../references/tuning-and-validation.md)。
