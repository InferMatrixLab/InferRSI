# 子项 02：共享任务接口

## 理解

任务包负责题目事实。消费者负责执行组织或 agent 对照。任务接口不应依赖硬件最终选择，也不应承担搜索调度。

## 计划

- 用版本化 JSON manifest 记录任务、SearchSpace 关联、来源、环境、输入、可编辑范围、oracle、单位、计时边界与局限。
- 用内容哈希冻结包、grader 和候选；任务改变后不得继续冒充原比较。
- 暴露 correctness、measurement、diagnostic 三个操作。实际命令仍由现有执行器运行。
- 将真正的 A/B 比较转成现有 RunSpec；不给诊断填假 baseline。
- 为路径、格式、未支持环境、非有限指标和漂移编写有实际失败意义的检查。

## 验收

同一包身份被两个消费者使用；修改冻结输入后被拒绝；缺失环境不记成功。真实运行和安装包验证见 validation.md。

## 已实施

代码在 `src/inferrsi/harness/benchmarks/contract.py`，CLI 入口为 `inferrsi benchmarks`。

| 对象 | 实际字段或操作 | 用途 |
| --- | --- | --- |
| TaskPackage | schema_version、adapter、source、environment、candidate、oracle、measurement、workloads、coverage | 消费者读取同一份题目事实 |
| 冻结身份 | task_sha256、grader_sha256、candidate_sha256、runtime_sha256 | 记录本次真正使用的包、实现和解释器/NumPy 版本 |
| 单次操作 | check、measure、profile | 都生成结构化结果，只有 measure 提供性能指标 |
| Workbench 绑定 | runspec(candidate, repo, output_dir, repetitions, max_minutes, min_improvement_pct) | 使用已有 AB/BA、快照、截止时间和报告 |
| 工程评估绑定 | grade_artifact；skill_verifier.task_descriptor | 用实际实现与独立 oracle 生成 SkillEval checks |

选择 JSON 是为了保持核心包零第三方依赖并便于命令快照。任务包描述题目，不保存密钥或用户运行配置。执行预算和增益门槛仍由 CLI/Python 调用方提供。

首个 adapter 明确限定 CPU/NumPy/float32；未知后端直接拒绝。未来 backend 实现新 adapter，不改变上述消费者接口。当前没有承诺任意任务 manifest 都能执行，也没有提供空的通信/显存适配。

真实 payload 仍由已有 `execute_trial/execute_command` 运行，独立 worker 仅执行一道题。`profile` 不需要 RunSpec，`compare` 才使用 RunSpec。保留缺依赖、超时、候选/任务漂移等失败路径。哈希冻结不是恶意代码隔离。
