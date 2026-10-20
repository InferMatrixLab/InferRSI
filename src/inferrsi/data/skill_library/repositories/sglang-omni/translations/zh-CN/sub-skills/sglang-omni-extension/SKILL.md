---
name: sglang-omni-extension
description: "扩展 SGLang-Omni 模型、阶段或运行时契约，选择配置、生命周期、流式与硬件原生验证。"
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: zh-CN
  skill-root: sglang-omni
  parent: sglang-omni
---

# 扩展与验证

用于新增模型/阶段，或修改调度器、载荷、传输和配置契约。阅读[集成与测试映射](references/integration.md)，在目标仓库中遵循其 `AGENTS.md` 及引用的编码约定。

1. 明确支持的模型 architecture、权重、接口及预期输入输出行为。按调度和状态需求选择最接近的已有流水线，不仅按模态选择。
2. 把修改放到正确所有者：拓扑属于模型 `config.py`，输入规范化属于 request builder，批处理/生命周期属于调度器，forward 专有逻辑属于 runner，传输属于 comm，依赖属于平台清单。
3. 共享框架契约保持与模型无关。实现最小适配器并明确状态和生命周期契约；只有语义相符时才复用现有状态、预处理、参考编码和 vocoder 辅助设施。
4. 验证成功执行、非法输入、预处理期间取消、迟到数据块、EOS/flush、重复请求和清理。为受影响契约补充已有的聚焦原生测试；mock/无 GPU 测试不能证明模型质量。
5. 在目标硬件比较流式与非流式输出、usage/finish reason、质量和延迟，并覆盖基线与并发负载。明确列出未运行的硬件检查。

发现阶段跳过模型时，先读导入错误和 architecture 注册再修改 registry。工厂参数失败时追踪消费方，不要静默忽略。拆进程后共享状态失效时，将所需状态放到受支持的载荷/服务边界，或恢复同进程布局。交付最小补丁、测试证据、剩余平台验证项与回退路径。
