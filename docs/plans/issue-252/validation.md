# #252 本地验证记录

本页保留 **v1 历史运行**（六个计时 case、重复输入）的原始记录，不能代表后续 v2 变化输入协议。当前 RSI 接入边界见 [接入审计](rsi-integration.md)，协议修复与新证据见 [v2 验证](replay-validation.md)。旧数值、身份与 verdict 不重写或合并到新结果。

验证日期 2026-11-03。实现基于 `663f3b327998526a13aa31e72ad729025c18983c`，对应初始实现 [d0ce9d7](https://github.com/Bounty-hunter/InferRSI/tree/d0ce9d785e1bead9124eed1cf3f6e9f2e0cf05db)；实际运行文件的身份以结果中的内容哈希为准。本记录说明共享任务子集的功能与集成，不是项目维护者的验收决定。

## 实际运行结果

最终原始目录名为 `inferrsi-252-validation-final`，保留在仓库外的本地 outputs 目录。重放这套 v1 协议须使用上述原始版本的 `tools/engineering_benchmark_validate.py`、任务包和 grader，并核对记录中的文件身份；新执行产生自己的记录，不会重建原始计时值。当前分支的工具执行 v2 协议，不能用于复现本页的样本数量或身份。该次执行使用 Windows、Python 3.11.18、NumPy 2.4.6。

[可公开的原始汇总](validation-summary.json) 保留任务/候选/grader/runtime 身份、执行数量、原始 verdict 和覆盖状态，不包含个人路径。完整原始日志和样本仍在本地，公开汇总不能代替独立重放或正式 campaign 验收。

| 验证内容 | Softmax CPU | RMSNorm CPU |
| --- | --- | --- |
| workload 数 | 6 | 6 |
| 每次独立正确性断言 | 24 | 24 |
| 正确候选在工程评估中 | 通过 | 通过 |
| 正确候选经过实际 SkillEval run_trial/verifier | 通过 | 通过 |
| 全零错误候选经过同一路径 | 拒绝 | 拒绝 |
| 错误候选请求测量 | 失败，无可用性能指标 | 失败，无可用性能指标 |
| Workbench 配对 trial | 3 baseline + 3 candidate | 3 baseline + 3 candidate |
| 保留的实际计时样本 | 180 | 180 |
| CPU profile | 已生成，42 次 compute 调用 | 已生成，42 次 compute 调用 |
| 所有消费者 task/grader/runtime 身份 | 一致 | 一致 |
| 所有消费者实际输入摘要、shape/dtype/strides | 一致 | 一致 |
| Workbench 源码完整性检查 | 通过 | 通过 |

`summary.json` 的 `checks_succeeded` 为 true。每个任务目录包含冻结的任务包、候选源码、runspec.json、identity.json、correctness、profile、workbench、skilleval-good、skilleval-bad、wrong-measure。原始样本、命令、stderr、输入摘要和 profile 均保留，可追溯到实际执行。

工程评估与 SkillEval 的 PASS 仅表示相应公开用例的数值正确性。Workbench 的比较 verdict 原样保留，包括不满足增益门槛的结果。两次集成运行的性能胜负有变化，且宿主机同时有软件检查活动，不能据此宣布优化收益；本次目的为验证测量通路和失败处理，不是做隔离 CPU 性能实验。统计显著性仍为 not established。

## 软件检查

- 新增专项回归 `tests/test_engineering_benchmarks.py`：**26 passed**。覆盖真实任务、反例、预检之后变错、task/candidate/grader/runtime 漂移、缺 NumPy、超时、实际 Workbench AB/BA、真实 SkillEval verifier 和错误产物身份。
- `ruff check src tests tools/engineering_benchmark_validate.py`：通过。
- `git diff --check`：通过。
- sdist 和 wheel 构建：通过。Windows 长路径导致的第一次构建失败保留；缩短构建临时目录后成功，没有删减包内容。
- 全新非 editable wheel 环境，源码目录外运行 `python -I tests/check_installed.py`：通过，包括任务文件、许可证、127 条既有知识记录等安装检查。
- 同一隔离安装中实际执行 Softmax 独立 oracle：通过。
- 全量回归使用 Python 3.11、4 个 pytest worker 完成：**3479 passed、51 skipped、56 failed**，另有 281 个通过的 subtest。55 个失败用例产生 56 个失败报告，全部在未修改的原始基线复现。典型原因包括 Windows 的 CRLF 字节差异、符号链接权限、POSIX FIFO/process API、Linux sandbox 和路径假设；没有通过修改无关测试掩盖。
- 基线对照在独立 detached worktree 执行，确认 import 指向原始基线 `src/inferrsi`；逐个匹配 JUnit 中的失败用例，未出现“本次失败但基线通过”的用例。全量结果仍为非绿色，不能称为所有检查通过。

最初仅有 Python 3.14 的环境缺少 tzdata，导致仓库中 6 个已有模块无法收集测试。后续使用仓库 CI 覆盖的 Python 3.11，并在本地测试环境安装 tzdata。未更改项目的时区业务逻辑。26 项专项验证的最终结果来自该 Python 3.11 环境。

全量串行尝试在发现原有失败后改用 4 个 worker 完整执行。最终日志为 `inferrsi-252-full.log/xml`；对照为 `inferrsi-252-baseline-all-failures.log/xml`；新增功能专项为 `inferrsi-252-focused.log`。早期失败、构建长路径问题和首次集成运行也保留，没有覆盖为成功。

## 四个子项的实际用途

后续新增了[实际工程用途对照](usefulness.md)：普通冒烟漏掉的 RMSNorm epsilon 错误被共享任务和 SkillEval 一致拒绝；原版对原版的大幅计时差异同时说明，本机小尺寸协议尚不能支持可靠性能排序。该次公开汇总保留全部 720 个原始样本，不改变本页早先集成运行的结果。

1. 调研决定落实在代码边界中：保留 axis=1、独立 oracle、正确性先行、profiling 独立、已有 runner 复用，没有照搬外部搜索平台。
2. 共享接口会拒绝漂移或未支持环境，避免两个消费者用不同题目版本得出不可比较的结果。
3. 两个算子确实计算并计时；数值、布局和状态错误会被抓到，未用预制分数代替实现。
4. Workbench 与 SkillEval 真正执行了同一任务包；逐项比较实际输入摘要验证复用，没有为第二个消费者复制答案。

## 本次未建立的结论

GPU/NPU 正确性和性能、通信/内存容量任务、真实模型/服务收益、技能或搜索策略收益均未验证。公开开发用例不是 holdout；可信代码执行不等于恶意 agent sandbox。本次公开提交用于评审；尚无独立 reviewer 的签署、维护者对首批子集的正式接受或关闭 #252 的授权，公开追踪入口见总方案。上述差别不影响已经完成的本地实现和功能验证，但不能被省略为“整个 tracking issue 已验收”。
