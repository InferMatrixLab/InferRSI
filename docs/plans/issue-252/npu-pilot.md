# NPU 试点：用 RMSNorm 跑通一次真实优化比较

2026-11-04，用户将试点明确指定为 NPU。**本轮已在 Ascend 910B1 完成实际运行，七项软件资格检查通过**，见[实测解释与保留决定](npu-validation.md)和[全部样本及身份](npu-validation-summary.json)。本页保留任务接口与执行方法。已有 CPU 测试和样本仅作历史软件证据；项目接受、NPU 产物隔离与真实 Agent 收益另行验收。

以下图示、步骤和验收矩阵描述本轮已执行的参考控制与工具资格试点，其 profiling 检查继续按原冻结计划保留。通用 Agent 优化流程中，profiling 是按需使用的工具，不是必做步骤，也不因缺少 profile 默认判失败；见[当前流程说明](04-integration.md#流程也是交付内容)。

## 这次究竟要跑通什么

给 Agent 一个具体问题：**在 Ascend NPU 上保持 affine RMSNorm 计算结果，检查基础算子组合能否由更合适的实现替代。** Agent 交付真实源码；InferRSI 负责独立检查、诊断和测量，再用证据决定是否保留。首个参考候选采用 `torch_npu.npu_rms_norm`，是否更快由实际实验判断。

```mermaid
flowchart LR
    A["固定题目、环境和验收"] --> B["运行 NPU 基线并 profiling"]
    B --> C["记录改法依据并交付候选"]
    C --> D["独立正确性和错误控制"]
    D --> E["同码对照与 NPU 同步计时"]
    E --> F["Workbench 报告与保留决定"]
```

这些步骤由主 Agent 调用已有接口完成；本次没有新增跨轮次搜索控制器，也没有通过图示保证任何 Agent 都自动遵守顺序。留存的诊断、代码与决定才是演练证据。

## 为什么选择 RMSNorm

RMSNorm 是推理中明确的归约与逐元素计算。基础运算组合和 NPU 融合算子提供两条可实际比较的实现路径，且遗漏 epsilon、忽略权重、错误 dtype 或旧结果重放都有可构造的反例。相比先接入整个服务，它能在一个受限问题上验证设备执行、数值裁判、同步计时和 profiler 是否真正接通。

已有 [KernelBench 语义与评测研究](01-research.md)提供任务/基线/裁判分离的来源；[AgentKernelArena task contract](https://github.com/AMD-AGI/AgentKernelArena/blob/47c2658a07efc7c2c0f72751781a5b5690471b0b/docs/how-to/add-task.md)提供任务责任划分。它们的 GPU/CPU 结果不能证明 Ascend 资格；本轮任务采用独立的 NPU affine 语义，torch_npu API、运行时兼容性和设备行为必须以源码核对与真实执行补证。

| NPU 一手来源 | 采用与验证边界 |
| --- | --- |
| [op-plugin RmsNormKernelOpApi.cpp](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/op_plugin/ops/opapi/RmsNormKernelOpApi.cpp) 与 [对应测试](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/test/test_custom_ops/test_npu_rms_norm.py) | 固定 `9f23f00`，核对 affine 权重、epsilon 和输出接口；[BSD-3-Clause 许可](https://github.com/Ascend/op-plugin/blob/9f23f00b1ebe54cca612b0537bc582dba409a0af/LICENSE)。实际安装版本的支持范围仍需本轮执行验证 |
| [Ascend PyTorch profiler tests](https://github.com/Ascend/pytorch/blob/9065e614f02639f5ddde0cf370bb9d38de7bd8a9/test/profiler/test_npu_profiler.py) | 固定 `9065e61`，核对 NPU profiler 使用方式；trace 成功和实际设备活动须检查最终产物，不能只凭 API 存在 |

本次使用原生算子 API 和自编任务适配，不搬入上游整套执行器。源码参考、许可、版本与实测分开记录。

## 任务接口与冻结内容

| 项目 | 本轮约定 |
| --- | --- |
| 任务 | `rmsnorm-npu`；单个实现文件 `implementation.py` |
| 候选入口 | `compute(x, weight, *, eps)`，输入输出是目标 NPU 上的 tensor |
| 数值语义 | 二维 contiguous float32 `[rows, features]`；`x / sqrt(mean(x²) + eps) * weight`，非全一的一维 float32 权重 |
| baseline | 在 NPU 上执行的 PyTorch 基础运算组合 |
| 参考候选 | `torch_npu.npu_rms_norm(x, weight, epsilon=eps)[0]`；取规范化输出而非辅助结果 |
| oracle | CPU scalar double / `math.fsum` 归约后乘权重并转 float32；不复用设备归约或将 baseline 当唯一真值 |
| 环境 | 冻结实际设备型号、torch / torch_npu / CANN 版本、设备选择与源码身份；缺少 NPU 时明确失败，不回退 CPU |
| 输入范围 | 形状、分布、epsilon、容差与变化输入序列写入 manifest；仅宣称实际检查范围 |
| 修改权限 | 候选源码可改；输入、oracle、容差、计时规则和报告不可由候选改写 |
| 性能边界 | 输入/权重和 oracle 在计时外准备；使用声明的设备同步边界统计完成调用；预热/初始化与正式样本分开 |
| profiler | 单独运行并保存 CPU/NPU trace 或表格、配置与文件摘要，不把 profiler 开销混入性能分数 |

共享接口保持 `check / profile / measure / plan / compare` 的分工；NPU adapter 负责自身语义、依赖、设备检查、同步与运行时身份。不能只把 CPU manifest 的 backend 改名就称为设备适配。

普通 `plan` 只是命令/RunSpec 预览。正式实验仍要在搜索前保存任务、基线、候选、oracle、环境与验收条件；重复次数、时间预算及判断门槛放在本次实验计划与 acceptance issue，不能写成仓库通用常量。

## 实际执行顺序

1. **确认环境。** 在已有 NPU 容器内核对个人身份、设备映射和共享调度器。所有 torch_npu 导入、设备诊断、测试与基准在有效设备预约内执行；不改共享安装，不切换正在被其他任务使用的源码。
2. **固定本轮输入与实现。** 保留源码、task/grader、运行时及 manifest 身份；记录工作目录和实际导入位置，避免只改变目录却导入其他 checkout。
3. **运行基线与独立 profiling。** 先确认数值正确；保留真实 NPU 活动，记录观察到的算子、调用或同步行为。没有 device trace 时不得声称已诊断设备瓶颈。
4. **记录假设并运行候选。** 将观察与候选改动关联；如果融合候选来自预先选定的参考实现，明确是 authored control，不能声称 Agent 从 profile 自主发现它。
5. **执行正确性和错误控制。** 检查合法候选、全零错误、遗漏 epsilon、忽略权重等语义错误；失败不得获得可用性能分数。实际被计时的输出也要核对。
6. **执行 A/A 和候选比较。** 相同设备与固定条件下保留逐次样本；使用现有 Workbench 组织 AB/BA。诊断、H2D/D2H、oracle 和初始化开销单独记录。
7. **记录决定。** 引用数值、trace 和原始样本，说明保留、放弃或证据不足。信号无法区分、运行不完整或环境漂移时，不得写成优化成功。

## 验收矩阵与实际证据

| 要回答的问题 | 必须执行的控制/记录 | 本轮状态 |
| --- | --- | --- |
| 是否确实在 NPU 运算？ | 输入/输出设备、实际运行时、设备预约、真实设备活动、退出码 | Ascend 910B1 已运行，退出 0；实际 kernel trace 已检查 |
| 是否算对？ | baseline 与参考候选对独立 oracle；声明范围内的边界输入、输入与权重保持 | 两者各 75 次调用、375 项断言通过 |
| 错误但快是否会被拒绝？ | 全零、遗漏 epsilon、忽略权重等候选；无可用性能指标 | 六类错误控制均拒绝；另有预检后重放控制 |
| 计时是否覆盖完成的设备计算？ | 同步边界、变化输入、预热与正式样本、实际输出校验 | 同步 eager 计时，保留全部 800 样本 |
| 同码是否被误判成进步？ | A/A 或 no-op 对照，保留波动与原始 verdict | 两个 shape 差异小于 0.4%；未达到收益门槛 |
| 融合候选是否值得保留？ | composed baseline 对 fused 候选的 AB/BA、分工作负载样本和结论 | 本轮两个 workload 达到预定门槛，保留参考实现 |
| profiling 是否发挥作用？ | 真实 profile、据此作出的具体判断及后续动作；预定控制与自主发现分开 | 核对每输入 6 个基础 kernel → 1 个 RmsNorm；非自主发现证明 |
| 结果是否接入 RSI？ | Workbench 的 RunSpec、实际实现身份、检查/比较报告与最终决定 | 实际 A/A 与参考 AB/BA、最终 validation 和身份重验已完成 |
| 正式 SkillEval 是否能隔离 NPU 产物？ | 设备访问、父子边界、可信 oracle、重验与攻击控制 | 本轮尚未建立，不能用 CPU sandbox 替代 |
| 是否提高了 Agent/skill 或服务能力？ | 受控 Agent 两臂或目标模型/服务实验 | 未测，不由本试点推导 |

“有用”首先指可以识别错误、记录真实设备行为，并支持有根据的保留决定。算子完成延迟有改善，只能支持对应 NPU、dtype 和 workload 的结论；没有模型/服务验收就不声称端到端收益。

## 产物与边界

保留任务/源码/环境摘要、独立检查结果、全部计时样本、profile 文件及其摘要、Workbench 报告、日志和退出码。公开前移除私有主机、账号与个人路径，完整原始日志留在受控执行归档中；任何删减或转换说明来源和范围。

首轮运行已审核可信源码。现有正式 `engineering-benchmark-v1` 只支持 CPU 任务，Linux bubblewrap 控制没有验证 NPU 设备隔离；不得通过隐式宿主执行或 CPU fallback 绕过不支持状态。NPU 产物隔离需要后续单独验收。

旧 CPU 任务继续服务回归和历史记录。Tokenizers、KV、通信与服务的研究保留在[扩展方案](task-expansion/README.md)，按各自任务资格推进。当前跟踪已收敛为 #336 任务库和 #337 接入两项，见[总览](README.md)；本页的试点记录不因 Issue 调整而改变，NPU 演练完成不自动关闭整个 #252。
