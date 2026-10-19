---
name: sglang-omni
description: "操作、解释、调优和扩展 sgl-project/sglang-omni 多阶段 omni、语音与 TTS 推理，依据源码核对拓扑、传输和质量。"
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: zh-CN
  skill-root: sglang-omni
---

# SGLang-Omni

操作和扩展 `sgl-project/sglang-omni` 的多阶段运行时。它负责流水线拓扑、进程与阶段生命周期、传输、模型适配和服务；适用的自回归阶段组合使用上游 SGLang。这是独立于 `sgl-project/sglang` 的仓库。使用 SGLang 文本服务或 `multimodal_gen` 的参数前，应追踪本运行时中实际消费该参数的代码。

提出建议前，先确认模型与权重版本、输入输出模态、接口、平台及依赖、GPU 拓扑与显存、并发量、延迟和质量目标。仅分析代码时，记录未知的运行环境信息，不虚构部署条件。

| 工作 | 加载 |
|---|---|
| 解释 DAG、定位状态所有权、分析调度和传输、选择已有优化面 | [架构与搜索空间](sub-skills/sglang-omni-architecture/SKILL.md) |
| 解析配置、启动模型服务、在质量约束下调优延迟与吞吐、排查过载 | [服务与调优](sub-skills/sglang-omni-serving/SKILL.md) |
| 新增阶段或模型、修改运行时契约、选择回归测试 | [扩展与验证](sub-skills/sglang-omni-extension/SKILL.md) |

安装或提供版本敏感建议前，阅读[快照与依赖](references/snapshot.md)；通过[来源记录](references/repo-provenance.md)检查版本漂移。只加载任务需要的分支。

以同一基线推进：记录最终配置和源码版本，每次改变一个有明确范围的因素，再验证受影响的契约及端到端目标。交付时给出实际改动、证据、剩余不确定性和回退配置。CPU 配置测试不能证明 GPU 服务、数值质量或性能。此图是可移植候选包，不代表已通过 AREX 运行时导入验收或硬件基准测试。
