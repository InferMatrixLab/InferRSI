---
name: omni-serving
description: "配置并评测受支持的 vLLM-Omni 部署、流式输出与阶段放置。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 服务与调优

读取[服务操作参考](references/serving.md)，获取版本对齐、启动模板、实验顺序和故障恢复；选择搜索变量时参照[架构表](../omni-architecture/references/architecture.md)。

从选定模型支持的默认部署开始。保存模型、平台、YAML、CLI 解析后的有效配置；从日志确认实际阶段放置和后端。解析器接受配置不等于运行时支持该组合。

先跑固定短请求，再增加并发；分开测编译/预热、排队、推理、传输和输出编码。音频记录首媒体包及块间隙；图像/视频记录端到端延迟、尺寸/时长与质量，文本 token 吞吐不能替代这些指标。

先定位瓶颈，再调整 TP、副本、批大小或异步缓冲。正确性出现变化时保留失败证据，恢复到最后有效基线；相关状态、传输和模型检查见[验证](../omni-validation/SKILL.md)。
