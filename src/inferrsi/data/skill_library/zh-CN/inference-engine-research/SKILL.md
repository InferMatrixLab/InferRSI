---
name: inference-engine-research
description: "在 Strata、vLLM、SGLang 及两个 Omni 仓库间路由推理引擎研究，形成有源码依据且受正确性约束的搜索与验证计划。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 推理引擎研究总入口

用于比较架构或设计受约束的推理引擎搜索。用户指定仓库时，直接读取相邻的该仓库入口。使用本总入口需保留全部六个相邻根目录；五个仓库 Skill 也可各自独立分发。

| 问题 | 路由 |
|---|---|
| Strata 异构 MoE、CPU/GPU 专家放置、内存与推测执行 | [strata](../strata/SKILL.md) |
| vLLM token 调度、KV/前缀复用、执行/并行或模型接入 | [vllm](../vllm/SKILL.md) |
| SGLang 调度、Radix/HiCache、prefill/decode、并行运行时或扩展 | [sglang](../sglang/SKILL.md) |
| SGLang-Omni 流水线、stage/scheduler 归属、流式与传输 | [sglang-omni](../sglang-omni/SKILL.md) |
| vLLM-Omni 模型/部署分离、AR/扩散执行、阶段传输及异构输出 | [vllm-omni](../vllm-omni/SKILL.md) |

## 比较流程

1. 固定模型/checkpoint/tokenizer、模态、硬件/互联、软件版本、输入输出分布、到达/并发模式、延迟 SLO 和质量契约。只询问会改变决策的缺失事实，否则明确可逆假设。
2. 加载最相关的仓库分支。比较功能名称前先追踪工作单位、状态归属、调度、内存、通信、输出及清理。
3. 把候选分成三类：已支持的已有配置；保持语义的实现修改；带新增假设或近似预算的研究扩展。
4. 先检查约束再跑 benchmark：模型/后端组合、内存/生命周期、分区/布局、数值/质量、取消/终止、队列稳定性。
5. 用同条件真实负载测量。区分 CPU/静态、mock 契约、加速器/原生传输、真实模型质量、服务性能证据；不能把低层证据升级成更强结论。
6. 输出带源码依据的候选、交互项、测试、预期观察及恢复方式。只有有效运行参与排名，目标冲突时报告 Pareto 前沿，不编造通用最优方案。

## 跨仓库迁移规则

DP/EP/TP、batch size、prefix cache、async execution、streaming 在不同引擎中可能含义不同。先翻译职责和能力契约，再迁移参数或优化。不能假设 Omni 仓库接受独立获取的基础引擎 HEAD；本包快照不是兼容性矩阵。

文本 TTFT/TPOT 与媒体首包、块间隙、端到端完成、RTF、图像/视频吞吐及质量需分开测量。减少步数、分辨率或输出长度会改变负载/质量契约，必须披露。

五个仓库根目录均包含固定来源与源码证据。整体是可移植候选 Skill；GPU、原生分布式和质量验证需目标环境。本包未实现新引擎，也不包含实测加速比。
