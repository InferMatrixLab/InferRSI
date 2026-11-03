# #252：实际工程用途对照

本补证回答一个具体问题：共享任务能否帮助使用者识别一个看似合理的错误改动，并让正确候选经过同一套工程检查和实际性能比较？它不以 CI 绿色或某次计时 PASS 作为“有用”的定义。

## 预先固定的对照

选择既有 `rmsnorm-cpu` 任务，保持六个公开工作负载、axis=1、float32、epsilon、容差、oracle、预热与采样规则不变。所有代码均为审核过的本地实验实现；SkillEval 交接的是保留产物身份，没有调用生成模型。

| 实现 | 检查目的 |
| --- | --- |
| unchanged | 逐字复制原版，作为原版对原版的计时对照 |
| no-epsilon | 一个真实容易出现的错误：省掉 epsilon；先观察普通输入冒烟，再交给完整任务及两个消费者 |
| einsum | 用 axis-1 平方和归约替代显式 `x*x` 中间数组，保留 epsilon、类型、布局和输入语义；性能改善只是待检验假设 |

普通输入冒烟预先定义为 seed 2026、shape `(4, 17, 9, 7)` 的 float32 正态分布乘以 4，使用任务的独立 oracle 和容差。它与完整任务的压力输入不同，结果会如实保留。即使错误实现未通过此冒烟，也不换一组输入重试。

先冻结计划、任务、实现、grader/runtime 身份和比较参数，再执行。对 unchanged 与 einsum 各做一次既有 Workbench 比较，按预定顺序运行，所有 trial 均保留。性能阈值只用于展示既有描述性裁决，不作为本补证的功能通过条件，不根据结果选择重跑或修改阈值。

## 怎样判断有实际用途

1. 正确候选在完整任务和实际 SkillEval verifier 中均通过；两个消费者使用同一任务、实际输入和 oracle。
2. no-epsilon 在完整任务中被拒绝，错误测量没有可用性能指标；保留具体失败断言。
3. 正确候选的实际比较保留每个工作负载的原始样本，不能只挑总分或快的 case。
4. 原版对原版的结果同样公开；若也出现描述性 PASS，必须标明相同实现的计时波动，不能宣称优化收益。
5. profiling 独立运行且没有性能胜负，保留调用路径及其分辨能力的限制。

## 诊断与决策边界

已有 CPU profile 只有 42 次记录的 compute 调用，总时间约毫秒量级，文本中的多个耗时显示为 `0.000`。这能说明实际调用了哪些函数，不能证明内存带宽或临时数组分配就是瓶颈。einsum 候选来自源码检查提出的假设，不能写成 profiler 已证实的优化方向。

小尺寸公开用例没有建立真实服务代表性。既有 Workbench 使用中位数和阈值，尚未实现统计显著性或多轮选择偏差控制；未改进实现也可能得到描述性 PASS。本补证保留这个事实，不以集成测试通过替代性能验收。

## 复现入口与结果

两阶段复现入口为 `python -m tests.fixtures.engineering_benchmark_usefulness`：`prepare` 只冻结输入，`run` 要求显式计划摘要并执行一次。使用全新输出目录，参数来自对应 Issue 的预登记记录。完整原始日志留在本地；公开汇总仅发布无私人路径的身份、结果、失败断言和逐 case 样本。

实际执行前的条件、身份与摘要见 [#337 预登记](https://github.com/InferMatrixLab/InferRSI/issues/337#issuecomment-6607885902)。本地原始目录名为 `inferrsi-252-usefulness-20261103-v2`；此前的目录只执行过 prepare，没有运行 payload。独立静态检查发现并修复了补证脚本的最终质量门槛缺口，然后重新冻结计划，实际 payload 只执行一次。

```bash
python -m tests.fixtures.engineering_benchmark_usefulness prepare \
  --repo <checkout> --output-dir <new-output> \
  --repetitions 6 --max-minutes 2 --min-improvement-pct 0 --timeout-seconds 25
python -m tests.fixtures.engineering_benchmark_usefulness run \
  --output-dir <new-output> --plan-sha256 <digest-returned-by-prepare>
```

这些参数来自本次预登记，不是共享的性能验收默认值。新复现的路径或环境会改变计划摘要，应使用该次 prepare 的返回值。

## 实测结果与明确决策

2026-11-03 在 Windows / Python 3.11.18 / NumPy 2.4.6 上执行。期间没有并行运行本地测试，但宿主机没有专用资源隔离。运行时与任务仍为 PR 初始实现；本补证只新增 fixture 和说明。

| 检查 | 实际结果 | 说明 |
| --- | --- | --- |
| no-epsilon 普通输入冒烟 | 通过 | 单个普通输入确实漏掉了错误 |
| no-epsilon 完整任务 / SkillEval | 两边均 FAIL | 拒绝 `normal.values`、`strided.values`、`zeros.finite`、`zeros.values`、`tiny.values`、`singleton.values` 六个断言 |
| no-epsilon 测量 | 拒绝，无性能指标 | 错误实现没有凭借省略计算获得可用分数 |
| unchanged / einsum 正确性 | 两个实现均在两条路径通过 | 两个 Workbench 比较结束时的质量验证也通过 |
| 共享任务和实际输入 | 一致 | 包含正确性、profiling、计时和真实 SkillEval verifier |
| 原版对原版比较 | 12 个 trial，360 个原始样本；原始 verdict 为 FAIL | 报告的 improvement 为 -50.52%，同码对照说明当前测量条件不足以可靠分辨优化 |
| einsum 对原版比较 | 12 个 trial，360 个原始样本；原始 verdict 为 FAIL | 报告的 improvement 为 -76.95%；不能在上述噪声条件下把数值解释为稳定退化或加速 |
| 独立 CPU profiling | 两份均完成，无性能 verdict | 支持调用路径检查，未确认内存瓶颈 |

**已经证明的用途：** 共享基准抓住了预先指定的普通冒烟漏检，同时让两个消费者用同一套题目和 oracle 识别正确与错误实现，并保留可审查的实验记录。八项功能检查全部通过。

**没有通过的用途：** 本机小尺寸协议尚不能支持可靠性能排序。即使正确性通过，也不能据此采用 einsum 候选；本次决定保留原版，不修改任务包默认实现。不重跑挑选好看的结果，也不把两个性能 FAIL 改成 PASS。

后续若要将这些任务用于性能搜索，需要单独预登记计时稳定性验证：先使原版对原版具备足够分辨能力，再比较候选；考虑足够长的采样、宿主机干扰、逐 case 噪声和跨轮次选择偏差。这是后续验收项，不是本次已经交付的统计控制器。

[公开原始汇总与全部 720 个计时样本](usefulness-summary.json) 为本次 summary 的原始副本；两份已去路径的原始 profile 为 [unchanged](usefulness-profiles/unchanged.txt) 和 [einsum](usefulness-profiles/einsum.txt)。它们保留原始数值与 SHA-256；完整命令、日志和源码快照仍在本地。此次探针代码摘要为 `317285d0534f9935d06e1fc488ef35c56a76ab7cba2c2423e5a73ba09799ebc7`，计划摘要见预登记与 JSON，不因后续文档更新而改写。

该检查不证明 agent/skill/search 的收益、GPU/NPU 资格或服务加速，也不实现全流程控制器。
