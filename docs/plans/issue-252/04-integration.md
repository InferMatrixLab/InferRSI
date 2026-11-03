# 子项 04：消费者接入与实际用途验证

## 理解

只有 schema 和几道题并不能完成 #252。需要证明同一任务包能用于现有 Workbench 和工程评估；该证明不等价于 agent 获益实验。

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
- `tools/engineering_benchmark_validate.py` 冻结任务和候选，运行两个真实任务、CPU profile、AB/BA，再通过真实 SkillEval trial 处理正确/错误的 authored control。没有生成模型请求，也没有伪造 token 使用。
- `tests/check_installed.py` 检查 wheel 中的任务数据、许可和源码；新增回归覆盖真实子进程与失败路径。

消费链为“同一 task.json 和 grader → Workbench 性能比较 / SkillEval 独立正确性验证”。后者是离线保留产物交接，不是在线 agent 写代码的新 sandbox。是否由技能帮助产出更好代码，需要未来真实 agent、匹配预算和对照条件的实验。

运行方法和数据目录说明见 [使用文档](../../engineering-benchmarks.md)，最终结果见 [验证记录](validation.md)。
