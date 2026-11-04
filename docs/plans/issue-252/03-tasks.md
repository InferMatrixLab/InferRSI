# 子项 03：把 NPU 试点做成可执行任务

**这项工作的当前交付是 `rmsnorm-npu`：给出可以在真实 Ascend NPU 上运行的基线、候选、输入、独立正确性检查、profiling 和测量规则。** 用户已经指定 NPU，不能再以 CPU 两题可运行作为试点验收。

| 要说清楚的问题 | 本子项的答案 |
| --- | --- |
| 具体做什么 | 将 affine RMSNorm 的数值语义接到 PyTorch / torch_npu，独立定义设备同步与计时 |
| 交付什么 | 任务包、基础算子 baseline、融合候选、数值 oracle、变化输入、错误控制与原始结果 |
| 谁使用 | 修改实现的 Agent/开发者，以及 Workbench 的任务操作 |
| 实际作用 | 验证候选确实在 NPU 计算且算对，并比较真实完成一次计算的成本 |
| 当前状态 | 已在 Ascend 910B1 完成 [NPU 资格实验](npu-validation.md)，保留全部 800 样本与错误控制；CPU 旧结果不替代它 |

## 任务定义

首版使用二维 contiguous float32 输入 `[rows, features]` 与一维 float32 `weight`，沿 feature 轴计算 `x / sqrt(mean(x²) + eps) * weight`。这一版本明确采用真实 affine 语义，权重不是全一。二维的 axis=1 与末轴一致；不能直接将旧 CPU 四维 axis=1、无 affine 任务送给按末维归一化的融合算子。

基线由在 NPU 上执行的 PyTorch 基础运算组成；候选验证 `torch_npu.npu_rms_norm(x, weight, epsilon=eps)[0]`。接口为 `compute(x, weight, *, eps)`。具体形状、epsilon、容差与变化输入协议在最终 manifest 中冻结；不从 CPU 结果推导设备支持范围。融合算子是可检验的参考候选，不要求所有合法实现都调用它。

独立参考计算在 CPU 使用 scalar double / `math.fsum` 做归约，再乘权重并转换为 float32。输入与权重准备、传到设备、oracle、复制回 host 检查均在性能计时区间之外。正确性包括输出形状、dtype、设备、有限性、数值误差和输入/权重内容不被改变。普通输入之外需覆盖全零、小值及不同形状，防止省略 epsilon、忽略权重或硬编码结果通过。

## 测量与诊断

- 输入在调用前准备并绑定摘要；变化输入避免前次正确输出被重放成“优化”。不得将缓存后的答案当作实际计算时间。
- NPU 是异步设备；计时边界必须明确等待调用前后的设备工作完成。仅统计 Python 发起调用的时间不能作为 NPU 完成延迟。
- 预热、首次编译或初始化、输入准备、oracle 与输出校验不计入正式样本；具体次数及策略来自冻结任务与实验计划。
- profiling 独立于正式计时，保留 CPU/NPU 活动与 trace 身份。若设备 trace 不可用，明确缺口，不能用 CPU cProfile 替代。
- 运行同码 A/A、错误但快的候选、基础算子与融合候选；保留全部有效和失败记录，避免只报告最快样本。

完整流程、控制组和证据清单见 [NPU 试点](npu-pilot.md)。

## 验收

任务能在明确设备与运行时上重现；基线和合法候选计算正确；错误候选被拒绝且没有可用性能分数；真实 NPU profile 与同步计时进入 Workbench 证据。是否有可分辨加速另行判断，不能预先承诺融合必快。

这只是算子级 NPU 验收，不证明模型质量、服务吞吐、其他 dtype/形状、通信或显存容量。正式 SkillEval NPU 候选隔离仍需另外设计和验证，不能把可信 Workbench 源码执行包装为该能力。

## 保留的 CPU 工作

`softmax-cpu` 和 `rmsnorm-cpu` 仍是软件控制与历史任务，保留原 KernelBench 来源和 MIT 许可。它们的 NumPy 基线、标量 double / math.fsum oracle、变化输入和错误反例可以检验共享软件接口；不向 NPU 迁移其计时结果或环境资格。

旧 `numpy-axis1-v2` 每题一次完整 trial 为 41 次调用、164 项断言、25 个计时样本；CPU profile 仅解释 CPU 调用。v1 的 360 个样本与 v2 的 300 个样本保留各自 task/grader 身份，[旧协议验证](replay-validation.md)和[用途对照](usefulness.md)中的噪声、失败与限制不改写。

[五类扩展方案](task-expansion/README.md)仍保留后续题源。当前优先跑通 NPU RMSNorm；Tokenizers、KV 复用、通信和服务任务依次独立评估，不因本任务完成而标记整类已覆盖。
