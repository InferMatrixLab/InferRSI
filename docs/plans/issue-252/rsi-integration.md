# #252 在现有 InferRSI 中怎样发挥作用

验收起点是“谁调用任务包，拿结果作什么决定”。两个算子能运行、两个底层消费者复用 oracle，只完成组件级验证。它们尚不能证明 InferRSI 的优化者因此变得更有效。

## 两条现有路径，共用一份任务定义

| 路径 | 变化的对象 | #252 的职责 | 结果影响的决定 |
| --- | --- | --- | --- |
| 引擎优化：主 Agent → Workbench | 引擎的代码或配置 | 定义适用的任务、输入、oracle、诊断与测量边界 | 该实现是否正确；是否有足够证据保留它；下一轮需要什么诊断 |
| 优化者评估：SkillEval | skill、知识或 harness 的候选版本 | 用相同任务和独立 oracle 检查两边实际产出的实现 | 新指导是否帮助完成任务；质量和资源成本如何变化 |

两条路径中改变的对象不能混淆。引擎代码变快，不等于某个 skill 有效；skill 版本比较也不能通过替换任务或判分规则制造进步。整体 agent/harness 收益仍由 #248 的受控实验回答，#249 负责并行候选搜索的相关范围。

已有 [harness-improvement controller](../../harness-improvement.md) 可以消费其支持的 SkillEval grades，进行 development 选择、重跑和一次 holdout 接受/拒绝。本次 benchmark 不能假定已经接入它。不要为接入 #252 再造一套总控制器或执行平台。

## 对照真实入口审计当前状态

| 入口 | 现在已经接通什么 | 尚未接通什么 |
| --- | --- | --- |
| `benchmarks plan/compare` → `TaskPackage.runspec` → `run_experiment` | 同一任务生成既有 RunSpec，由 Workbench 执行配对比较并保留证据 | 自动从用户目标/profile 选出适用任务；服务与目标硬件验收 |
| `benchmarks check/profile/measure` | 分开的数值校验、CPU 诊断、测量操作 | 强制宿主 Agent 按整个优化流程执行 |
| `skill_verifier.task_descriptor` → `skill_evaluation.run_trial` | 对 controller 已审核的保留实现运行真实 verifier；答案提交该实现的 SHA | Agent 根据不同技能实际产出两份实现的比较 |
| `tools.skill_eval_compare` | 已有冻结两臂、模型/预算、产物与报告机制 | 新 benchmark descriptor 尚未成为正式支持的 adapter；现有 engineering adapter 限定 parser 任务及隔离执行 |
| `tools.skill_eval_improve` | 已有面向支持的离线 audit 任务的选择、重跑和 holdout 流程 | 共享工程基准尚未接入该控制器的任务/grader 契约 |

依据为 [CLI 适配](../../../src/inferrsi/harness/benchmarks/cli.py)、[保留产物 verifier](../../../src/inferrsi/harness/benchmarks/skill_verifier.py)、[SkillEval 比较入口](../../../tools/skill_eval_compare.py)、[现有 engineering adapter](../../../src/inferrsi/harness/skill_eval_engineering.py) 和 [改进入口](../../../tools/skill_eval_improve.py)。主 Agent 的调查与代码修改职责见[现有插件入口](../../../plugins/inferrsi/skills/inferrsi/SKILL.md)。

## 一次引擎优化中应该怎样使用

1. **从目标和基线 profile 开始。** 主 Agent 明确模型、硬件、工作负载和质量要求，再确认该任务是否覆盖所需语义、dtype、布局和环境。当前 CPU RMSNorm 任务不能因为名称相同就代表真实 GPU/NPU 服务。
2. **冻结任务与实验条件。** 在候选尝试前固定任务、oracle、输入序列、版本、比较条件和预算。候选只改允许的实现；不同时修改裁判或基线。
3. **利用知识形成可检验假设。** Agent 读取适用技能、论文和历史失败记录，说明该变更如何作用于已观测的瓶颈。CPU cProfile 无法确认的内存瓶颈继续保持未知。
4. **先挡住错误，再测量。** 数值不正确的候选不能获得可用于选择的性能分数。计时必须测到实际计算；预检不能给后续同输入缓存重放预热。测量规则的修改产生新的任务/grader 身份，不重写旧证据。
5. **区分原始报告与优化决定。** 保留 Workbench 原始 PASS/FAIL/INCONCLUSIVE；主 Agent 同时判断证据是否足以支持保留/放弃。若同码对照无法分辨，决策是“测量不足，先修协议”，不能把某次 FAIL 归纳成整个优化机制无效。
6. **记录对下一轮有用的事实。** 保留候选、环境、任务、正确性失败、原始样本及未解决的诊断。经验整理与晋升走现有流程；不从一次算子结果自动推广成服务收益或通用技能。

## 按 RSI 需求补证的顺序

### A. 先使任务适合被优化者消费

要求 oracle 独立、候选修改边界清楚、实际计算不被预检缓存替代、输入在消费者之间配对一致、测量失败不产生可用性能证据。这是 #252/#337 的基础交付，不是另一个 search-policy 项目。

[缓存重放 review](https://github.com/InferMatrixLab/InferRSI/pull/338#discussion_r4456416093) 暴露了这一层的具体缺口，现已通过 [v2 变化输入协议及回归](replay-validation.md)修复。此前的普通冒烟漏检对照证明了正确性检查用途；同码噪声与可靠性能排序仍须单独验证。

### B. 证明结果确实进入优化决定

最小演练应沿已有入口保留“profile → 假设 → 产物 → check → compare → 决策”链，并至少包含：错误产物被拒绝、正确但证据不足的产物不被当作改进、负结果留下适用条件。既有 [RMSNorm 对照](usefulness.md) 提供了部分输入与结果；当前没有程序化的全流程强制或真实 agent 对照，不能据此宣布完整闭环验收。

### C. 再接到已有 SkillEval 两臂入口

沿 `skill_eval_compare` 扩展任务适配与产物交接，保留其冻结、模型/预算一致性、独立 verifier、隔离和日志机制。两边分别接收旧/新 skill（或无/有 skill），各自交付实现，再交给同一任务包判分。

当前可信 CPU worker 不能直接接未经审核的模型代码，也不能代替现有 engineering adapter 的隔离。没有支持的产物执行环境时，应保留未验证状态；换一个 scripted client 只证明通路，不证明技能帮助。

### D. 最后评估优化者本身是否改善

实际 agent 实验要固定任务集、模型、总预算和对照，记录所有尝试、质量、可分辨的性能与资源使用。若用于选择可复用技能，还要有适当的独立验证任务；同一道公开题换一个 seed 不自动等于独立 holdout。先明确新 adapter 支持的范围，再评估能否被既有 harness-improvement controller 消费。

这一层沿 #88/#248 及已有 controller 的职责推进，不把整个搜索控制器、自动知识晋升或服务验收塞进 #252。

## 当前结论

共享任务与底层消费者复用已有实际证据，已补正影响测量语义的输入重放缺陷；端到端 SkillEval 接入、优化者收益和可靠性能排序尚未完成。四个子项的组件实现不能替代这些系统验收。PR 继续作为 Draft 评审，按现有 RSI 接口补齐接入，不把独立题目数量或另建编排系统作为进展指标。
