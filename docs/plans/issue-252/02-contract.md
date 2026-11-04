# 子项 02：规定任务怎样提交、运行和判定

**这项工作的交付是一套共同规则：同一道优化任务交给 Workbench 或评估工具，都使用同一份输入、答案、计时边界和版本。**

| 要说清楚的问题 | 本子项的答案 |
| --- | --- |
| 具体做什么 | 定义任务包字段、候选函数入口、检查/诊断/测量操作和结果身份 |
| 交付什么 | `TaskPackage`、`check/profile/measure` 操作及生成既有 RunSpec 的接口 |
| 谁使用 | Workbench 适配代码、离线 verifier 和后续任务作者 |
| 实际作用 | 一次比较中的题目和裁判固定；源码或规则改变时会被识别，两个调用者不用分别维护答案 |
| 当前状态 | CPU 接口与软件验证保留；本轮增加 NPU 设备语义、同步计时与环境身份，实际资格单独记录 |

NPU RMSNorm 的入口为 `compute(x, weight, *, eps)`，采用二维 contiguous float32 与非全一权重；旧 CPU 题的 `compute(x, *, eps)`、四维 axis=1、无 affine 语义保持原身份。不能因同名算子就混用题目或裁判。接口不决定候选怎么生成。

## 本轮 NPU 契约

[NPU 试点](npu-pilot.md)列出当前目标：独立 adapter 在实际设备上验证输入/输出设备、dtype、数值与输入保持，使用 CPU scalar double / `math.fsum` oracle；数据准备与传输、oracle、校验在性能计时外完成。同步边界必须覆盖实际完成的 NPU 计算。独立 CPU/NPU profile 不进入性能分数。

运行时身份需绑定实际设备与 torch / torch_npu / CANN 版本，不沿用只包含 Python/NumPy 的 CPU 身份。当前命令指纹包含 torch/torch_npu 版本与分配的可见设备；worker 另记录实际型号和 CANN，资格工具检查所有 action/trial/final validation 的实际环境一致。不能把命令指纹单独称为完整硬件资格。任务、候选、oracle、输入和计时规则继续使用共享内容身份；缺依赖、无设备或不支持语义不能回退 CPU。已支持范围及执行证据见[本轮记录](npu-validation.md)。

Workbench 接入先运行已审核可信源码。正式 `engineering-benchmark-v1` 目前只接受已声明的 CPU 任务；NPU 题出现在 catalog 中，不代表正式 SkillEval 具备设备隔离或产物重验能力。adapter 的能力检查必须显式拒绝不支持的组合。

## 理解

任务包负责题目事实。消费者负责执行组织或 agent 对照。共享操作接口保持可复用，具体 adapter 必须声明硬件语义与支持范围，不承担搜索调度。

## 计划

- 用版本化 JSON manifest 记录任务、SearchSpace 关联、来源、环境、输入、可编辑范围、oracle、单位、计时边界与局限。
- 用内容哈希冻结包、grader 和候选；任务改变后不得继续冒充原比较。
- 暴露 correctness、measurement、diagnostic 三个操作。实际命令仍由现有执行器运行。
- 将真正的 A/B 比较转成现有 RunSpec；不给诊断填假 baseline。
- 为路径、格式、未支持环境、非有限指标和漂移编写有实际失败意义的检查。

## 验收

同一包身份被支持它的消费者使用；修改冻结输入后被拒绝；缺失环境不记成功。本轮 NPU 需证明真实设备检查、同步计时和 Workbench 证据，不能由 CPU 消费者测试替代。已有 CPU 变化输入协议见 [v2 验证](replay-validation.md)；早期安装包检查和 v1 运行保留在[历史验证记录](validation.md)，不作为当前 NPU 的执行结果。

## 已有软件接口

代码在 `src/inferrsi/harness/benchmarks/contract.py`，CLI 入口为 `inferrsi benchmarks`。

| 对象 | 实际字段或操作 | 用途 |
| --- | --- | --- |
| TaskPackage | schema_version、adapter、source、environment、candidate、oracle、measurement、workloads、coverage | 消费者读取同一份题目事实 |
| 冻结身份 | task_sha256、grader_sha256、candidate_sha256、runtime_sha256 | 记录实际包、实现与运行时；NPU 需扩充实际设备环境身份 |
| 单次操作 | check、measure、profile | 都生成结构化结果，只有 measure 提供性能指标 |
| Workbench 绑定 | runspec(candidate, repo, output_dir, repetitions, max_minutes, min_improvement_pct) | 使用已有 AB/BA、快照、截止时间和报告 |
| 工程评估绑定 | grade_artifact；skill_verifier.task_descriptor | 用实际实现与独立 oracle 生成 SkillEval checks |

选择 JSON 是为了保持核心包零第三方依赖并便于命令快照。任务包描述题目，不保存密钥或用户运行配置。执行预算和增益门槛仍由 CLI/Python 调用方提供。

已有 `numpy-axis1-v2` 明确限定 CPU/NumPy/float32；本轮 NPU 使用独立 adapter，不改变上述操作分工。未知后端直接拒绝。没有承诺任意任务 manifest 都能执行，也没有提供空的通信/显存适配。

真实 payload 仍由已有 `execute_trial/execute_command` 运行，独立 worker 仅执行一道题。`profile` 不需要 RunSpec，`compare` 才使用 RunSpec。保留缺依赖、超时、候选/任务漂移等失败路径。哈希冻结不是恶意代码隔离。
