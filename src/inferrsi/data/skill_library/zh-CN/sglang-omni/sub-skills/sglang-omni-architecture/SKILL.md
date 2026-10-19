---
name: sglang-omni-architecture
description: "追踪 SGLang-Omni 阶段 DAG、调度器、队列、状态所有权与传输，区分已有优化参数和代码扩展。"
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: zh-CN
  skill-root: sglang-omni
  parent: sglang-omni
---

# 架构与搜索空间

用于源码解释、阶段瓶颈、流水线布局变更、队列阻塞和通信缺陷。先读[运行时契约](references/runtime.md)，再检查对应的固定版本源码，不从模型名称推断行为。

1. 确定具体的 `PipelineConfig` 及变体。分别画出普通边（`next`/`route_fn`）、汇聚边（`wait_for`/`wait_for_fn`/`merge_fn`）、流式边（`stream_to`/完成信号目标）和终端结果。阶段列表顺序可能是构造顺序，不是执行顺序。
2. 为每个逻辑阶段标注调度器、所属进程、副本绑定、GPU/TP rank、输入输出张量设备和生命周期所有者。进程副本复制进程中的全部阶段，不等于 TP。
3. 追踪单个请求的准入、预处理、调度器 inbox、模型执行、outbox、下游传输、终端汇总和取消。选择调优参数前先定位最早可观测的等待点。
4. 将建议归类为已有参数、模型专有能力或代码扩展。此版本没有通用传输后端选择器，也没有受支持的 `OmniScheduler.event_loop_overlap` 开关。
5. 检查成功与失败路径：仅等待当前请求激活的汇聚源；有序数据块先于 EOS；取消后不能重新发布状态；发送缓冲区必须保留至正确的完成机制生效。

布局变更后发生阻塞时，恢复已知进程/GPU 布局，比较解析后的路由与副本绑定，再检查本地对象传递条件、传输选择和清理。不要通过丢弃队列数据块或删除 overlap 保护来掩盖生命周期错误。输出所有权图、瓶颈假设、已有搜索空间和验证证据。实测调优转到[服务](../sglang-omni-serving/SKILL.md)，代码修改转到[扩展](../sglang-omni-extension/SKILL.md)。
