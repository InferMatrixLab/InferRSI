---
name: architecture-search-space
description: "追踪 vLLM V1 请求执行及 token/KV 所有权；在提出推理改动前，将调度、缓存、后端、投机与并行控制项映射到源码。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 架构与搜索空间

从现象或待实现机制、固定提交、一次请求或迭代的轨迹开始。执行链与不变量见[运行路径与不变量](references/runtime-and-invariants.md)；判断调参还是实现新能力时读[能力边界](references/capability-boundaries.md)。

1. 追踪前端请求 → engine core → scheduler output → executor/runner → attention/model/sampler → scheduler update。现象涉及陈旧输出或完成状态时，还要检查取消与异步重叠路径。
2. 定位稀缺资源：调度 token 预算、runner 输入容量、准入序列数、KV 块、encoder 计算、设备计算、显存带宽或通信。它们可能同时成为限制。
3. 将已有控制项对应到资源，说明相互作用及能否定假设的观测。解析实际生效配置，不把 dataclass 的测试默认值当成服务默认值。
4. 若能力缺失，明确缺少的行为或不变量及代码边界。已有实验性扩展点可作起点，不代表稳定性承诺。改动转到[扩展与验证](../extend-validate/SKILL.md)。

检查：解释应包含真实符号、固定证据链接、工作负载依赖和正确性约束。恢复：文档与实现矛盾时，报告冲突，当前行为以固定实现为依据并缩小结论；不能仅凭目录或注册表条目判断支持性。
