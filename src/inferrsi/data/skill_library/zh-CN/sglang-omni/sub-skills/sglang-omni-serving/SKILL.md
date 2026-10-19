---
name: sglang-omni-serving
description: "解析 SGLang-Omni 配置、选择模型专有服务方案，在明确音视频质量约束下调优延迟和吞吐。"
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: zh-CN
  skill-root: sglang-omni
  parent: sglang-omni
---

# 服务与调优

用于 SGLang-Omni 启动、模型方案、最终配置、过载和实测优化。阅读[模型方案与实验契约](references/recipes-and-tuning.md)及根目录[快照](../../references/snapshot.md)。

1. 选择模型对应的方案和接口，保留其平台依赖版本与参考音频要求。启动 worker 前匹配缓存权重与配置类。
2. 用与拟启动命令相同的参数检查 `sgl-omni config resolve` 和 `config explain`，保留配置、差异及来源。解析配置不保证零依赖：模型注册/配置导入或元数据查询仍可能需要可选包、缓存或网络元数据。
3. 在已授权的目标环境中启动最小受支持拓扑。施压前验证就绪、单个请求、输出模态、采样率、完整音频/文本以及流式错误。
4. 在同一数据集、随机种子/采样、时长分布、质量评分、硬件和依赖版本下记录预热基线，每次仅改变一个因素。一起比较成功且满足质量要求的完成量、延迟分布、音频时长/RTF、失败和质量。
5. 质量、完成率、显存或尾延迟回退时恢复基线，保存逐请求产物和服务日志。定位饱和队列后再提高并发。

启动失败时先检查最早的缺包/配置/工厂错误，不要直接提高显存比例。OOM 时区分权重、KV、图捕获、vocoder 和通信池，核算跨进程显存预留，最小修改后重跑同一负载。503 时检查准入、请求构造和 AR 队列。HTTP 200 后没有音频时，确认语音模式，并检查 SSE 错误事件和 EOS。交付可复现的命令/配置改动及实测证据，不承诺未经测量的加速。
