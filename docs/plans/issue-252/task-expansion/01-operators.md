# 算子计算：当前在 NPU 上跑通 RMSNorm

**当前题目：在 Ascend NPU 的给定输入、权重和容差下，比较 affine RMSNorm 的基础运算与融合实现，同时保留计算结果。**

状态：`rmsnorm-npu` 已在 Ascend 910B1 完成真实正确性、同步计时、CPU/NPU profile、A/A 和候选比较，见[实测记录](../npu-validation.md)。资格限已记录 runtime、float32 与 workload，不能外推整类算子或其他硬件。`softmax-cpu` 保留为软件控制，`rmsnorm-cpu` 已移除；[正式正确性接入](../formal-integration.md)目前仍是 CPU 路径。

## 为什么先在 NPU 做这个任务

RMSNorm 有清晰的数值语义、基础运算基线和 torch_npu 融合候选，能在一个受限问题上检验真实设备执行、独立 oracle、同步计时和结果交接。先完成这条 NPU 通路，再扩展题类；更多 CPU 数学样例不能替代设备验收。

在现有 SearchSpace 中关联 Operator 的 Optimize/Verify。NPU profile 必须实际生成并解释；任务标签不证明 Agent 具有 Diagnose 能力。设备结果只提升该环境和工作负载的证据，不能自动提高整个 Accelerator 层的成熟度。

## 固定来源与复用决定

| 来源 | 具体借鉴 | 适用边界 |
| --- | --- | --- |
| [Ascend op-plugin RMSNorm](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/op_plugin/ops/opapi/RmsNormKernelOpApi.cpp) 与 [对应测试](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/test/test_custom_ops/test_npu_rms_norm.py) | 真实 affine 算子 API；`9f23f00`，BSD-3-Clause | 本轮先声明二维 contiguous float32，运行时支持与性能另做设备验证；不导入上游 runner |
| [KernelBench Softmax](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/KernelBench/level1/23_Softmax.py)、[RMSNorm](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/KernelBench/level1/36_RMSNorm_.py) | 既有 CPU 任务的数学题意；`423217d`，MIT，原包保留许可证 | 新 NPU 题单独定义二维 affine RMSNorm，不继承旧四维 axis=1、无 affine 或上游 GPU 资格 |
| [AMD AgentKernelArena task v2](https://github.com/AMD-AGI/AgentKernelArena/blob/47c2658a07efc7c2c0f72751781a5b5690471b0b/docs/how-to/add-task.md) | semantics、candidate、baseline、reference、workload 与 evaluation 的分工 | 作为协议设计参考；不导入其 GPU/Agent 执行平台或声称当前 CPU 实现满足其设备资格 |
| [BackendBench](https://github.com/meta-pytorch/BackendBench/blob/2a8d7e19e2c13c789ff2dceb44883ea8ea04dab4/README.md) | 边界输入/布局检查与模型来源 shape 的区分 | 作为扩展输入的设计参考；未复制 OpInfo/FACTO 或 TorchBench 运行体系 |

后两项本轮仅引用既有[源码调研](../01-research.md)，没有复制其代码；未来复制具体文件时按其文件及依赖许可保留归属。

## Agent 做什么、工具检查什么

- NPU 改动面是 `implementation.py` 的 `compute(x, weight, *, eps)`；不能修改 oracle、输入分布、容差或计时器。
- 首版明确二维 contiguous float32，输入/权重保持及变化输入需检查；独立 CPU double oracle 不复用设备归约。
- CPU/NPU profiling 单独运行，不将诊断开销计入优化分数；缺少设备 trace 如实记录。
- Workbench 比较已审核可信源码；正式 SkillEval adapter 当前只支持 CPU 隔离 replay，不接收 NPU 题。

## 下一步资格实验

在真实 NPU 完成同码/no-op、错误但快的实现和基础算子/融合候选对照，确认计时信号可区分；保留原始样本与版本，不把 CPU 历史样本重绑到新 grader。

本轮先验证选定 NPU 任务的执行与测量协议。后续从实际模型 profile 选择代表瓶颈，再决定扩展 reduction、fusion、attention 或其他算子。每个设备任务独立定义同步、编译、warmup、dtype、数值检查和计时边界；不能只给 CPU manifest 换一个 backend 字符串。

该类任务的成功只支持相应算子/环境结论。模型或服务收益仍需对应工作负载的端到端验收。
