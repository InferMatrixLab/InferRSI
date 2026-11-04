# 子项 04：接入现有 RSI，并验证结果能被使用

**这项工作的交付是调用链和实际证据：让现有 Workbench 执行任务，让现有 verifier 按同一题目检查实现，并明确这些结果支持哪些决定。**

本轮以 [NPU RMSNorm](npu-pilot.md) 为试点验收对象：真实 NPU 基线、profiling、候选、独立检查、A/A 与性能比较必须在同一条证据链中。已有 CPU Workbench 与正式 SkillEval 结果保持历史身份；正式 SkillEval NPU 产物隔离尚未建立，不能因设备任务能在 Workbench 运行就宣称该能力完成。

| 要说清楚的问题 | 本子项的答案 |
| --- | --- |
| 具体做什么 | 把任务操作绑定到既有执行、比较、验证和报告入口，实际运行正确与错误候选 |
| 交付什么 | NPU Workbench RunSpec 绑定、真实设备演练和结果记录；保留已有 CPU 正式产物路径 |
| 谁使用 | 主 Agent 的引擎优化流程、评测开发者、PR 评审者 |
| 实际作用 | 工作台能够执行比较并保留证据；错误实现被共同裁判拒绝；结果可供 RSI 决定保留、放弃或继续诊断 |
| 当前状态 | CPU 接入已有；NPU Workbench 演练与性能资格为当前实施目标，设备结果待单独记录；真实技能收益未测 |

例如主 Agent 交付一个候选后，可以检查它、查看 profile、取得比较证据。要证明新技能让 Agent 更好，还需要旧/新技能各自产出实现的正式两臂实验；预先写好的候选回放不能替代它。

## 流程也是交付内容

本子项要交付的是能够使用任务、得到结果并据此行动的接入流程。区分以下三层，不能把其中一层完成写成全部完成：

- **单次实验的执行与验收：** 固定比较条件、检查实际实现、测量、留存结果，交给现有 Workbench 或 SkillEval 消费。这是 #252 必须提供并验证的接入。
- **主 Agent 的完整使用过程：** 从目标开始，运行基线和 profiling，提出假设，修改实现，检查与比较，记录保留、放弃或证据不足的理由。需要通过实际演练验证，而不仅是画流程图；当前还没有完整闭环验收。
- **自动搜索策略：** 程序选择下一种改法、分配多轮预算、决定何时停止或接受候选。这类决策需与独立的 [Optimization Search Policy 提案](https://github.com/InferMatrixLab/InferRSI/issues/252#issuecomment-6495138306)对齐，提案本身也不负责模型生成候选。本次为其提供可消费的结果；不将该提案默认为已经实现，也不把它悄悄并入 #252 的验收范围。

### 从哪里开始，以及每一步由谁做

下表描述需要讲清并演练的使用过程，最后一列单独记录当前实现，不能据表中步骤推断已有自动编排器。

| 步骤 | 谁做、交出什么 | 当前实现与待补项 |
| --- | --- | --- |
| 1. 明确目标和验收依据 | 主 Agent 根据目标项目确定输入、环境、指标、质量约束及预算；适用时复用内置题包 | 内置题可加载；已有通用 Workbench 可接外部命令。尚无自动从用户目标生成合格任务的能力 |
| 2. 准备比较条件 | 调用者在搜索前固定基线、验证规则和工作负载；每个候选有独立身份 | 复用题包身份和执行快照，NPU 需记录设备/运行时。普通 `plan` 仅预览，不等于保存了冻结的 campaign |
| 3. 运行基线并 profiling | 主 Agent 调用对应环境工具，保留诊断并说明改法依据 | 本轮需要真实 CPU/NPU profile；CPU 旧产物不替代。没有强制 Agent 先诊断再修改 |
| 4. 提交并检查实现 | Agent 修改允许范围；工具实际运行并独立检查产物 | NPU 先执行已审核可信源码；正式 SkillEval 隔离路径仍限受支持的 CPU 任务 |
| 5. 测量并报告 | Workbench 在声明的比较条件下运行、保留原始样本和结论 | 复用 AB/BA、快照和报告；本轮需验证 NPU 同步计时及 A/A，可靠性能资格待实测 |
| 6. 使用结果 | 主 Agent 引用证据解释保留、放弃或继续诊断；下一候选重新标识 | 现有报告可供使用，已有部分用途对照；未完成真实 Agent 全链路演练，没有程序化跨轮次搜索/停止控制 |

用户目标不在题库时，第一步使用目标项目自己的 benchmark 和测试，通过现有 `inferrsi run` 的 baseline/candidate/validation 命令接入 Workbench，不需要先扩充题库。缺少质量检查或可信测量时，应补齐对应实验条件；通用 runner 无法判断测试是否充分代表真实业务。当前具体任务 adapter 不能直接承担任意模型或服务的适配。

### 流程怎样约束结果，而不是只提醒 Agent

现有程序已检查任务/产物身份漂移、缺失验证和不完整执行；内置 NumPy worker 先检查正确性，错误实现不产生可用于选择的性能指标。**通用 Workbench 的外部命令路径不能因此被描述为同一个先检查再计时的执行顺序**：它当前在测量后运行独立 validation，并由最终评价拒绝无效结果。

尚无程序强制宿主 Agent 按“profile → 假设 → 修改”顺序行动，也没有完整优化轮次的资格检查。后续若增加流程约束，应在既有入口校验证据和声明的完成条件：缺少该实验要求的诊断或验收，不得记录成完整优化成功。不能仅在提示词里写了顺序，就声称所有 Agent 都会遵守。

本子项当前 NPU 验证需要保留一条可复查的演练链：诊断依据、候选修改、独立检查、比较结果、主 Agent 的决定。至少证明错误候选被拒绝、证据不足不会被当作改进，以及最终结论只覆盖实际验收的目标。如果融合候选是预先选定的 authored control，应如实记录，不能写成 Agent 从 profile 自主发现。该演练与真实 skill 收益实验、目标服务端到端验收分别记录。

## 理解

只有 schema 和几道题并不能完成 #252。需要证明同一任务包能用于现有 Workbench 和工程评估；该证明不等价于 agent 获益实验。

[RSI 接入审计](rsi-integration.md)区分早期的 `run_trial/verifier` 低层接线与后续[正式 CPU 两臂接入](formal-integration.md)：`engineering-benchmark-v1` 复用 `skill_eval_compare` 的冻结、产物留存与配对报告，使用共享 oracle 在隔离进程外检查候选实际输出。该 CPU 边界不自动支持 NPU；`skill_eval_improve` 仍不支持这些公开 development 任务，系统收益仍需要真实受控 Agent 实验。

## 计划

- Workbench 接入复用 run_experiment、AB/BA、超时、源快照、结果和报告。
- 离线工程评估接入复用现有 SkillEval 的独立 checks/verdict 消费契约，明确本地 authored control 与真实 agent 输出的区别。
- 用 NPU 正确、错误、同码及融合候选验证实际运算、裁判与测量资格；改变冻结文件时拒绝沿用原比较。
- 保留真实 CPU/NPU profile 与原始结果，检查来自设备执行而非预制分数。
- 验证非 editable wheel 安装，以及现有相关回归；最终完整测试结果如实记录。

## 验收

当前 NPU 验收以真实 Workbench 演练为边界：错误候选没有可用性能证据，缺失 device profiling 不冒充已有诊断，同码噪声不自动成为改进。用户授权了本轮 NPU 执行；这不代表付费模型、正式 SkillEval NPU 隔离或真实 Agent 收益已验证。既有 CPU 两消费者的一致性仍按原软件记录保留。

## 已有 CPU 软件接入与历史证据

- `inferrsi benchmarks plan/compare` 生成并执行真正的既有 RunSpec；不改原 runner 的统计或阶段规则。
- `grade_artifact` 将独立正确性结果转成既有 SkillEval checks 结构。
- `skill_verifier.py` 接入现有 `skill_evaluation.run_trial`，任务描述锁定 controller 审核后的保留产物，答复只提交该产物哈希。
- 后续 `engineering-benchmark-v1` 正式 adapter 接入 `skill_eval_compare` 和 `skill_eval_local`，冻结题包/两臂 skill、留存真实 `implementation.py`、隔离运行候选、在父进程复用 oracle，并在报告中重验；方法与平台记录见[正式接入说明](formal-integration.md)。
- `tools/engineering_benchmark_validate.py` 冻结任务和候选，运行两个真实任务、CPU profile、AB/BA，再通过真实 SkillEval trial 处理正确/错误的 authored control。没有生成模型请求，也没有伪造 token 使用。
- `tests/check_installed.py` 检查 wheel 中的任务数据、许可和源码；新增回归覆盖真实子进程与失败路径。

消费链为“同一题目与 oracle → Workbench 性能比较 / SkillEval 独立正确性验证”。Workbench 和早期离线 verifier 执行已审核可信源码；正式两臂 adapter 接收真实产物，复用既有 bubblewrap 边界，仅让候选计算在子进程运行，参考答案留在父进程。它隔离产物 replay，不自动认证或限制生产者 Agent 的全部权限。是否由技能帮助产出更好代码，需要真实 Agent、匹配预算和对照条件的实验。

CPU 运行方法和数据目录说明见 [使用文档](../../engineering-benchmarks.md)，已有 CPU 协议结果见 [v2 验证](replay-validation.md)。早期安装包检查和 v1 集成结果另存于[历史验证记录](validation.md)。当前 NPU 演练的接口、步骤和验收矩阵见 [NPU 试点](npu-pilot.md)。

补充[实际工程用途对照](usefulness.md)把预先固定的 no-epsilon、einsum 和 unchanged 实现接入同一任务，证明普通冒烟漏检会被完整任务拒绝。它也暴露了计时稳定性限制：同一代码的比较出现大幅差异，可靠性能排序仍待后续协议验证，不能作为已完成的验收项。
