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
| `tools.skill_eval_compare` | 新增 `engineering-benchmark-v1`：共享题目/两臂 skill 冻结、实际文件留存、隔离计算与父进程 oracle、配对报告重验；支持现有 local stage/capture | 当前仅正确性；真实受控 Agent/skill 收益、性能排序、provider generation 模式未接入 |
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

### C. 接到已有 SkillEval 两臂入口

已沿 `skill_eval_compare` 扩展 `engineering-benchmark-v1`，支持 update 模式的旧/新 skill 两臂，保留冻结、模型/预算、日志与报告。两边分别交付 `implementation.py`，控制器留存实际字节；候选在既有 bubblewrap 边界内计算，父进程使用共享输入与 oracle 独立检查。`skill_eval_local` 也支持 stage/capture；完整使用方法和验证分层见[正式接入说明](formal-integration.md)。

原有可信 CPU worker 仍不能直接接未经审核的模型代码；新 formal adapter 为产物 replay 使用隔离路径，没有宿主回退。当前只输出正确性，不使用候选自报 latency；真实 Agent 执行权限、技能收益和性能排序另行验证。固定作者脚本只证明通路和裁判行为，不能证明技能帮助。

### D. 最后评估优化者本身是否改善

实际 agent 实验要固定任务集、模型、总预算和对照，记录所有尝试、质量、可分辨的性能与资源使用。若用于选择可复用技能，还要有适当的独立验证任务；同一道公开题换一个 seed 不自动等于独立 holdout。先明确新 adapter 支持的范围，再评估能否被既有 harness-improvement controller 消费。

这一层沿 #88/#248 及已有 controller 的职责推进，不把整个搜索控制器、自动知识晋升或服务验收塞进 #252。

## 当前结论

共享任务与底层消费者复用已有实际证据，输入重放缺陷已修复；后续正式两臂 adapter 也已实现产物交接与独立正确性检查。真实 Agent/skill 收益、可靠性能排序、provider generation 和改进控制器接入仍未完成。具体平台软件对照结果见正式接入记录，不能用接口实现代替系统收益验收。PR 继续作为 Draft 评审，不另建编排系统。
