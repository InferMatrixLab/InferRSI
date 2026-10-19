---
name: operation-performance
description: "通过有界实验运行和测量固定版本的 vLLM，覆盖 batching、显存、前缀复用、投机、并行、P/D 传输、编译和量化。"
license: Apache-2.0
metadata:
  disco-role: operating
---

# 运行与性能

现象到参数的推理见[实验决策](references/experiment-decisions.md)；实际运行前读[命令与测量](references/commands-and-measurements.md)。

记录模型与 tokenizer 版本、设备数量/型号/显存与互联、软件和源码版本、生效配置、请求长度分布、到达模式、缓存状态以及时延和质量目标。在目标硬件建立已知正常的基线；没有基线时先做小规模正确性 smoke，再优化。

每次测量一个主要假设。固定负载和质量约束，比较重复的预热后运行，单独记录启动与编译开销。配置和 offered load 都要探索：无限速突发结果不能独立证明可持续服务容量。结果保留失败请求与准入拒绝。

候选配置违反正确性、质量、显存或声明的时延边界时停止该候选，恢复更改的配置并保留日志。用各自信号诊断抢占、排队、传输或集合通信故障；GPU 看似空闲并不能证明增大 batching 会有效。

交付表包含基线/候选配置、成功与错误数、吞吐、TTFT 和 ITL/TPOT 分布、显存峰值、缓存/抢占信号、质量结果及剩余不确定性。只报告实际测得的收益。没有运行资源时，给出准确实验和预期观测并标注未执行。
