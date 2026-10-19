---
name: sglang-runtime-memory
description: "跟踪 SGLang 请求和调度流程，分析 Radix/HiCache 所有权、KV 压力、分块预填充与投机解码。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 运行时与内存

通过[架构与内存](../../references/architecture-and-memory.md)读取源码位置、不变量和区分原因的观测点。拓扑或实验设计请返回[根技能](../../SKILL.md)。

1. 固定负载：输入/输出长度、共享前缀分布、流式行为、采样、并发到达、模型状态类型及缓存冷/热状态。先判断延迟来自排队、prefill、decode 还是主机/存储传输。
2. 沿分词、准入、前向、完成/取消跟踪一个请求。区分逻辑请求状态、物理 KV 槽位、前缀缓存节点和待完成的传输状态。
3. 查明该模型实际选择的缓存。普通 RadixCache 和 UnifiedRadixCache 的组件契约不同，不能将全注意力假设直接移植到 SWA 或 Mamba 状态。
4. 调参时同时检查声明和解析/兼容性钩子，并记录生效值。修改代码时，先找出所有受影响的分配、引用计数和完成路径。
5. 验证 miss/hit 等价性、部分前缀边界、压力下驱逐、完成/取消清理及 chunk 边界。投机解码还需验证 draft/target 兼容性、接受 token、拒绝 token 的状态清理及验证路径正确性。

预期交付：一个已跟踪的所有权边界、一项小改动，以及能够证伪假设的正确性/性能观测。OOM 减少本身不能证明请求状态正确或吞吐提升。

锁或池计数不一致时，停止性能优化并缩小失败生命周期。启动钩子拒绝配置时，保留错误信息并选择受支持基线，不绕过校验器。用[验证门槛](../../references/tuning-and-validation.md)区分本地静态检查和必须在 GPU 上执行的测试。
