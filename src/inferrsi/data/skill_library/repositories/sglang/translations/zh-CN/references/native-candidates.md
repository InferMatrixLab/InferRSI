# 原生候选映射

以下是仓库原生候选，不是已导入依赖。应用前先读取固定文件，再检查目标 checkout 的变化。本快照中 `.claude/skills` 是指向 `.agents/skills` 的仓库别名；可移植来源记录使用真实 `.agents` 文件。带脚本的原生技能在此仅作为参考。

| 原生技能 | 适用情形 | 处理方式 |
|---|---|---|
| [sglang-runtime-context](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/sglang-runtime-context/SKILL.md#L1-L35) | 配置发布、override 与每次前向状态 | 仅参考；检查当前契约 |
| [kernel-organization](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/kernel-organization/SKILL.md#L1-L35) | 内核所有权与迁移 | 仅参考；检查当前契约 |
| [add-jit-kernel](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/add-jit-kernel/SKILL.md#L1-L35) | JIT 实现细节 | 仅参考；检查当前契约 |
| [add-sgl-kernel](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/add-sgl-kernel/SKILL.md#L1-L35) | AOT wheel 内核工作 | 仅参考；检查当前契约 |
| [write-sglang-test](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/write-sglang-test/SKILL.md#L1-L35) | CI 注册与测试入口 | 仅参考；检查当前契约 |
| [kl-consistency-test](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/kl-consistency-test/SKILL.md#L1-L35) | prefill/decode 与缓存命中状态检查 | 仅参考；检查当前契约 |
| [debug-distributed-hang](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/debug-distributed-hang/SKILL.md#L1-L35) | 集合通信顺序与 rank 诊断 | 仅参考；检查当前契约 |
| [debug-cuda-crash](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/debug-cuda-crash/SKILL.md#L1-L35) | 设备失败定位 | 仅参考；检查当前契约 |
| [generate-profile](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/generate-profile/SKILL.md#L1-L35) | 采集 profiling 证据 | 仅参考；检查当前契约 |
| [llm-torch-profiler-analysis](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/llm-torch-profiler-analysis/SKILL.md#L1-L35) | 分析已采集 trace | 仅参考；检查当前契约 |
| [sglang-prod-incident-triage](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/sglang-prod-incident-triage/SKILL.md#L1-L35) | 运行时症状排查 | 仅参考；检查当前契约 |
| [speculative-naming](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/speculative-naming/SKILL.md#L1-L35) | 投机实现命名与边界 | 仅参考；检查当前契约 |

不要仅因原生技能带脚本就复制它们。已有 AREX `sglang_source_smoke.py` 只检查路径/依赖标记；外部构建审计对本快照更具体。本包不捆绑可执行 operating helper。文档命令使用的仓库脚本保留在上游，需要仓库 checkout。

模型集成请使用[模型注册证据](source-map.md#e18)和[模型指南](source-map.md#e37)；`cookbook-add-model` 编写部署文档，不是模型运行时实现契约。返回[并行与扩展](parallelism-and-extension.md)。
