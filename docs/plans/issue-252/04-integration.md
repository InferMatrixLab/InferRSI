# 子项 04：接入现有 RSI，并验证结果能被使用

**这项工作的交付是调用链和实际证据：让现有 Workbench 执行任务，让现有 verifier 按同一题目检查实现，并明确这些结果支持哪些决定。**

| 要说清楚的问题 | 本子项的答案 |
| --- | --- |
| 具体做什么 | 把任务操作绑定到既有执行、比较、验证和报告入口，实际运行正确与错误候选 |
| 交付什么 | Workbench RunSpec 绑定、SkillEval 低层 verifier、正式两臂产物 adapter、复现工具和结果记录 |
| 谁使用 | 主 Agent 的引擎优化流程、评测开发者、PR 评审者 |
| 实际作用 | 工作台能够执行比较并保留证据；错误实现被共同裁判拒绝；结果可供 RSI 决定保留、放弃或继续诊断 |
| 当前状态 | Workbench、底层 verifier、正式 SkillEval 正确性产物交接已实现；真实技能收益与可靠性能排序未完成 |

例如主 Agent 交付一个候选后，可以检查它、查看 profile、取得比较证据。要证明新技能让 Agent 更好，还需要旧/新技能各自产出实现的正式两臂实验；预先写好的候选回放不能替代它。

## 理解

只有 schema 和几道题并不能完成 #252。需要证明同一任务包能用于现有 Workbench 和工程评估；该证明不等价于 agent 获益实验。

[RSI 接入审计](rsi-integration.md)区分早期的 `run_trial/verifier` 低层接线与后续[正式两臂接入](formal-integration.md)：新 `engineering-benchmark-v1` 复用 `skill_eval_compare` 的冻结、产物留存与配对报告，使用共享 oracle 在隔离进程外检查候选实际输出。`skill_eval_improve` 仍不支持这些公开 development 任务；系统收益仍需要真实受控 Agent 实验。

## 计划

- Workbench 接入复用 run_experiment、AB/BA、超时、源快照、结果和报告。
- 离线工程评估接入复用现有 SkillEval 的独立 checks/verdict 消费契约，明确本地 authored control 与真实 agent 输出的区别。
- 用正确、错误、改变冻结文件三种情况验证两端一致性。
- 用实际工作负载保留原始结果和 CPU profile，检查来自真实执行而非预制分数。
- 验证非 editable wheel 安装，以及现有相关回归；最终完整测试结果如实记录。

## 验收

两个消费者共享 task/grader 身份，正确性结论一致；错误候选不能获得可用性能证据；缺失 profiling 不冒充已有诊断。付费模型、生产 SkillEval 执行授权和设备资格不由本次接入改变。

## 已实施

- `inferrsi benchmarks plan/compare` 生成并执行真正的既有 RunSpec；不改原 runner 的统计或阶段规则。
- `grade_artifact` 将独立正确性结果转成既有 SkillEval checks 结构。
- `skill_verifier.py` 接入现有 `skill_evaluation.run_trial`，任务描述锁定 controller 审核后的保留产物，答复只提交该产物哈希。
- 后续 `engineering-benchmark-v1` 正式 adapter 接入 `skill_eval_compare` 和 `skill_eval_local`，冻结题包/两臂 skill、留存真实 `implementation.py`、隔离运行候选、在父进程复用 oracle，并在报告中重验；方法与平台记录见[正式接入说明](formal-integration.md)。
- `tools/engineering_benchmark_validate.py` 冻结任务和候选，运行两个真实任务、CPU profile、AB/BA，再通过真实 SkillEval trial 处理正确/错误的 authored control。没有生成模型请求，也没有伪造 token 使用。
- `tests/check_installed.py` 检查 wheel 中的任务数据、许可和源码；新增回归覆盖真实子进程与失败路径。

消费链为“同一题目与 oracle → Workbench 性能比较 / SkillEval 独立正确性验证”。Workbench 和早期离线 verifier 执行已审核可信源码；正式两臂 adapter 接收真实产物，复用既有 bubblewrap 边界，仅让候选计算在子进程运行，参考答案留在父进程。它隔离产物 replay，不自动认证或限制生产者 Agent 的全部权限。是否由技能帮助产出更好代码，需要真实 Agent、匹配预算和对照条件的实验。

运行方法和数据目录说明见 [使用文档](../../engineering-benchmarks.md)，当前协议的实际结果见 [v2 验证](replay-validation.md)。早期安装包检查和 v1 集成结果另存于[历史验证记录](validation.md)。

补充[实际工程用途对照](usefulness.md)把预先固定的 no-epsilon、einsum 和 unchanged 实现接入同一任务，证明普通冒烟漏检会被完整任务拒绝。它也暴露了计时稳定性限制：同一代码的比较出现大幅差异，可靠性能排序仍待后续协议验证，不能作为已完成的验收项。
