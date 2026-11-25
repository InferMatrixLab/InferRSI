# 在 Ascend A2 上运行 Codex 图像优化 E2E

本目录只有一个 pytest 用例。它在同一台 Ascend A2 机器上启动 Codex，等待优化结束，从固定基线应用最终补丁，然后独立测量单张图像的耗时与质量。[任务与基线版本](https://github.com/InferMatrixLab/InferRSI/issues/479)

## 运行

在预配置的 Linux A2 环境中运行。该环境需要已登录的 Codex CLI、可用的 InferRSI、该基线所需的 vLLM-Omni 昇腾依赖和本地只读模型权重。给进程分配一张空闲的 Ascend 910B，使其仅能看到这张卡。环境变量可由机器的作业配置一次性设置。

```bash
export QWEN_E2E_REPO='<本地-vllm-omni-Git-仓库>'
export QWEN_E2E_REVISION='<Issue-指定的完整基线提交>'
export QWEN_E2E_CHECKPOINT='<本地-Qwen-Image-2.1-Turbo-权重目录>'
export QWEN_E2E_RESULTS='<本次作业可写的私有结果父目录>'
python -m pytest -qs e2e/qwen_image/test_user_journey.py
```

前三个变量是必需项。省略 `QWEN_E2E_RESULTS` 时使用 pytest 临时目录。每次运行都会新建结果子目录。Codex 使用机器上已配置的模型，也可以通过 `QWEN_E2E_CODEX_MODEL` 指定。默认每次 Codex 调用或测量进程的超时为 7200 秒，可用 `QWEN_E2E_TIMEOUT_SECONDS` 调整。运行期间无人工问答、审批或手工提交补丁。

## 输入与执行

- 用户请求见 [request.txt](../e2e/qwen_image/request.txt)。用例附上本机模型、冻结测量程序和新建 campaign 的位置，要求 Codex 将选中的实现留在工作副本的 `vllm_omni/` 中。实际投递内容保存在结果目录的 `request.txt`。
- [workload.json](../e2e/qwen_image/workload.json) 固定两个预热请求和六个测量请求（种子 42–47）。两侧均使用 1280×704、BF16、原生八步、CFG=1、单卡、单请求单图。计时从调用 `Omni.generate` 开始，到取得已解码的 RGBA 图像为止。模型加载、预热和 PNG 落盘分别处理。
- 用例先在两个全新进程中复测基线，核对六张原图，记录两组中位耗时的相对差值作为本次噪声参考。此时将运行条件写入 `frozen.json`。若 Issue 另有最低降幅，开跑前用 `QWEN_E2E_MIN_GAIN_PCT` 指定百分数。
- Codex 退出后，用例读取同一次运行中的最终回复和 InferRSI campaign，核对至少两轮优化、完成状态和最终选中源码。随后从工作副本提取补丁，在第二个干净 Git 副本中应用，核对 `vllm_omni/` 的 Git 树。之后以 AB、BA、AB 的顺序交替测基线（A）与补丁（B），每组每侧启动一个新的推理进程。每个进程保存六个原始耗时与六张 PNG。

## 校验优化指标

`baseline_ms` 和 `candidate_ms` 分别为各自三个组中位数的中位数。用例输出节省的毫秒数、降幅 `100 × (baseline_ms − candidate_ms) / baseline_ms` 和加速比 `baseline_ms / candidate_ms`，逐种子比对所有候选图像的 RGBA 字节。

| 结果 | 条件 |
| --- | --- |
| `PASS` | 六组图像全部一致；耗时降幅为正、达到预设最低降幅，且超过测前基线 A/A 差值。 |
| `FAIL` | 已完成优化却没有交付源码改动、补丁与选中源码不符、候选图像变化，或实测未达到正向收益及设定的最低降幅。 |
| `INCONCLUSIVE` | 基线不稳定、环境或执行证据不完整，或正向收益仍处于 A/A 波动范围。pytest 返回非零。 |

最终结果见 `result.json`。同目录保留 Codex 会话日志、回复、`candidate.patch`、各组原始耗时和 PNG，可从这些文件复核结果。运行目录可能含私有机器路径和会话内容。
