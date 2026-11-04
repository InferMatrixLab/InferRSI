# 研究支持文档：选定任务和复用方案

原独立 Issue #334 的范围已并入 [#336 任务库建设](03-tasks.md)和 [#337 流程接入](04-integration.md)。本文保留论文、固定源码与历史采用理由；研究仍随每批任务和接口工作进行，不再作为独立交付 Issue。旧 Issue 关闭不代表所有研究候选已实现或获验收。

2026-11-04 范围更新：用户已指定 NPU 试点，当前优先交付 [RMSNorm NPU 方案](npu-pilot.md)。[五类任务研究](task-expansion/README.md)继续保留，但 Tokenizers.encode 不再作为当前试点。下面的初始 CPU 选型作为历史设计依据，不代表本轮设备验收或整个 SearchSpace 的最终覆盖。

**这项工作的交付是选型结论：用真实 NPU affine RMSNorm 跑通任务、独立检查、profiling 和比较，复用已有任务契约与 Workbench，而不是再建一个执行平台。**

| 要说清楚的问题 | 本子项的答案 |
| --- | --- |
| 具体做什么 | 阅读论文与固定版本源码，比较任务、正确性参考、测量和执行边界，确定首批范围 |
| 交付什么 | 下文的一手来源表、方案比较、采用/不采用理由和任务选择 |
| 谁使用 | 子项 02 的接口开发者、子项 03 的任务开发者，以及范围评审者 |
| 实际作用 | 明确 NPU 试点问题、基线与参考候选，复用已有 Workbench；CPU SkillEval 资格不自动延伸到设备 |
| 当前状态 | 既有研究保留，NPU 选择与资格计划明确；设备结果和维护者验收分别记录 |

它是设计依据，运行时不会执行“调研模块”。具体成果落实在任务库和流程接入两项工作中。

## 理解

研究目标是选出适合现有 InferRSI 的最小可用组合。不能把一个外部 benchmark 的评分、runner、agent 和 CUDA 假设整体搬进来。

## 计划

1. 重读 #252 正文与两条评论，区分已要求的任务契约和独立 policy RFC。
2. 核对 KernelBench、AgentKernelArena、BackendBench、SkillsBench 的论文和源码边界。
3. 用 AlphaEvolve、AIDE 检查任务评估和搜索策略的职责划分。
4. 核对现有 RunSpec、Workbench 和 SkillEval，选择最薄的接入方式。
5. 记录固定来源、许可证、适配变化以及未采用原因；让实现和反例验证检验决策。

## 一手来源与采用边界

2026-11-03 重新读取下列来源。论文解释方法，固定版本代码确定可复用接口。作者的测量结果不作为本地结果。

| 工作 | 证据与具体设计 | 本次决定 |
| --- | --- | --- |
| KernelBench | [论文 §3、§4.2](https://arxiv.org/html/2502.10517v1) 将正确性和速度分开；[Softmax](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/KernelBench/level1/23_Softmax.py) 和 [RMSNorm](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/KernelBench/level1/36_RMSNorm_.py) 明确 axis=1；[MIT 许可](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/LICENSE) 已读取 | 适配数学题意并保留许可。CPU/NumPy、小形状、边界分布是明确变更。原 Softmax 的 4096×393216 FP32 输入约 6 GiB，不直接搬用 |
| AgentKernelArena | [论文 §3.1](https://arxiv.org/html/2605.16819v1) 分离 workspace、baseline、agent、central evaluation；[task v2 contract](https://github.com/AMD-AGI/AgentKernelArena/blob/47c2658a07efc7c2c0f72751781a5b5690471b0b/docs/how-to/add-task.md) 把 semantics/candidate/baseline/reference/workload/evaluation 放在任务包 | 采用责任划分、baseline/oracle 分离、统一最终评估。没有复制 GPU 平台或评分器，没有声称满足其 GPU 资格标准 |
| BackendBench | [README](https://github.com/meta-pytorch/BackendBench/blob/2a8d7e19e2c13c789ff2dceb44883ea8ea04dab4/README.md) 明确用 OpInfo/FACTO 做边界检查，用真实模型 shapes 做性能 | 借鉴边界和布局验证。首批不引入整个 PyTorch backend override、FACTO 和 TorchBench，也不声称覆盖它们 |
| SkillsBench | [固定版本 README](https://github.com/benchflow-ai/skillsbench/blob/f860ecf02ef53412a030f8661c83d644b739ff01/README.md) 分离 task.md、environment、oracle、verifier；[论文](https://arxiv.org/abs/2602.12670) 是技能受控比较参考 | 保持题目与技能条件独立，沿用现有 SkillEval verifier，不接入另一套云执行平台 |
| AlphaEvolve | [§2.1、§2.4–2.6](https://arxiv.org/html/2506.13131v1) 分离 task/evaluate、evaluation cascade、程序库和演化控制 | 采用正确性先于测量。候选生成、选择和程序库不放进 #252 |
| AIDE | [§3.1–3.2](https://arxiv.org/html/2502.13138v1) 显式区分 evaluator h、search policy π、coding operator f、solution tree T | search policy 是独立模块。本次提供任务评估，不实现搜索树或停止规则 |
| InferRSI 当前源码 | RunSpec 要求 baseline/candidate；runner 已有 AB/BA、超时和快照；SkillEval run_trial 已有独立 verifier；生产 engineering verifier 有 Linux bubblewrap 边界 | 生成真实 RunSpec，诊断用 execute_trial；保留产物接入现有 verifier。生产 sandbox 和执行权限不变 |

## 当前 NPU 选择

官方算子与测试固定在 op-plugin `9f23f00b1ebe54cca612b0537bc582dba409a0af`，NPU profiler 使用方式参考 Ascend/pytorch `9065e614f02639f5ddde0cf370bb9d38de7bd8a9`；[NPU 来源表](npu-pilot.md#为什么选择-rmsnorm)给出具体文件与许可。它们提供 API 和任务设计依据，不替代安装环境验证。

1. 首个试点选 **affine RMSNorm**：二维 contiguous float32 输入、非全一权重，基线使用 NPU 上的基础运算组合，参考候选使用 `torch_npu.npu_rms_norm`。独立 CPU scalar double / `math.fsum` 路径计算参考结果。官方 NPU 算子的语义与运行时支持需单独核对，不直接继承旧 CPU 四维无 affine 任务。
2. 保留 `check / profile / measure` 与现有 RunSpec / Workbench 接口，由 NPU adapter 明确依赖、设备身份、同步、输入准备和计时边界。实际设备不支持时拒绝执行，不静默退回 CPU。
3. 先用正确/错误候选、A/A 和基础算子/融合候选对照验证任务能否产生可信决策，再扩充题数或评估 Agent。融合候选是参考控制，不预设其必然加速。
4. 真实 CPU/NPU profiling 单独运行；记录观察如何影响改法或最终决定。仅生成 profile 文件不能证明 Agent 使用了诊断。
5. 正式 SkillEval 的现有 Linux sandbox 是 CPU 路径。NPU Workbench 先执行已审核可信源码；NPU 产物隔离与真实 skill 收益单独跟踪。

具体契约、验收矩阵和未完成项见 [NPU 试点](npu-pilot.md)。后续 Tokenizers、KV、通信与服务题仍按各自来源、环境和裁判重新资格，不因已有 CPU 或 NPU 任务完成而宣布全部覆盖。

## 历史 CPU 方案比较与采用理由

以下记录最初硬件未定时的 CPU 决策，不作为当前优先级。原设计和失败证据保留便于审查，本轮已由上面的 NPU 决定更新交付目标。

| 方案 | 优点 | 当前问题 | 决策 |
| --- | --- | --- | --- |
| 完整引入外部 benchmark runner | 复用成熟 GPU 生态 | 硬件未定，重复 Workbench，带入 agent/评分假设 | 不选 |
| 只写统一 schema | 成本低、无需设备 | 无法验证真实任务或消费者 | 不选 |
| 首版实现所有硬件与三大类别 | 覆盖广 | 无资格环境，容易只剩空协议 | 不选 |
| 小任务包 + adapter + 既有执行器 + 两个消费者 | 语义和证据共享，可立即跑通和检验反例 | 首批只证明 CPU 子集 | **采用** |

1. **首批选 Softmax 和 RMSNorm**。都是推理相关归约算子。Softmax 暴露 exp 溢出，RMSNorm 四维输入暴露错误轴，使第二道题有不同验证价值。通信/显存不放空实现。
2. **消费者接口通用，adapter 能力具体**。`command(check|measure|profile)` 和 `runspec` 是共享边界，当前 `numpy-axis1-v2` 以变化输入修复最初 v1 的重放问题，见 [协议验证](replay-validation.md)。未知 backend/adapter 被拒绝。未来适配器沿用消费者入口，但必须定义自身同步、计时、manifest 校验和环境资格。
3. **独立 oracle**。baseline/candidate 用 NumPy 归约，oracle 用标量 double 与 math.fsum，减少共享实现错误。容差属于具体任务数值规范，非全仓库性能门槛；每次比较冻结。
4. **检查真实计时路径**。计时后的实际输出再验证，能发现预检后变错的状态行为。公开输入、同进程评估不能抵御恶意作弊，入口限定已审核可信文件，不能直接接任意模型源码。
5. **profiling 独立**。CPU cProfile 解释 CPU 调用，不进入速度统计、不输出 A/B verdict。设备 trace 待硬件 adapter。
6. **SkillEval 采用保留产物 replay**。controller 固定审核后的候选及其哈希，已有 run_trial 调用独立 verifier。本次 authored control 验证真实通路，没有模型调用和技能收益结论。
7. **共享身份与原始样本**。task、grader、candidate、runtime 分别有哈希，记录实际输入摘要及每次样本。漂移、缺依赖、超时保留不完整证据。没有新建 AB/BA 调度器或统计规则。

## 对评论中三个问题的处理

- 没有引入 `upper_bound < residual_target`，增量贡献仍由独立 policy 处理。
- correctness/profile 有独立执行记录，不需要伪造 baseline；只有 measurement 构成 A/B。
- 没有把某 cell 一条失败记录解释成搜索耗尽，也没有增加停止控制器。

以上 CPU 选择针对当时硬件未定的约束；当前设备方向已明确为 NPU。无论哪一阶段，来源调研和贡献者方案都不代替维护者对 #252 的最终验收。
