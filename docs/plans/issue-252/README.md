# #252 共享工程基准交付计划

本地实施依据为用户在 2026-11-03 的明确委托。重新读取的 [Issue 正文](https://github.com/InferMatrixLab/InferRSI/issues/252) 与全部两条评论仍未记录维护者对首批子集的验收。本目录记录可供维护者评审的实现与证据，不代替项目接受或关闭 Issue。

基线为 `663f3b327998526a13aa31e72ad729025c18983c`。实现位于独立分支 `codex/issue252-engineering-benchmarks`，不改变其他工作区。

## 要解决的实际问题

Workbench 和工程评估需要对同一个候选实现回答两个问题：计算是否正确，以及指定工作负载下测得什么性能。任务语义、输入、参考答案和计时规则应只有一份。搜索策略决定下一步尝试什么，消费者不能各自复制或修改题目答案。

本次将这个模块命名为 **Engineering Benchmarks（工程基准）**。这是本次实现的命名，尚非维护者已接受的架构决策。

## 子项与执行顺序

| 子项 | 要交付什么 | 如何证明有用 |
| --- | --- | --- |
| [01 调研和决策](01-research.md) | 一手论文、固定版本源码对照，选择及不选择的理由 | 每项决策对应接口、任务或验证行为 |
| [02 共享接口](02-contract.md) | 任务包读取、身份冻结、命令生成、独立诊断 | 错误配置和任务漂移会被拒绝，能生成现有 RunSpec |
| [03 首批任务](03-tasks.md) | 少量真实算子任务，独立 oracle，基线和候选接口 | 正确实现通过，典型错误被抓到，实际执行并计时 |
| [04 消费者与验收](04-integration.md) | Workbench 和离线工程评估共享同一任务，复现入口和结果 | 真正调用现有执行器/评估器，保留原始样本、失败记录和诊断 |

硬件尚未确定，按用户的“共享接口优先”约束先验证本机 CPU 子集。加速器适配不能用 CPU 结果冒充。通信、分布式拓扑、显存容量、GPU/NPU 计时不属于这个首批子集。

## 与评论中的 Search Policy 的关系

[RFC](https://github.com/InferMatrixLab/InferRSI/issues/252#issuecomment-6495138306) 提出了候选卡、准入、成本层级、轮次、负结果和停止规则。[维护者回复](https://github.com/InferMatrixLab/InferRSI/issues/252#issuecomment-6495720922) 明确要求保持它与 #252 独立，并修正增量贡献、诊断记录、搜索耗尽三个问题。本次交付任务和 oracle，不顺带实现这套搜索控制器。

Profiling 保留为独立诊断操作，与 correctness 和配对 performance 分开。它不伪造 baseline，也不产生性能胜负。本次 CPU profiling 只能解释 CPU 调用；设备 trace 由未来环境适配器提供。

## 完成标准

- 每个子项有方案、理由、实际改动和验证记录。
- 首批任务可从安装包读取，离开源码目录仍可使用。
- 冻结任务、grader、候选和输入身份，保留失败与缺失状态。
- 测量明确单位、边界、预热、重复与样本，不用文档或 CI 绿色代替真实任务运行。
- 证明接口复用和错误识别；不宣称技能/agent/search 的收益、GPU/NPU 正确性或服务加速。
- 正式 Issue 验收、维护者同意、独立 review 与本地实施完成分别报告。

最终结果见 [验证记录](validation.md)。

## 当前交付

公开子任务分别为 [#334 调研与决策](https://github.com/InferMatrixLab/InferRSI/issues/334)、[#335 共享接口](https://github.com/InferMatrixLab/InferRSI/issues/335)、[#336 首批任务](https://github.com/InferMatrixLab/InferRSI/issues/336)、[#337 消费者与验证](https://github.com/InferMatrixLab/InferRSI/issues/337)。四项均引用父任务 #252，保持打开供维护者评审与验收。当前提交账号无法写入原生父子关系，需维护者补充。

四个子项的本地实施已完成。已交付共享 TaskPackage、两个真实 CPU 算子任务、独立正确性与 profiling、Workbench/SkillEval 接入，以及可复现实测工具。使用入口见 [工程基准文档](../../engineering-benchmarks.md)。

建议先读本页理解范围，再读 01 看方案理由。要开始使用时，运行 `inferrsi benchmarks list` 和 `show softmax-cpu`，复制任务包中的示例候选到独立 implementation.py，按使用文档执行 check、profile、compare。修改任务协议应创建新比较，不能沿用旧身份。

这完成的是用户委托的首批共享接口和 CPU 子集；#252 的维护者验收、目标硬件选择与后续覆盖仍单独记录，不在本地冒充已接受。
