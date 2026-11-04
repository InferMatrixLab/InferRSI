# 按优化方向扩展任务：开源调研与首批选择

2026-11-04。本轮是官方源码、任务文件、许可证及论文的调研与设计交付；没有执行新增题目、调用模型或运行设备实验。以下五类是阅读分组，映射到已有 [SearchSpace](../../../searchspace-matrix.md)，不另建权威分类，也不把“找到来源”记成实测覆盖。

## 本轮决定

**保留 Softmax/RMSNorm 作为算子接口试点；下一批重点增加真实仓库 CPU 热路径和内存管理任务，设备明确后再接通信及服务性能。** 每类先做一个完整任务，验证裁判、计时和结果用途后再扩充数量。

AgentKernelArena 适合学习 kernel 任务的提交与独立评测；整个 InferRSI 还需要仓库补丁、状态管理、资源配置和服务工作负载。不能把所有任务都变成 `compute(x)`，也不能把功能修复的通过率叫作性能提升。

| 类别与任务卡 | 给 Agent 的具体问题 | 优先来源 | 当前状态 / 次序 |
| --- | --- | --- | --- |
| [① 算子计算](01-operators.md) | 在既定输入和数值约束下优化 Softmax/RMSNorm 实现 | KernelBench、AgentKernelArena、BackendBench | 已有 CPU 试点；先修完测量资格，不急于再加同类算子 |
| [② CPU 热路径与运行时](02-host-runtime.md) | 大量 added tokens 时，保持分词结果不变，降低编码开销 | GSO 的 Tokenizers 历史优化任务；SWE-fficiency 的任务契约 | **下一项新增任务首选**；真实 repo-patch adapter 和历史环境尚未实现 |
| [③ 内存与缓存](03-memory.md) | 正确处理异步完成与 KV 回收；随后优化混合尺寸分配的容量和开销 | 已有 RSI KV 任务、vLLM、Mooncake | **先接已有任务**，保留原资格边界；Mooncake 为下一独立新题候选 |
| [④ 多卡通信](04-communication.md) | 固定拓扑/消息量下优化 collective 实现或配置 | nccl-tests、MSCCL-tools、MSCCL++ | 先固定任务契约，实际带宽/延迟等待目标设备；CPU 符号检查单独标记 |
| [⑤ 服务配置与调度](05-serving.md) | 固定模型、请求和质量要求下，优化首 token 延迟或有效吞吐 | InferenceBench、llama.cpp、vllm-evolve；Apple RSI-Inference Bench 作真实引擎扩展参考 | 硬件及模型明确后执行；CPU llama.cpp 也是候选，但仍需模型资产与质量裁判 |

第一阶段从“多做两道数学题”转为“三种不同问题的试点”：算子计算、CPU 分词、状态回收。状态回收是既有工作，接入不算新造题；也不因此宣布内存容量、GPU kernel 或服务端到端全部覆盖。

## 哪些开源项目更适合借鉴

以下采用决定由本次调研提出，不表示维护者已接受扩展范围。固定版本链接用于复查源码；具体任务卡保留更多测试、指标和适配条件。

| 来源及已检查内容 | 固定版本 / 许可 | 采用什么；为什么不整体搬入 |
| --- | --- | --- |
| [GSO：任务与实际 grading](https://github.com/gso-bench/gso/blob/32d78b331d59ed689b1238789dc20d36576951c0/src/gso/harness/grading/evalscript.py) | `32d78b3`；代码 MIT，目标 Tokenizers 为 Apache-2.0 | 借真实仓库 base / expert / candidate 三方、输出等价检查与性能 workload；选择推理相关 encode 任务。历史工具链、数据资产与测量资格须重新验证 |
| [SWE-fficiency：TestSpec](https://github.com/swefficiency/swefficiency/blob/12d32a2d6800824a7d84bdb6797b5708e7b7957f/swefficiency/harness/test_spec.py) | `12d32a2`；代码 Apache-2.0，README 声明其他材料 CC-BY-4.0 | 借 correctness tests、performance workload、独立 profiling script 的分工。通用科学 Python 任务不全部适合推理，不导入整套 runner 或总分 |
| [SWE-Serve：adaptive allocation](https://github.com/NVIDIA/swe-serve/blob/84d8fd92739a4a76ceddba56e5a70605921c4ad2/tasks/ss-sgl-adaptive-allocation-safety/task.toml) 与 [score](https://github.com/NVIDIA/swe-serve/blob/84d8fd92739a4a76ceddba56e5a70605921c4ad2/tasks/ss-sgl-adaptive-allocation-safety/tests/score.py) | `84d8fd9`；Apache-2.0 | 借真实 SGLang 状态/容量修复题与 F2P/P2P。所读题为 correctness 评分，没有速度分；“CPU 任务”仍可能要求较大容器资源 |
| [ISO-Bench](https://github.com/ISO-Bench/ISO-Bench/blob/9cc08ddd1011a34c49b43c22671ae639f16a21d3/README.md) 与 [固定数据卡](https://huggingface.co/datasets/ISO-Bench/ISO-Bench/blob/24ef5d04b4993aca5e0d2cfa64b51cb40fc4cb55/README.md) | 代码 `9cc08dd` Apache-2.0；数据卡 `24ef5d0` CC-BY-4.0 | vLLM/SGLang 性能提交可作为后续真实引擎补丁题源。论文的 54 题与所读数据卡的 106 题是不同版本；具体行来自实时接口，尚未绑定固定 parquet，部分题命令读取失败，不称为已可复现 |
| [Apple RSI-Inference Bench](https://github.com/apple-aiml-research/ml-rsi-inference-bench/blob/1a38072fbe284234c874356b86c9df666a5a79a3/README.md) | `1a38072`；[Apple Sample Code License](https://github.com/apple-aiml-research/ml-rsi-inference-bench/blob/1a38072fbe284234c874356b86c9df666a5a79a3/LICENSE)，不是 MIT/Apache；README 的论文仍为 coming soon | 更贴近整个推理系统：模型接入、实现优化、性能回归修复。优先借真实引擎任务设计；1–8 张 H100/B200、大模型与长执行预算不适合当前轻量首批 |
| [InferenceBench：任务与评测入口](https://github.com/aisa-group/InferenceBench/blob/108ec747fab0bd92fd9de501f62157d074c50ed5/README.md) | `108ec74`；Apache-2.0 | 借服务 launcher、不同负载、独立质量门槛、同预算非 Agent 搜索对照。完整原生流程有指定 GPU、数据缓存及模型裁判，不直接移植平台 |
| [Mooncake：分配 benchmark](https://github.com/kvcache-ai/Mooncake/blob/e5ef0e427a49cd2f8ad5b4356b09435095030439/mooncake-store/benchmarks/README.md) | `e5ef0e4`；Apache-2.0 | 借混合尺寸分配/释放 workload、分配失败与碎片指标，并绑定独立 allocator tests；先验证最小 C++ 构建，不把逻辑容量称为 HBM 节省 |
| [nccl-tests](https://github.com/NVIDIA/nccl-tests/blob/afd59abab774a6a4b492eb344bd0c845a0b7bb4d/README.md)、[MSCCL-tools](https://github.com/microsoft/msccl-tools/blob/030a750fc56e03fb863ffe48268672d84d4cdc7b/tests/test_language.py)、[MSCCL++](https://github.com/microsoft/mscclpp/blob/f5643de98b0c174baa3af2b2e6126f93dd07dc06/test/mscclpp-test/allreduce_test.cu) | `afd59ab` BSD-3-Clause；`030a750` / `f5643de` MIT | 分别提供真实测量、可检查的通信计划、自定义 collective。需要明确候选修改面；硬件测试工具本身不是 Agent 优化题 |
| [llama.cpp：llama-bench](https://github.com/ggml-org/llama.cpp/blob/149f5641b931aaf33697d70f9abc90c3e5300247/tools/llama-bench/README.md) | `149f564`；MIT | 借 CPU prefill/decode、线程/batch 配置与逐次样本。固定模型资产后可先做 CPU；计时工具不自动提供质量 oracle |
| [vllm-evolve：plugin](https://github.com/JiusiServe/vllm-evolve/blob/43cc82c2c649699fb166339f85de2c8f79f2db4e/targets/scheduling/plugin_template.py) | `43cc82c`；实际 LICENSE 为 Apache-2.0 | 借窄 admission 策略入口与实际生效证明。当前主要重排 FCFS waiting deque；不能按 roadmap 声称已有 KV eviction/routing 或模拟平台 |
| [AutoTuneBench](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/README.md) 与仓内 [已核查参考](../../../../src/inferrsi/data/skill_library/methods/inference-benchmark-design/references/autotunebench-trial-validity.md) | `64cc8d7`；选定代码/数据 MIT，vendor 许可分开 | 借 treatment 是否真正送达、原始记录与资格先于收益的审计方式。既有审查已发现声明与部分执行路径不一致，不把 README 的完整流程当作已验证实现 |

不优先使用 PIE/MLGym 扩充本轮题数：前者以竞赛程序与模拟 CPU 为主，后者主要优化 ML 质量/奖励，且许可与训练成本另有约束。它们的任务组织经验有价值，但不是当前推理工程性能题的直接替代。

## 两个尤其贴近 RSI 的题例

**真实仓库热路径：Tokenizers.encode。** 固定原始仓库和 tokenizer 资产，Agent 用 profile 找大量 added tokens 的开销，修改 Rust/Python 代码，提交 patch；裁判检查 token IDs、tokens、offsets 等语义，再比较编码时间。它直接验证 CPU 分词优化，不直接证明服务 TTFT。具体 base/expert 身份及资产冻结缺口见[任务卡](02-host-runtime.md)。

**真实引擎回归：SGLang 流式 decode 吞吐下降。** Apple 的 [instruction](https://github.com/apple-aiml-research/ml-rsi-inference-bench/blob/1a38072fbe284234c874356b86c9df666a5a79a3/tasks/regression_sglang_stream_decode_tps_c1/instruction.md) 与 [task.toml](https://github.com/apple-aiml-research/ml-rsi-inference-bench/blob/1a38072fbe284234c874356b86c9df666a5a79a3/tasks/regression_sglang_stream_decode_tps_c1/task.toml) 给出真实 baseline、流式 workload、输出保持、scored/guard 条件；并允许不同修复机制。这比指定“必须写某个 kernel”更接近 RSI 的瓶颈调查。但该题固定 4×B200 和大模型；其环境清理脚本有枚举 GPU 进程的操作，不能直接移植到共享机器。当前只借设计、保留来源，未执行或复制脚本。

Apple 的另一个 [vLLM 源码优化题](https://github.com/apple-aiml-research/ml-rsi-inference-bench/blob/1a38072fbe284234c874356b86c9df666a5a79a3/tasks/optimize_qwen3_6_27b_1xh100_open/instruction.md) 允许热路径、布局、融合等多种改法，但不计纯配置修改；InferenceBench 则允许更开放的服务配置选择。两者不是谁更“完整”，而是考察不同搜索范围。InferRSI 应分别声明代码任务和配置任务，避免同一排行榜混用规则。

## 论文怎样影响选择

| 一手来源 | 本次采用的结论 | 不由此推导什么 |
| --- | --- | --- |
| [GSO §2.1–2.2](https://arxiv.org/html/2505.23671v3#S2) | 从真实优化提交提取 base、workload、等价检查和 expert control；Agent 提交真实 patch | 历史提交更快不等于我们的环境更快；参考答案不是唯一合法算法 |
| [ISO-Bench](https://arxiv.org/abs/2602.19594) | 从真实推理引擎的优化 PR 中挑代表任务；执行指标与诊断/机制分析分别保留 | LLM 对补丁的相似性/意图评分不能替代数值、质量及性能实测；不要求 Agent 复制人类补丁 |
| [InferenceBench §3、§5](https://arxiv.org/html/2607.20468v1#S3) | 分开 prefill、decode、并发目标；固定质量标准；后续搜索实验加入同预算 random/TPE/SMAC 等对照，检查最终提交是否保留最好有效候选 | 论文中 Agent 或搜索基线的排名不能迁移到 InferRSI；本轮没有执行该实验 |
| [性能 benchmark 可靠性研究 §III–IV](https://arxiv.org/html/2607.01211v2#S3) | 在接入任务前重放参考优化、做同码对照，分开任务有效性与 Agent 成绩；报告分项结果，不急于做一个总分 | 作者跨机结果不代替我们的硬件资格；“能运行”不等于性能信号稳定 |

软件测试、公开论文、源码检查、真实运行证据分别记录。上述论文/仓库的收益数值没有被用作本次本地结果或默认阈值。

## 对接口和流程的具体影响

不同类别共享“任务/环境/验收规则固定 → baseline/profile → 候选 → 独立检查 → 比较 → 结果与决定”的过程，候选形式不能只支持一种：

| 候选形式 | 对应题型 | 与当前实现的关系 |
| --- | --- | --- |
| 一个受限实现文件 | 已有算子；已有 KV 的 `candidate.py` | NumPy adapter 与 KV replay 是两条既有路径，语义/计时不同；接入时保留各自裁判与冻结身份 |
| 固定仓库上的 patch | Tokenizers、Mooncake、引擎回归 | **待实现 repo-patch adapter**；独立构建、受保护测试、完整产物和对应 baseline；不让模型改裁判 |
| 声明的配置或 launcher | llama.cpp / 服务配置 | **待实现对应任务适配**；锁定模型、请求量和设备，检查实际启动/生效的配置及最终服务器 |
| collective 算法或候选库 | 多卡通信 | 待选设备后实现；符号验证、编译、真数据校验、计时分别记录 |

复用现有 Workbench 的执行、AB/BA 和证据，不把 GSO、Pier、Harbor、InferenceBench 的控制器全部引入。上游 task 包是素材和契约来源；任何新执行环境或多文件候选都需要其自身的产物隔离与验收，现有单文件 sandbox 不能自动覆盖仓库 build/server。

Profiling 保留独立阶段与原始产物。若以后评估“给 Agent profiler 反馈是否有用”，还应保留反馈进入下一次 Agent 输入的证据；生成了一份 profile 本身不足以证明它发挥了作用。

## 新任务入库前怎样验证有用

1. **来源与可重现性：** 固定仓库、base、参考修复、数据/模型、编译环境和许可证；公开历史参考修复不提供给 Agent。公开题只能作为 development 或受限条件下评测，不能冒充天然未见 holdout。
2. **裁判区分度：** 正确基线、参考优化、错误但快的变体都实际运行；错误结果不得获得可用于选择的性能分数。
3. **测量资格：** 同码 A/A 和 no-op 不应被当作进步；参考优化在选定环境确有可分辨信号。保留失败、波动与全部原始样本，无法分辨就暂不用于性能排名。
4. **目标覆盖：** 计时工作负载、非计时语义边界、guard 工作负载分开说明。不能缩短输入、少处理请求或减少分配来换取虚假加速。
5. **真实接入：** 源码/编译产物/配置确实进入最终执行；profile 和结果可追溯。用一条演练证明报告支持“保留/放弃/证据不足”的决定。
6. **能力评测另做：** 任务资格成立后，固定模型与预算做 Agent/skill/搜索策略对照；记录失败成本、有效尝试数、最终质量和性能。不把一个新任务的通过当成整个 RSI 变强。

每个方向分开报告“找到来源、已适配、正确性验证、性能资格、Agent 对照”的状态。第一版不将内存、延迟、带宽或功能通过率压成一个未经论证的总分。

## 与四个子项的关系及本轮产物

- **#334 调研：** 本文与五类任务卡补充原来的算子选型；首批扩展优先级已明确。
- **#335 接口：** 识别 repo-patch / launcher / 多进程任务的真实差异；这些是下一步设计输入，尚未新增通用 adapter。
- **#336 任务：** 保留原两题；CPU 分词是新增首选，KV 是既有任务复用，其他候选按任务卡分阶段实施。
- **#337 接入验证：** 按上面六项资格步骤验证真实用途；现有正式 SkillEval correctness 接入仍只支持它已声明的内置题。

本轮新增的是可复查的来源选择和任务设计文档。没有修改历史证据、SearchSpace 成熟度、现有任务或执行协议，也没有宣布新类别已经能运行。范围扩展与具体硬件/模型验收仍需沿原 Issue 跟踪。
