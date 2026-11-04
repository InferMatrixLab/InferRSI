# #252：给 InferRSI 提供共享优化任务和独立评测

**我们要交付一套可复用的优化任务和独立评测工具：Agent 交付实现，工具检查算得对不对、在固定条件下测得多快，主 Agent 再依据这些证据决定下一步。**

本次模块称为 **Engineering Benchmarks（共享工程评测任务）**。它的输入是选定的任务包和候选实现，输出是正确性结果、独立 profile、原始计时及对应版本。名称是本次交付提议，正式范围仍待维护者接受。

**第一次阅读请从[完整导读](walkthrough.md)开始**：沿 RMSNorm 例子解释四个子任务、每个流程框、profiling、实际命令和结果。想核对本轮发现及修复的问题，请读[审查记录](review.md)。

## 实际交付给使用者什么

以当前 `rmsnorm-cpu` 为例：

- **任务是什么：** 在规定的 CPU float32 输入上计算沿 axis=1 的 RMSNorm，保留 epsilon 和输入内容。
- **Agent 可以改什么：** 独立 `implementation.py` 中的 `compute(x, *, eps)` 实现。
- **Agent 交付什么：** 一份候选源码；输入、oracle、容差和计时规则来自受保护的任务包。
- **谁检查：** `check` 使用独立参考答案验证；`profile` 生成单独诊断；`compare` 交给现有 Workbench 比较原版与候选版。
- **结果如何发挥作用：** 错误实现不能获得可用性能分数；主 Agent 根据正确实现的计时和完整性证据判断是否保留。若计时无法分辨，继续记录“证据不足”，不能宣布优化成功。

一次真实对照中，省略 epsilon 的实现通过了普通输入冒烟，却被完整任务和 SkillEval 底层 verifier 一致拒绝。这证明了错误识别用途。该对照同时暴露计时噪声；可靠性能排序仍未建立，见[用途验证](usefulness.md)。之后还修复了重复输入导致缓存重放可被计时的问题，见 [v2 验证](replay-validation.md)。

## 四个子任务分别做什么

**这四项是交付步骤，不是四个运行时模块。** 第一项决定做什么，第二项规定规则，第三项交付可执行任务，第四项接入已有系统。

| 子任务 | 要交付的具体东西 | 谁使用、实际发挥什么作用 | 当前状态 |
| --- | --- | --- | --- |
| **① 选定第一批任务和复用方案** · [#334](https://github.com/InferMatrixLab/InferRSI/issues/334) · [详细说明](01-research.md) | 论文/开源对照、任务选择、复用和适配决定 | 开发者据此确定先做哪几题、复用哪些设计，以及当前硬件范围 | 调研与方案已完成，范围待维护者接受 |
| **② 规定任务怎样提交、运行和判定** · [#335](https://github.com/InferMatrixLab/InferRSI/issues/335) · [详细说明](02-contract.md) | 统一任务格式、候选入口、check/profile/measure 接口和版本记录 | Workbench 与评估工具读取同一题目和裁判；题目或源码变更后不能继续当作原比较 | 已实现共享接口和内容冻结 |
| **③ 把第一批任务做成可执行的包** · [#336](https://github.com/InferMatrixLab/InferRSI/issues/336) · [详细说明](03-tasks.md) | Softmax、RMSNorm CPU 任务；每题带输入、基线、独立参考答案和测量规则 | Agent 有明确修改对象，工具有真实可运行的正确性、诊断和测量任务 | 已实现并实测；可靠性能排序未建立 |
| **④ 接入现有 RSI，并验证结果能被使用** · [#337](https://github.com/InferMatrixLab/InferRSI/issues/337) · [详细说明](04-integration.md) | Workbench 绑定、正式两臂产物 adapter、复现入口和证据记录 | 现有实验流程执行任务；两臂分别交付实现，由同一裁判检查并保留证据 | Workbench、底层 verifier、正式 SkillEval 正确性产物入口已实现；真实技能收益和性能排序仍未完成 |

## 放在我们 RSI 的哪里

同一套任务服务两种不同的比较：

| RSI 要回答的问题 | 现有调用者 | #252 的作用 |
| --- | --- | --- |
| 这个引擎实现是否正确、有可验证的改进？ | 主 Agent + Workbench | 提供共同工作负载、独立正确性检查和测量规则 |
| 新 skill/知识是否帮助 Agent 产出更好的实现？ | SkillEval 两臂比较；后续衔接已有改进流程 | 两边产出的实现使用同一套任务和裁判，不随技能条件更换答案 |

第一条路径已有实际执行。第二条现已增加 `skill_eval_compare` 的正式产物交接：两臂分别交付 `implementation.py`，候选在隔离进程运行，父进程以共享 oracle 检查，报告重验留存源码。接入方法及平台验证边界见[正式接入说明](formal-integration.md)；尚未比较旧/新技能对真实 Agent 交付的影响。完整调用关系和分层验收见 [RSI 接入审计](rsi-integration.md)。

当前由主 Agent 决定下一步尝试什么；任务包决定要算什么、怎样检查和测量。Optimization Search Policy 的提案讨论如何选择下一次尝试，本次没有实现该策略。Profiling 是独立诊断，不冒充速度比较。#252 提供可调用的评测操作，不负责强制主 Agent 遵守整个流程或另建搜索控制器。

## 参考 AMD 项目时具体学什么

之前调研的 AMD 项目是 [AgentKernelArena](https://github.com/AMD-AGI/AgentKernelArena/blob/47c2658a07efc7c2c0f72751781a5b5690471b0b/README.md)。它明确描述：给 Agent GPU 优化任务，在工作区产出实现，由独立 evaluator 检查、计时并产生结果；外部系统负责训练或策略更新。

本次借鉴它的[任务契约](https://github.com/AMD-AGI/AgentKernelArena/blob/47c2658a07efc7c2c0f72751781a5b5690471b0b/docs/how-to/add-task.md)：明确计算语义、可编辑实现、性能基线、正确性参考、工作负载和评测操作。我们把这层能力接到已有 InferRSI；当前交付范围是共享任务及其接口，不等同于 Arena 完整的 GPU/Agent 执行平台。

## 怎么开始使用和检查结果

运行 `inferrsi benchmarks list`、`show rmsnorm-cpu`，将示例候选复制成独立 `implementation.py`，再按[使用文档](../../engineering-benchmarks.md)执行 `check`、`profile` 和 `compare`。共享接口优先，硬件尚未确定，所以目前只支持明确的 CPU 子集。

正式两臂入口的当前软件验证见[接入与实际 CI 记录](formal-integration.md#已执行的软件验证)：49 项通过、无跳过，包含 5 个真实 Linux sandbox 案例。原 Workbench 测量证据见 [v2 协议验证](replay-validation.md)；历史证据见 [v1 集成记录](validation.md) 和 [v1 用途对照](usefulness.md)。本地测试、组件实现、正式系统接入与维护者验收分别记录。GPU/NPU、通信/容量任务、真实 agent/skill/search 收益和可靠性能排序均不能由当前 CPU 结果代替。

## 跟踪与范围

实现及文档在 [Draft PR #338](https://github.com/InferMatrixLab/InferRSI/pull/338)，四个子任务保持打开。原生父子关系写入受账号权限限制，目前通过相互引用和父任务索引追踪。

初始基线为 `663f3b327998526a13aa31e72ad729025c18983c`，工作分支为 `codex/issue252-engineering-benchmarks`。本地实施与提交依据为用户的明确委托；这不等价于维护者已接受整个 #252。父 Issue 的 [Search Policy RFC](https://github.com/InferMatrixLab/InferRSI/issues/252#issuecomment-6495138306) 按[维护者范围意见](https://github.com/InferMatrixLab/InferRSI/issues/252#issuecomment-6495720922)保持独立。
