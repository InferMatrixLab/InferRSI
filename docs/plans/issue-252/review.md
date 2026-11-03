# #252 本轮审查记录与阅读入口

本轮继续审查 PR #338，并准备供首次接触 InferRSI 的读者使用的[完整导读](walkthrough.md)。结论是：发现并修复一个 CLI 失败状态传播缺陷，补齐公开可检查的既有 v2 样本/profile，修正文档的历史版本指向。PR 仍保持 Draft；这些工作不代表维护者已经接受范围或批准合并。

## 审查对象和覆盖

审查起点为 `ac03ae23ce0bb5864a55c2c97d5f3d8d3b550d39`，对照原始基线 `663f3b327998526a13aa31e72ad729025c18983c`，共 42 个变更文件。审查分工与本轮修复复核均在同一工作树进行；新导读、样本导出和修复属于本轮增量。

| 范围 | 具体检查 | 结果 |
| --- | --- | --- |
| 任务契约、worker、NumPy 评测、两套任务包 | manifest 拒绝路径、输入上界、身份冻结、独立 oracle、axis=1/4D/跨步布局、变化输入、逐调用检查、profile/计时边界 | 未发现额外需修复缺陷；原 40 项专项测试独立重跑通过 |
| consumers、离线 verifier、CLI、接线和打包 | 真实 executor/RunSpec/run_trial 接入、结果与状态、包内资源、验证脚本 | 发现 R1；其余未发现新的实质问题 |
| 文档与证据 | 四项交付含义、RSI 调用关系、历史版本、声称完成的范围、样本可检查性 | 发现 R2/R3 并修正；保留正式集成与验收缺口 |
| 本轮 R1 修复 | 独立复核 diff、读取真实状态文件、退出码与既有 run 命令一致性 | 修复复核未发现新问题；新增实际执行回归通过 |

“未发现”描述本轮检查结果，不是对所有输入、设备或恶意源码的保证。代码入口仍限定已审核可信实现。

## 已处理的问题

### R1 · P2：compare 在失败时仍返回退出码 0

**触发：** 通过 `inferrsi benchmarks compare` 运行返回全零的错误 Softmax 候选。Workbench 实际记录 `state=failed`、`verdict=INCONCLUSIVE`；旧 CLI 仅返回运行目录和范围信息，最终进程退出码却为 0。

**影响：** 脚本或 Agent 如果以退出码判断成功，会把失败比较误当成功。这与已有 `inferrsi run` 的退出约定不一致。

**修复：** benchmark CLI 读取并原样返回保留的 `status.json`；顶层 CLI 按实际 verdict 返回 PASS=0、FAIL=1、INCONCLUSIVE=2。不修改 Workbench 的判定规则，不把未完成比较改写为数值 FAIL。

**验证：** 三个新回归均执行真实 CLI/Workbench，并检查响应与磁盘状态及 evaluation 一致：

| 情况 | 状态与 verdict | 退出码 |
| --- | --- | --- |
| 正确候选完成比较，但无法达到 100% 延迟下降的测试门槛 | completed / FAIL | 1 |
| 全零错误候选导致测量失败 | failed / INCONCLUSIVE | 2 |
| 极短预算在执行前耗尽 | timeout / INCONCLUSIVE | 2 |

测试中的 100% 和极短预算是为确定性触发分支设置的测试条件，不是性能验收标准。`grade` 对错误产物本身仍可报告正确性 FAIL；不完整的 A/B 比较则是 INCONCLUSIVE。

### R2：v2 可公开记录只有数量和身份，没有原始计时

**影响：** 读者无法从仓库字节复算 300 个样本的聚合或查看 profile。

**处理：** 从原始本地 v2 运行只读导出 [replay-measurements.json](replay-measurements.json) 和两份 [RMSNorm](replay-profiles/rmsnorm-cpu.txt) / [Softmax](replay-profiles/softmax-cpu.txt) profile。保留全部 12 个 trial、300 个样本、逐样本输入哈希、原始 evaluation 与来源哈希；profile 逐字节复制，既有 summary 不改写。不重复运行，不筛除离散值，不声称公开了未附带的完整日志。

**核验：** 样本数、每 case 中位数、trial 指标、Workbench 两侧聚合、输入序列与旧汇总逐项一致。补充材料提高可检查性，不会使原本未建立的测量资格自动成立。

### R3：当前接入文档仍指向历史 v1 验证

**影响：** 读者可能以为当前工具可以生成旧协议的 360 个样本，或将 v1 和 v2 结果合用。

**处理：** 子项②/④指向 v2 记录，历史安装证据单独标明；v1 页面固定到原始实现，说明重放需使用当时的工具、题目和 grader。总览明确主 Agent 作决策，Search Policy 是独立提案。新导读将四个交付步骤与运行时模块分开解释。

## 本轮验证及证据边界

| 检查 | 结果与边界 |
| --- | --- |
| 修复前核心专项重跑 | ac03ae23 上 40 项通过 |
| 修复后专项回归 | `tests/test_engineering_benchmarks.py` 43 项通过，含 3 个实际 Workbench CLI 回归 |
| 顶层 CLI 回归 | `tests/test_cli_catalog.py` 19 项通过 |
| 静态与文档检查 | Ruff、diff 空白检查、本地 Markdown 目标检查通过；证据导出核验通过 |
| 已有 hosted CI | ac03ae23 的 Linux Python 3.10/3.11 full-check 和 installed-package 通过；[运行记录](https://github.com/InferMatrixLab/InferRSI/actions/runs/41672237031)；不将该 CI 结果冒充本轮新提交检查 |
| 历史 Windows 全量 | 3479 passed、51 skipped、56 failure reports；失败在未修改原始基线复现，原运行仍不绿，本轮未重复整个 Windows 全量 |
| 新性能实验 | 未执行。本轮修复不修改输入/oracle/计算/计时行为；真实 CLI 状态分支通过上述回归验证 |

**grader 版本变化必须保留：** `grader_digest()` 对整个 benchmark 目录取哈希，因此修改 `cli.py` 也会改变 grader。旧 v2 300 个样本始终属于 `0b75b5bbe7fc048293a6c8b4c2e9a35d1cbf63c27b16b420f3f49da3efb57407`；本轮修复后的测试身份为 `34928e6956f54aab565a4d48ea68f74ee72aa91578f8ce63fd013934c71b4d55`。不能把旧样本重新绑定成新提交的运行记录。

外部 reviewer 在 [r4459426716](https://github.com/InferMatrixLab/InferRSI/pull/338#discussion_r4459426716) 确认了 ac03ae23 的缓存重放修复；该确认明确只覆盖这一问题，不能描述为完整 PR approval。本轮独立分工 review 也不替代维护者的项目验收。

## 仍需分别解决的事项

- 首批 CPU 任务及接口范围的维护者 accept/revise/reject 决定；原生父子 Issue 关系和标签由有权限的维护者协调。
- 同码噪声与可分辨性能排序；现有 Workbench 的描述性 PASS/FAIL 不足以支持稳定优化收益。
- `tools.skill_eval_compare` 的正式任务适配、产物交接与受支持隔离；当前只是底层保留产物 verifier。
- 真实旧/新 skill 的受控 Agent 实验及资源成本；固定作者产物不能证明技能收益。
- 硬件确定后的同步、计时、真实负载与设备/服务验收。

下一步工作沿已有 RSI 入口推进，详见 [接入审计](rsi-integration.md)。四个子 Issue 保持打开；本轮不作完成、合并或可靠性能提升的声明。
