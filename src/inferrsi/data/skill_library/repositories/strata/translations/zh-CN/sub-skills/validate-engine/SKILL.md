---
name: validate-engine
description: "通过源码检查、CPU 测试、GPU 算子对齐、真实模型 API、取消与并发测试，以及受控质量和性能实验验证 Strata 引擎改动。用于验收 AI 生成的推理引擎候选或判断性能提升是否成立。"
license: MIT
metadata:
  disco-role: operating
---

# 验证 Strata 引擎候选

使用本子技能把优化方案转为可复现的接受或拒绝结论。完整命令、前置条件、指标及恢复动作见[验证操作手册](references/validation.md)。变量选择交给 [design-space](../design-space/SKILL.md)，执行调优交给 [tune-execution](../tune-execution/SKILL.md)。

## 输入与验收约定

取得基线与候选的源码版本和可执行文件、目标 GPU 与后端、CPU/RAM/存储、模型与量化格式、模型文件哈希、tokenizer、实际生效配置与环境变量、负载、质量容差、内存预算、延迟或吞吐目标。没有 GPU 或模型仍可做源码和 CPU 检查，但不能据此声称引擎已在该后端跑通。

Strata 的 `setup.py` 是安装与启动脚本，不是 setuptools 打包配置。不要把 `pip install .` 或 `import strata` 当作安装验证。仓库脚本应在源码 checkout 中执行；Python 环境由 `requirements.txt` 描述，原生引擎由 CMake 构建。Setup 可以安装软件并下载大型模型，因此不属于验证用 smoke 命令。

## 流程

1. **固定实验。** 记录两个源码版本、构建选项、二进制哈希、模型哈希、实际配置与环境，以及机器信息。尝试候选前定义成功阈值，保留未参与调优的负载。初次比较一次改变一个因素，再检查因素间的交互。
2. **检查源码和 CPU 行为。** 运行选定的不下载 Python 测试。存在 C++20 工具链时，使用手册中的纯 CPU CMake 配置。成功 configure 或 import 不等于运行时正确。
3. **执行真实后端。** 构建被修改的后端、device self-test 及相关 GPU parity target。分别记录通过、失败、跳过、缺失和不可用。缺少 fixture、指令集不支持或没有加速器都不能算通过。
4. **检查真实模型。** 验证健康状态、模型身份、确定性短回答、prefill/decode 行为和改动涉及的功能。测试工具支持时保留原始 token ID 或 logits。保持原路径精确性的优化应满足相应对齐约定；数值变化则需明确误差范围和任务质量界限。
5. **覆盖状态切换。** 检查缓存恢复、长输入、并发 slot、取消，以及取消后的下一次请求。batch 与 solo 的精确比较需要控制 CPU/GPU 舍入条件；遵循手册，不能把每一次文本差异都认定为调度 bug。
6. **正确性通过后测性能。** 使用当天基线、交替 A/B 顺序、预热、重复运行、实际 token 数、缓存状态，以及明确来自引擎或客户端的计时。报告中位数与范围；报告 p95 时同时给出样本量。区分新输入、缓存复用和首次加载耗时。
7. **复核并决策。** 拒绝违反正确性、质量、内存或必要延迟界限的候选。对于合理取舍保留 Pareto 候选集。交付结论时附命令、退出码、原始输出位置、排除项、风险和剩余硬件验证；不要把只读过源码的想法提升为已测量的默认配置。

## 输出

生成简洁实验记录，包含 `candidate`、`baseline`、`hardware`、`model`、`workload`、`changed_factor`、`correctness`、`quality`、`latency`、`throughput`、`memory`、`errors`、`evidence`、`decision`。每层验证标记为 `PASS`、`FAIL`、`BLOCKED_REQUIRED_BACKEND`，或给出明确理由的跳过。必要后端没有运行证据时，总体验证仍为部分完成。

## 执行边界

本技能内置验证逻辑和命令约定。原生测试二进制、模型 fixture 和服务器应在匹配版本的 Strata checkout 中执行：它们依赖该版本的 C++ 实现、tokenizer、模型文件和后端库。复制进技能会形成另一套容易过期的引擎，因此不捆绑模型、运行时或安装器。操作手册已包含选择与解释检查所需的知识，不要求先打开上游文档；源码链接仅提供出处。
