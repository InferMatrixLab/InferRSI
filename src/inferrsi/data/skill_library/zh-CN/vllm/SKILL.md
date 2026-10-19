---
name: vllm
description: "分析和使用 vLLM 推理引擎：V1 调度、KV 与前缀复用、并行拓扑、投机解码、后端选择及可测量的性能实验；将源码改动路由到针对性验证。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# vLLM 推理引擎

当任务需要解释 vLLM 如何执行请求、选择已有推理控制项，或定位范围明确的引擎改动时使用。本图是基于单一源码快照的可移植候选技能，不代表完整仓库或全部硬件覆盖。

依赖默认值或兼容性前，先读[源码快照](references/repo-provenance.md)。提交不同，需重新检查受影响代码和 CLI。模型版本、tokenizer/chat template、硬件与后端、流量长度与并发、时延或吞吐目标决定有效路径；只在缺失信息影响下一步时澄清。

| 需求 | 阅读 |
|---|---|
| 追踪 token step、理解 KV 生命周期、区分已有参数与新增机制 | [架构与搜索空间](sub-skills/architecture-search-space/SKILL.md) |
| 定位 OOM、排队或时延；选择 TP/PP/DP/EP、投机、P/D、编译或量化实验 | [运行与性能](sub-skills/operation-performance/SKILL.md) |
| 修改调度器、缓存、连接器、attention、量化或编译行为并验证正确性 | [扩展与验证](sub-skills/extend-validate/SKILL.md) |

交付有证据的结论：当前机制 → 有边界的决策或改动 → 预期可观察现象 → 正确性与性能检查。区分源码事实、假设和实际执行结果，不把 help、import、合成基准或 AST 检查说成推理或性能验证。

维护 token 计数、完成与取消行为、KV 所有权和语义缓存身份。量化改动要检查质量；投机要检查验证语义；并行与传输改动要检查拓扑和生命周期。只加载相关子技能及其引用。

沿用用户对模型运行和基础设施操作的已有授权。消耗资源前明确实际模型、目标资源和有界运行规模。源码或模型插件可执行代码；运行 setup 或启用 remote code 前先检查相关内容。本图不包含安装或修改环境的助手脚本。

机器契约：[路由](references/repo-routing-metadata.json)、[来源](references/repo-provenance.json)、[证据映射](references/evidence-map.json)。人工参考资料已打包，不依赖现场安装 AREX。API 请求细节、完整模型接入、全部加速器与穷尽式 kernel 覆盖不在本图范围内。
