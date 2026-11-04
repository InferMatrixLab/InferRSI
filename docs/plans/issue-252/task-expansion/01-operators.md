# 算子计算：保留已有试点，设备明确后扩展

**题目例子：在给定输入和容差下，让 RMSNorm 实现更快，同时保留计算结果。**

状态：Softmax/RMSNorm CPU 两题已存在；本轮没有新增算子、执行测量或建立 GPU/NPU 资格。当前可靠性能排序仍未完成。原始实现与证据见[子项 03](../03-tasks.md)及[正式正确性接入](../formal-integration.md)。

## 为什么保留，而不继续只加同类题

它们适合验证单文件候选、独立数值参考、输入变化与结果交接。增加更多 NumPy 数学函数会扩大数值样例，却不能自动覆盖 CPU 编码、状态回收、通信或服务调度。下一批开发优先补这些不同的工程问题。

在现有 SearchSpace 中关联 Operator 的 Optimize/Verify；CPU profile 只能提供本次 CPU 调用诊断。任务标签不证明 Agent 具有 Diagnose 能力，CPU 适配也不提升 Accelerator 资源层的实测成熟度。

## 固定来源与复用决定

| 来源 | 具体借鉴 | 适用边界 |
| --- | --- | --- |
| [KernelBench Softmax](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/KernelBench/level1/23_Softmax.py)、[RMSNorm](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/KernelBench/level1/36_RMSNorm_.py) | 数学题意；`423217d`，MIT，已有任务包保留许可证 | 当前缩小为 CPU/NumPy/float32 开发子集，不是上游 GPU workload |
| [AMD AgentKernelArena task v2](https://github.com/AMD-AGI/AgentKernelArena/blob/47c2658a07efc7c2c0f72751781a5b5690471b0b/docs/how-to/add-task.md) | semantics、candidate、baseline、reference、workload 与 evaluation 的分工 | 作为协议设计参考；不导入其 GPU/Agent 执行平台或声称当前 CPU 实现满足其设备资格 |
| [BackendBench](https://github.com/meta-pytorch/BackendBench/blob/2a8d7e19e2c13c789ff2dceb44883ea8ea04dab4/README.md) | 边界输入/布局检查与模型来源 shape 的区分 | 作为扩展输入的设计参考；未复制 OpInfo/FACTO 或 TorchBench 运行体系 |

后两项本轮仅引用既有[源码调研](../01-research.md)，没有复制其代码；未来复制具体文件时按其文件及依赖许可保留归属。

## Agent 做什么、工具检查什么

- 当前改动面是 `implementation.py` 的 `compute(x, *, eps)`；不能修改 oracle、输入分布、容差或计时器。
- 数值检查覆盖普通/极端值、不同 shape/layout、输入保持及多次变化输入；裁判与候选实现分开。
- CPU profiling 单独运行，不将诊断开销计入优化分数。
- Workbench 比较适用的已审核源码；正式 SkillEval adapter 隔离 replay，仅提供正确性结果。

## 下一步资格实验

先完成同码/no-op、错误但快的实现和参考优化对照，确认计时信号可区分；保留原始样本与版本，不把历史样本重绑到新 grader。

设备确定后，从实际模型 profile 选一个代表瓶颈，再决定是扩展 reduction、fusion、attention 还是其他算子。设备版需要独立定义同步、编译、warmup、dtype、数值检查和计时边界；不能只给 CPU manifest 换一个 backend 字符串。

该类任务的成功只支持相应算子/环境结论。模型或服务收益仍需对应工作负载的端到端验收。
