# v2：按 RSI 测量边界修复输出重放

当前 RSI 的候选比较要求测量实际实现的计算，不能让最终输出缓存冒充优化。[PR review](https://github.com/InferMatrixLab/InferRSI/pull/338#discussion_r4456416093) 指出 v1 预检、预热和计时复用同一输入，正确的 memoizing 实现可能只在预检计算一次。这是任务测量语义的缺陷，与有没有 CPU/GPU、是否有独立 oracle 无关。

## 修复与版本边界

- 适配器更新为 `numpy-axis1-v2`；每个任务显式声明 `seeded-distinct-per-call-v1` 输入协议和五个计时 case。全零输入仍检查正确性，但不计入性能分数。
- 执行前生成全部输入、逐输入独立 oracle 和预定顺序。输入对象一直保留，字节不与预检、预热和其他采样重复；baseline 与 candidate 使用同一序列。
- `check`、`measure`、`profile` 检查同一序列。结果区分计划的 `input_sequence` 与实际 `executed_calls`，每个计时样本绑定输入摘要；失败只留下实际执行的前缀。
- 对按 id/完整内容缓存的正确实现，不禁止代码写缓存，而是验证本序列没有命中旧结果。按 shape/layout 直接重放旧答案的实现会被变化输入拒绝，且不能输出性能指标。
- 输入和 oracle 生成在计时之外；计时仍只包围 compute。该机制不提供恶意代码隔离或隐藏测试，公开输入仍可能被过拟合。

任务、grader 身份和指标的五 case 聚合均已变化。v1 的 [集成记录](validation.md) 和 [用途对照](usefulness.md) 完整保留，不改写、不拼入 v2 的分数。正确性与性能排序仍分别判断。

## 实际验证

2026-11-03（UTC），Windows / Python 3.11.18 / NumPy 2.4.6。针对 v2 的专项回归 **40 项通过**，包括真实 baseline/candidate、缓存命中、旧输出重放、逐次输入配对、边界协议、漂移、超时、Workbench 和 SkillEval verifier。另行运行的 CLI catalog 和 SkillEval 相关回归也通过；Ruff 和 diff 检查通过。

开发时首轮回归暴露了 `SeedSequence` 的 NumPy 命名空间错误，修正为 `np.random.SeedSequence` 后完整重跑通过；未把首轮失败归因于环境或既有基线。日志保留在仓库外的本地 outputs 中。

随后单独执行现有复现工具：

```bash
python tools/engineering_benchmark_validate.py \
  --repo <checkout> --output-dir <new-output> --repetitions 3
```

这是固定示例候选的协议/消费者验证，不是新的性能优化搜索。工具在执行前冻结任务、候选及 RunSpec；实际原始目录名为 `inferrsi-252-replay-v2-validation`。

| 检查 | Softmax CPU | RMSNorm CPU |
| --- | --- | --- |
| 正确性范围 | 6 个基础 case + 35 次变化输入调用 | 相同 |
| 正确实现独立断言 | 164 项通过 | 164 项通过 |
| 正确/全零错误产物在 SkillEval | PASS / FAIL | PASS / FAIL |
| 错误测量 | 拒绝，无可用指标 | 拒绝，无可用指标 |
| 实际 Workbench trial / 计时样本 | 6 / 150 | 6 / 150 |
| 独立 profile | 完成 | 完成 |
| 所有消费者 task/grader/runtime 与基础输入 | 一致 | 一致 |
| 计划输入序列与正确实现的实际调用序列 | 一致 | 一致 |
| Workbench 源码完整性 | 通过 | 通过 |

[原始可公开汇总](replay-validation-summary.json) 保留每次变化输入的摘要及身份、数量和原始 verdict，未包含私人路径。完整原始计时、日志和 profile 仍在本地。两次 Workbench 描述性 verdict 都为 PASS，未将其解释为可靠性能提升；本次没有完成 v2 同码噪声资格验证，也没有建立统计显著性。

## 对 RSI 的实际含义

现在普通 id/content 缓存不能因预检复用而得到重放时间，错误的旧输出也不能成为优化证据。这提高了 Workbench 和离线 verifier 共同消费的任务语义可靠性。

这仍不是“RSI 已经自动变好”的证据。可靠性能排序、正式 SkillEval 两臂产物交接、真实技能/搜索收益及目标硬件验收仍未完成；调用关系及下一步验收沿 [RSI 接入审计](rsi-integration.md) 组织，不另建执行器或搜索控制器。
