# 双 NPU MoE forward：任务与独立评测入口

这道题让 Agent 优化一层真实结构的计算：路由 → 跨卡派发 → 本地专家 MLP → 合并结果，
加一个共享专家。Agent 交付 `compute(x, params, *, config, group)` 的 Python 实现；
评测入口检查两张卡的输出，再在相同设备上交错测量基线和候选。
它提供一次候选的事实反馈，调用方或 Agent 根据反馈决定下一次改动。

任务允许研究路由和重排开销、融合、冗余计算、通信组织及同步消除；
例如比较 AllGather 和 AllToAll 派发，但某一种优化并不保证有效。
完整定义在 [TASK.md](../src/inferrsi/benchmark/tasks/moe-forward-npu/TASK.md)，
固定形状和误差容差在 [task.json](../src/inferrsi/benchmark/tasks/moe-forward-npu/task.json)。
题目参考所引用版本的 vLLM-Ascend MoE 结构，代码独立编写，按 Apache-2.0 分发。
它不包含完整 vLLM 服务，也不能据此声称整模型或服务获得相同加速。

## 怎么运行

需要已经配置好的 Linux、PyTorch、torch_npu、CANN/HCCL 和两张可用 Ascend NPU。
在该环境安装当前 InferRSI checkout（例如 `python -m pip install -e .`）；
入口不安装或修改共享设备软件。候选是一个经审查的自包含 Python 文件，
可以导入当前环境已有的运行库。可先复制题目内 `baseline.py` 作为候选，验证接线。

由调用方申请两张空闲设备，不固定卡号。例如在仓库根目录：

```bash
npu run --gpus 2 --timeout 20m --wait 30m -- \
  python -m inferrsi benchmarks run moe-forward-npu \
  --candidate ./implementation.py \
  --output-dir ./outputs/moe/round-01 \
  --pairs 2 --timeout-seconds 900
```

`npu run` 是环境已有的分配器，不由 InferRSI 安装。它必须在子进程中设置
`ASCEND_RT_VISIBLE_DEVICES` 为两张不同的已分配卡。入口将它们映射为逻辑 rank 0/1，
用本机 `torch.distributed.run --standalone --nproc-per-node=2` 启动 HCCL。
分配等待在入口计时之外；分配器超时应为本次评测的超时和清理留出余量。
没有该分配器时，也可在已经获得的两卡分配内直接执行相同 Python 命令。

安装 wheel 后，无需 `tools/` checkout，可用同一参数运行：

```bash
inferrsi benchmarks run moe-forward-npu \
  --candidate ./implementation.py --output-dir ./outputs/moe/round-01 \
  --pairs 2 --timeout-seconds 900
```

每个候选必须使用**新的输出目录**，已有目录会拒绝覆盖。`--pairs` 和
`--timeout-seconds` 都必须显式指定；两组配对为每实现每性能 case 16 个计时样本，
四组为 32 个。超时包括入口准备和执行，之后最多有额外的有界进程清理等待。
入口先冻结题目、候选和 grader 的副本及 SHA256，再通过现有
由应用入口注入的 `harness.scenarios.external.execute_trial` 执行。
该执行器不含 metric 规则，入口在传 metric key 的同时传入自己的校验函数
（`metric=read_metric`）。
Python 调用 `evaluate` 时须显式传入 `execute_trial`。它额外清理本次唯一环境标记的
torchrun 子进程，覆盖子进程创建独立 session 的情况；不会按宽泛进程名杀进程。

## 每个结果代表什么

| 产物 | 用途 |
| --- | --- |
| `result.json` | 本次权威结果：状态、正确性、可用加速比、执行时间、清理结果 |
| `identity.json`、`task/`、`candidate/`、`runner/`、`request.json` | 本次输入、代码与采样次数的冻结副本和哈希 |
| `results/rank-0.json`、`results/rank-1.json` | 每次正确性、预热、正式调用、输入哈希、两卡耗时和准备开销 |
| `results/summary.json` | rank 0 的原始汇总，必须经过外层完整性检查才可用 |
| `execution/` | 通用执行器记录、原始结果、stdout 和 stderr |

只在命令成功退出、两 rank 完整通过、全部预期调用和样本齐全、汇总可从原始样本重算、
代码未变化且清理完成时，`result.json` 才包含可用 `speedup`。
候选导入/执行失败、候选超时或输出错误记为 `candidate_failure / FAIL`，
`round_consumed=true`，不当作免费的基础设施重试。
基线、设备初始化、证据完整性或清理失败记为 `infrastructure_failure / INCONCLUSIVE`。
若已经观察到候选执行，随后发生基础设施或清理失败，仍保留 `round_consumed=true`；
已识别的候选失败也不会被后续清理问题改写为免费重试。清理未确认时应停止后续运行。
失败均无有效速度分数；原始日志中即使曾出现局部 PASS 或速度也不能替代最终结果。
`round_consumed=false` 只表示未发现候选执行记录；证据不完整时，不能据此认定可以免费重试。
退出码分别为 0（完成）、2（候选失败）、1（基础设施或参数失败）。

每个样本取两 rank 的完成时间最大值；每个 case 取 baseline/candidate 中位数之比；
最终 `speedup` 是三个 case 加速比的几何平均。
`metrics.suite_latency_ms` 是三个候选中位数之和，是供现有执行器读取的单独指标，
不应拿它代替上述几何平均加速比。

计时覆盖完整 forward 的 host 调度、路由、重排、通信、MLP 和设备完成。
CPU 输入/oracle 准备、计时前 barrier、验收、形状预热不在 forward 分数中，开销另存。
预热使用数值和输出都不同、每 token 专家集合相同的输入；正式样本输入持续变化，
每次都验算并清零输出。首次调用包含候选自己的权重排布/编译等准备，但同进程共享
底层库缓存，因此不是两者各自在全新进程中的冷启动对照。
峰值显存是 baseline/candidate **共享进程峰值**，不是候选单独峰值。

## 在 RSI 优化循环里如何使用

```text
用户目标与题目约束 → Agent 改候选 → 本入口验算并测量 → Agent 看证据再修改
                                              ↓
                              调用方保留每轮结果、选最佳版本、独立复测
```

调用一次评测一个候选。`inferrsi benchmarks list` 和
`inferrsi benchmarks show moe-forward-npu` 可以读取题包信息，执行使用本页的 MoE 入口。
调用方负责启动 Agent、推进轮次、统计模型 tokens 和选择搜索策略，
并将每次 `result.json` 作为下一轮反馈。
知识库 ON/OFF 或不同 Agent 的差异由调用方控制，测量协议保持一致。
profiling 可作为 Agent 诊断工具，评测入口不要求先 profiling。

可给新 Agent 的简短任务指令：

> 阅读 `src/inferrsi/benchmark/tasks/moe-forward-npu/TASK.md`，
> 优化 `./implementation.py` 的完整双 NPU MoE forward。遵守输入只读、专家所有权、
> 正确性和计时边界。每次候选使用新的输出目录，按已约定的配对数、超时和实验预算，
> 通过 `inferrsi benchmarks run moe-forward-npu` 取得结果；保留失败，不以自报数字替代结果。
> 最终交付最佳候选、逐轮证据和独立复测记录。

例如要做 8 轮再复测，由调用方为 R1…R8 和 final 分配不同目录并保存候选快照。
轮数是该次实验的预算，不能把它当成通用默认值。优化曲线按每轮有效分数及历史最佳分数
绘制；失败轮保留空分数并消耗预算。累计 tokens 需从对应 Agent/session 的原始 usage
记录汇总；本入口的 `elapsed_seconds` 是评测墙钟，不是 Agent 搜索墙钟或模型费用。

## 验证范围与限制

历史冻结题目、baseline、oracle、采样逻辑已有双 NPU 实验；本次发布保留了这些数学和
计时语义，加入便携包装、源码冻结、双 rank 证据复核和独立 session 清理。
**新增的便携入口尚未在 NPU 上重新跑通**，CPU 测试和 wheel 资源检查只验证接线、
失败处理及证据完整性，不能当作新入口的 NPU 验收或性能结论。

当前权重更新用例验证原位更新后的结果，但两次访问之间还运行其他参数用例；
它没有穷尽“相同缓存项命中后立即原位更新”等所有缓存失效路径。
候选源码需要审查；输入/oracle 隔离是协议边界，不是恶意代码沙箱。
本题与历史实验都不能证明所有 MoE 形状、硬件或服务负载上的收益。
