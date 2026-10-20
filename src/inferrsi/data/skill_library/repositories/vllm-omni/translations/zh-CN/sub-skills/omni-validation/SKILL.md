---
name: omni-validation
description: "扩展 vLLM-Omni 流水线、输出契约、runner 或 connector，并选择正确性门槛。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 扩展与验证

修改拓扑、流式状态、扩散执行或传输前，读取[扩展与验证契约](references/validation.md)。按变更职责及实际后端选择测试。

先明确参考模型语义以及完整生产者/消费者契约。保持每请求 RNG、累积输出/状态、副本亲和性、取消语义和资源生命周期；既验证正常完成，也验证故障路径。

证据逐级提升：静态检查 → CPU/原生契约测试 → 所需加速器数值一致性 → 真实模型媒体质量 → 同条件性能。必需后端不可用时，该结论记为 `BLOCKED_REQUIRED_BACKEND`，不能用 import 或 mock 替代。

失败时区分环境问题、原生失败和 Skill 知识缺口；最小修复后重复受影响检查。报告命令、版本、输入身份、实测输出和未验证项。相关正确性门槛通过后再进入[服务调优](../omni-serving/SKILL.md)。
