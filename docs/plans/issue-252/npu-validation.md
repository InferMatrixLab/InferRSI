# NPU 试点实测：RMSNorm 已接通检查、profiling 和 Workbench

2026-11-04。**本轮已在一张 Ascend 910B1 上跑通完整的软件控制试点。** 正确实现通过，错误实现被拒绝，实际设备 profile 可读，同码对照没有被选为优化，融合参考实现在两个规定 workload 上达到执行前固定的改善门槛。七项资格检查均通过；项目验收、真实 Agent/skill 收益和服务收益仍未建立。

执行前的[范围、源码和判断门槛](https://github.com/InferMatrixLab/InferRSI/issues/337#issuecomment-6621316099)先于本次资格实验发表。被测源码为 `6308268fc6d1fbf90e9ab97b5da8af79152f39ea`；后续本记录仅整理证据，不将结果改标为新实现的运行。

[可公开证据与全部 800 个计时样本](npu-validation-summary.json)保留原 verdict、冻结身份、环境、逐项错误和 profile kernel 摘要。完整 raw archive 留在执行归档；公开转换及每份原始结果、trace、JUnit 的摘要也在该文件中。

## 实际做了什么，它有什么用

| 步骤 | 本轮实际结果 | 在 RSI 中发挥的作用 |
| --- | --- | --- |
| 固定任务 | `rmsnorm-npu`，二维 contiguous float32，`compute(x, weight, *, eps)`；5 个基础 case，非全一权重 | baseline 和候选做同样的工作，不能减少工作量换分 |
| 独立检查 | baseline、fused reference 各 75 次调用、375 项断言通过；oracle 使用 scalar double / math.fsum | 检查数值、shape/dtype/device、输入与权重保持 |
| profiling | 两个受测 shape 上，baseline 共 12 个计算 kernel，fused 共 2 个 `RmsNorm` kernel | 验证这份候选确实走融合设备路径；辅助解释调用延迟差异 |
| 错误控制 | 全零、漏 epsilon、漏权重、错误轴、原地改 shape、缓存旧输出均失败且无可用 metric | 阻止错误但看似很快的实现进入性能选择 |
| 同码 A/A | 两侧都运行 baseline；各 shape 中位数差小于 0.4%；Workbench 原始 verdict 为 FAIL（没有达到收益门槛） | 没有将 no-op 当作优化；这里的 FAIL 是预期控制结果 |
| 参考优化比较 | composed baseline → 既有 fused 实现；两个 shape 分别降低约 34.80%、30.60% 的同步调用延迟 | 在本轮范围内支持保留融合参考实现 |
| 留存与重验 | 16 个 trial / 800 个计时样本、最终 validation、完整环境和冻结 identity 均核对通过 | 决定可以回溯到真实源码、实际执行和原始数据 |

另外执行了**预检后才重放**的控制：前 5 个基础 case 的 25 项断言全通过，首个变化输入 warmup 被拒绝，无性能 metric。它补充证明检查没有停在最初的正确输出。该额外控制的源码、身份、失败 phase 和结果摘要也保留在公开证据中。

## NPU 与计时条件

实际环境为 Ascend 910B1、Linux aarch64、Python 3.12.13、torch 2.10.0+cpu、torch_npu 2.10.0.post4、NumPy 2.5.3、CANN 9.1.0。PyTorch 的 `+cpu` 包版本后缀不表示在 CPU 计算：设备 tensor、实际 `Ascend Hardware` kernel 事件和 torch_npu 执行分别核对。使用个人非 root UID、已有设备组和共享调度器单卡预约，主资格与额外重放控制退出码均为 0，完成后设备已释放。

计时为 **同步 eager 完成调用延迟**：预同步后开始计时，调用实现，再等待 NPU 完成才停止。包含 Python dispatch 和完成同步成本；输入/权重准备、H2D、独立 oracle、D2H 校验、profiling 均不进入该计时。因此下表不能称作纯 kernel 时间，更不能直接转换成模型或服务收益。

每个 shape 先做 10 次变化输入预热，再保留 25 个样本；每个比较使用 4 对 AB/BA。下表为各臂 4 个 trial 的对应 shape 中位数再取中位数。所有慢样本和原始 Workbench 聚合均保留，没有按结果筛选。

| 对照 | shape | baseline（ms） | 对侧（ms） | 同步调用延迟降低 |
| --- | --- | ---: | ---: | ---: |
| A/A，同实现 | `[1,4096]` | 0.280772 | 0.2797225 | 0.374% |
| A/A，同实现 | `[64,4096]` | 0.311018 | 0.310098 | 0.296% |
| baseline → fused | `[1,4096]` | 0.278377 | 0.181495 | 34.802% |
| baseline → fused | `[64,4096]` | 0.311328 | 0.216051 | 30.603% |

这证明了本轮固定环境和 workload 下的区分能力；仍是有限次描述性比较，没有建立跨机器稳定性、置信区间或服务增益。门槛来自执行前的 Issue 计划，不是新增仓库默认性能门槛。

## Profiling 怎样影响判断

baseline 在每个选定输入上出现 3 次 Mul、1 次 ReduceMean、1 次 Adds、1 次 Rsqrt；融合路径每个输入只有 1 次 `RmsNorm`。因此这份实现确实减少了设备算子调用，性能差异不是把结果移到 CPU 或返回另一个形状造成的。

本轮候选来自预先选择的官方 fused reference。主 Agent 根据 profile 核对机制，再根据独立检查、A/A 与固定条件对照决定保留它；没有声称 Agent 从 trace 自主发明或搜索出新 kernel。profile 属于诊断证据，不能用其中的 instrumented 时间替换上表。

## 软件回归与 review 修复

同一 source head 的 [Linux ready/review CI](https://github.com/InferMatrixLab/InferRSI/actions/runs/41764076901)通过：Python 3.10 和 3.11 各 **3649 passed / 20 skipped / 284 subtests passed**，两个安装包检查通过。托管 CI 中没有 NPU；设备验证来自上面的独立远端运行。

正式 CPU artifact job **54 passed / 0 skipped**，其中新增的 `test_real_sandbox_rejects_zero_output_despite_cwd_shadow` 真正执行，错误零输出在同名 cwd 包放宽容差后仍被规范 oracle 拒绝。另有 descriptor/starter/prepare/dependency 的来源回归。CI checkout merge `6f1506bcb366c10836991701f8beaf7ac89e9a11` 与被测 head 的 tree 均为 `5c22811e28f1c8c0182852916f43804c18b35edf`。这对应已实现的 P2 修复；原 reviewer 的审查结论仍待复审，不由作者标为接受。

新增 NPU 无设备回归本地最终 **14 passed / 1 device test skipped**。开发首轮的 6 项失败分别来自新测试的文本编码和输出目录使用错误，修复后重跑；没有归因于既有 baseline。独立源码审查还发现并修复了输入 shape 原地修改、A/A 最终 validation 失败混同无收益、冻结控制身份未重验三处问题。

早期探测的容器用户名初始化失败，以及一次 profile 后调用不存在的 `key_averages()` 导致退出 1，保留在原始日志中。正式 adapter 不使用该方法，直接核对硬件 trace；失败探测不参与 800 个性能样本。

## 如何复现和继续

使用 [NPU 试点的操作说明](npu-pilot.md)和 [共享接口](../../engineering-benchmarks.md)，在已预约的兼容 NPU 环境中运行 `python -m tools.npu_benchmark_validate`，显式传入本轮 Issue 的重复次数、预算与门槛。工具先写入 `plan/frozen.json`、`validator/task.json` 与 `patch/`，随后通过既有 Workbench 保留 `results/`、报告及 `summary.json`。

当前可保留的是这个 float32 NPU 参考候选及共享评测通路。BF16/FP16、更多形状、真实模型/服务、NPU 产物隔离和真实 Agent 两臂仍需分别验收。四个 Issue 与 PR #338 保持打开/Draft，NPU 软件控制通过不自动完成整个 #252。
