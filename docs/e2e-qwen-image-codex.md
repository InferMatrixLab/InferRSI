# 在 Ascend A2 上运行 Codex 图像优化 E2E

本目录只有一个 pytest 用例。它在同一台 Ascend A2 机器上启动 Codex，验证三轮叠加优化及其交付的累计补丁。取得完整三轮凭证后，用例独立测量单张图像的耗时与质量。[任务与基线版本](https://github.com/InferMatrixLab/InferRSI/issues/479)

## 运行

在预配置的 Linux A2 环境中运行。该环境需要已登录的 Codex CLI、可用的 InferRSI、该基线所需的 vLLM-Omni 昇腾依赖和本地只读模型权重。给进程分配一张空闲的 Ascend 910B，使其仅能看到这张卡。环境变量可由机器的作业配置一次性设置。

```bash
export QWEN_E2E_REPO='<本地-vllm-omni-Git-仓库>'
export QWEN_E2E_REVISION='<Issue-指定的完整基线提交>'
export QWEN_E2E_CHECKPOINT='<本地-Qwen-Image-2.1-Turbo-权重目录>'
export QWEN_E2E_MIN_GAIN_PCT='<验收降幅门槛百分数>'
export QWEN_E2E_RESULTS='<本次作业可写的私有结果父目录>'
python -m pytest -qs e2e/qwen_image/test_user_journey.py
```

前四个变量是必需项。`QWEN_E2E_REVISION` 必须与用例固化的 #479 基线完全一致，其他提交会在检出和测量前被拒绝。省略 `QWEN_E2E_RESULTS` 时使用 pytest 临时目录。每次运行都会新建结果子目录。Codex 使用机器上已配置的模型，也可以通过 `QWEN_E2E_CODEX_MODEL` 指定。默认每次 Codex 调用或测量进程的超时为 7200 秒，可用 `QWEN_E2E_TIMEOUT_SECONDS` 调整。此用例以运行期间无人工问答、审批或手工提交补丁为测试条件。

在当前 `main` 上，直接启动此无人值守用例且未满足启动审批时，预期结果为 `INCONCLUSIVE`。`campaign start` 要求与每次具体方案绑定的用户审批。遇到该关口时，Codex 将阻塞原因写入最终回复，用例保留日志和缺失轮次信息。 [启动审批规则](guides/task-intake.md#campaign-hand-off)

## 输入与执行

- 用户请求见 [request.txt](../e2e/qwen_image/request.txt)。用例附上本机模型、冻结测量程序和新建 campaign 的位置，要求 Codex 每轮以上一轮改进后的源码为起点，在同一项目中叠加三轮改动，并将第三轮累计实现留在工作副本的 `vllm_omni/` 中。实际投递内容保存在结果目录的 `request.txt`。
- [workload.json](../e2e/qwen_image/workload.json) 固定两个预热请求和六个测量请求（种子 42–47）。两侧均使用 1280×704、BF16、原生八步、CFG=1、单卡、单请求单图。计时从调用 `Omni.generate` 开始，到取得已解码的 RGBA 图像为止。模型加载、预热和 PNG 落盘分别处理。在每次请求的计时区间外启停采样记录。扩展从推理 worker 的 scheduler step 采集实际使用的 timestep、sigma 和下一步 sigma，基线和复测各组的有效序列必须一致。
- 用例先在两个全新进程中复测基线，核对六张原图，记录两组中位耗时的相对差值作为本次噪声参考。此时将运行条件写入 `frozen.json`。开跑前用 `QWEN_E2E_MIN_GAIN_PCT` 设定本用例的降幅门槛，低于 10% 的配置会在预检时拒绝。门槛与 A/A 波动参考一同保存在 `frozen.json`。
- Codex 退出后，用例读取同一次运行的最终回复和 InferRSI campaign。用例根据每轮启动计划重新评估 Harness 保存的原始计时和画质结果，核对执行记录的基线、候选摘要以及原始文件摘要。缺少原始产物的轮次无法通过校验。第一轮从原始基线开始，第二、三轮的基线必须分别匹配上一轮的候选快照，交付源码必须匹配第三轮结束的快照。
- 用例提取并在干净 Git 副本重建累计补丁，核对 Git 树和第三轮实际源码摘要。测试端再逐轮测量封存的基线和候选快照，在 `round-retest/` 保留原始耗时、采样网格与 PNG，并在 `verified.json` 将每侧结果和 RGBA 摘要与该轮启动计划、原始执行记录及对应源码摘要绑定。三轮核验完毕后，以 AB、BA、AB 的顺序独立复测原始 B0 与重建的累计 B3。每个推理进程保存六个原始耗时和六张 PNG。

## 校验优化指标

`baseline_ms` 和 `candidate_ms` 分别为各自三个组中位数的中位数。主要指标为第三轮累计版本相对原始基线的最终降幅。用例输出节省的毫秒数、降幅 `100 × (baseline_ms − candidate_ms) / baseline_ms` 和加速比 `baseline_ms / candidate_ms`，逐种子比对所有候选图像的 RGBA 字节。

| 结果 | 条件 |
| --- | --- |
| `PASS` | 六组图像全部一致，且第三轮累计版本相对原始基线的最终降幅严格大于已冻结的门槛和 A/A 波动。 |
| `FAIL` | 已完成优化却没有交付源码改动、补丁与选中源码不符、候选图像变化，或最终降幅小于或等于已冻结的门槛。 |
| `INCONCLUSIVE` | 基线图像或测量环境不一致，或执行证据不完整。超过门槛但未超过冻结的 A/A 波动时也判为 INCONCLUSIVE。pytest 返回非零。 |

最终结果见 `result.json`。同目录保留 Codex 会话日志、回复、`candidate.patch`、各组原始耗时和 PNG，可从这些文件复核结果。运行目录可能含私有机器路径和会话内容。
