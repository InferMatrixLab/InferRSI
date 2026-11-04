# #252：在 NPU 上跑通共享优化任务和独立评测

**当前交付目标是：让 Agent 面对一个真实 NPU 优化任务，交付实际实现，由 InferRSI 检查正确性、保留 profiling、在固定条件下比较性能，并据此决定是否保留候选。** 用户已明确将试点指定为 NPU；已有 CPU 两题保留为历史验证与软件控制，不作为这轮试点完成依据。

从 [NPU 试点方案](npu-pilot.md)开始。首个任务是 `rmsnorm-npu`：在 Ascend NPU 上比较 PyTorch 基础算子组成的 affine RMSNorm 与 `torch_npu.npu_rms_norm` 候选。融合实现是否更快，要由实际结果决定。NPU 接入、设备执行与性能资格分别验收，不能用设计或 CPU 测试代替。

本次模块称为 **Engineering Benchmarks（共享工程评测任务）**。输入是任务包和候选实现，输出是正确性结果、独立 profile、原始计时及版本身份。它服务主 Agent 的优化工作，也为后续 SkillEval 比较不同 skill 条件下的产物提供任务。名称与范围是本次交付提议，维护者验收另行记录。

## 实际交付给使用者什么

以 NPU RMSNorm 试点为例：

- **任务：** 在明确的 NPU、dtype、输入与容差下计算 affine RMSNorm，保留 epsilon、权重和输入内容。
- **Agent 修改：** `implementation.py` 的 `compute(x, weight, *, eps)`；不修改输入、oracle、容差或计时器。
- **基线与候选：** 相同 NPU 输入上的基础算子组合与融合算子调用；独立 CPU double 参考结果负责数值检查，不计入设备性能。
- **诊断与测量：** 独立记录 CPU/NPU profile；计时必须等待 NPU 运算完成，并排除输入准备、传输和正确性检查。
- **结果用途：** 错误实现不能获得可用性能分数。同码对照与真实候选比较支持“保留、放弃或证据不足”的决定；测不清就不宣布优化成功。

流程也是交付内容。只有题目目录或独立命令不够；第四项需要保留基线、profiling、改法依据、候选、验收结果和最终决定的一条实际演练链。见[流程范围与缺口](04-integration.md#流程也是交付内容)。

## 四个子任务分别做什么

这四项是交付分工，不是四个运行时模块；一个完整 NPU 试点会同时使用它们。

| 子任务 | 具体交付 | 实际作用 | 当前状态 |
| --- | --- | --- | --- |
| **① 选题复用** · [#334](https://github.com/InferMatrixLab/InferRSI/issues/334) · [说明](01-research.md) | 论文/源码比较、NPU 选型、来源与边界 | 决定优化什么、复用哪些接口和评测设计 | 既有研究保留；本轮 NPU 方案见试点文档 |
| **② 统一规则** · [#335](https://github.com/InferMatrixLab/InferRSI/issues/335) · [说明](02-contract.md) | 任务、候选、独立 oracle、NPU 同步计时、profile 与版本身份 | 固定一次比较中的工作和裁判，拒绝 CPU 回退或错误设备结果 | CPU 接口已有；NPU 适配与实测需单独验收 |
| **③ 交付题包** · [#336](https://github.com/InferMatrixLab/InferRSI/issues/336) · [说明](03-tasks.md) | `rmsnorm-npu` 基线、候选、输入、数值检查、测量规则 | Agent 有明确修改对象，工具能在真实 NPU 执行它 | 当前交付目标；设备运行结果按试点记录更新 |
| **④ 接入验证** · [#337](https://github.com/InferMatrixLab/InferRSI/issues/337) · [说明](04-integration.md) | NPU Workbench 演练、正确/错误控制、A/A 与候选比较、报告 | 证明真实产物进入执行，结果能支持下一步 | NPU 演练待实测记录；真实 skill 收益未测 |

## 在 RSI 中的位置

| RSI 要回答的问题 | 调用者 | 本次作用与边界 |
| --- | --- | --- |
| 这个实现是否正确、是否值得保留？ | 主 Agent + Workbench | 本轮优先在真实 NPU 跑通任务检查、profiling 和比较 |
| 新 skill/知识是否帮助 Agent 写出更好的实现？ | SkillEval 两臂比较 | 当前正式产物 adapter 仅支持已声明的 CPU 任务；NPU 产物隔离与真实 Agent 对照没有完成 |

当前正式 `engineering-benchmark-v1` adapter 的 Linux bubblewrap 控制只能作为 CPU 软件边界证据，不能直接挂载设备就声称 NPU 候选已安全隔离。NPU 试点先运行已审核的可信源码；接入方法和既有 CPU 证据见[正式接入说明](formal-integration.md)。不以本次 Workbench NPU 演练冒充正式 SkillEval NPU 支持。

题库不是用户需求的白名单。题库外目标可以将自己的 benchmark 和质量检查接入**已有通用 Workbench**；它不会自动生成验收标准。当前任务 adapter 只支持明确声明的语义和环境，不等于任意模型或服务适配器。

主 Agent 决定下一次尝试；任务工具检查与测量。Optimization Search Policy 讨论如何选择改法、分配预算和停止，本次没有实现该控制器，也没有程序强制所有 Agent 先 profile 再修改。

## 后续类别与历史证据

[五类任务方案](task-expansion/README.md)保留算子、CPU 热路径、内存与缓存、通信、服务配置/调度的研究。**次序现调整为先完成 NPU RMSNorm 试点。** Tokenizers.encode 保留为后续 CPU 仓库补丁候选；KV 保留既有任务复用方向。NCCL/MSCCL 等 CUDA 题源不能直接作为 Ascend 通信实现，需另选 NPU 对应机制和资格条件。

既有 CPU Softmax/RMSNorm 的错误识别、输出重放修复、计时噪声和失败记录不改写：[v1 集成](validation.md)、[v1 用途](usefulness.md)、[v2 协议](replay-validation.md)。正式 CPU 产物软件控制见[既有 CI 记录](formal-integration.md#已执行的软件验证)。这些记录不重标为 NPU 执行、可靠速度排序或真实 skill 收益。

旧的 [CPU 完整导读](walkthrough.md)解释已实现软件接口；当前交付与启动方式以 [NPU 试点](npu-pilot.md)及本轮实际结果为准。

## 跟踪与范围

实现及文档在 [Draft PR #338](https://github.com/InferMatrixLab/InferRSI/pull/338)，四个子任务保持打开。原生父子关系写入受账号权限限制，目前通过相互引用和父任务索引追踪。用户的 NPU 试点委托授权了本轮实施、运行和发布；它不代替维护者对整个 #252 的接受或关闭决定。

父 Issue 的 [Search Policy RFC](https://github.com/InferMatrixLab/InferRSI/issues/252#issuecomment-6495138306)按[维护者范围意见](https://github.com/InferMatrixLab/InferRSI/issues/252#issuecomment-6495720922)保持独立。
