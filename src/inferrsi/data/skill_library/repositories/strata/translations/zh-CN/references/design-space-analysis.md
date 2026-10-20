# 用 AI 生成 Strata 式推理引擎：仓库分析与搜索空间

**核心结论：搜索对象是内存约束下的专家放置、异构计算分工和状态管理的联合设计。** 只搜索 CUDA kernel 参数，会遗漏大量端到端收益；只增加 GPU 专家缓存，又可能挤掉 KV、MTP 或 prefill 工作区。

这里把“用 AI 生成”理解为：AI 提出配置或代码候选，由明确验证器筛选，保留可复现基线。目标模型、硬件、工作负载和质量门槛先固定；如果允许同时换模型或硬件，应作为单独外层搜索，并重新定义可比性。

交付的 [中文 Skill](../SKILL.md) 和 [English Skill](../../../SKILL.md) 都包含设计、调优、验证三个分支。详细构建与检查见 [verification](../../../../../workflows/inference-engine-research/references/import.md)。

## 先分清三层搜索

| 层次 | AI 可以生成什么 | 接受条件 |
|---|---|---|
| 现有参数层 | 合法 flags、env、布局预算、CPU worker、spec/prefill/batch 配置 | 实际生效、容量满足、质量和端到端指标过关 |
| 算法与代码层 | 专家准入/替换、CPU/GPU 分流、预取、融合、tile、队列、checkpoint 策略 | 接口与状态契约保持、编译/parity/并发回归通过，再做实测 |
| 模型与系统扩展层 | 新量化、专家剪枝、新模型族、通用并行或多机能力 | 新基线、新实现与质量预算，不能沿用“等价优化”的结论 |

**不是自由搜索变量的内容：** 固定 checkpoint 的张量形状、路由语义、tokenizer、RoPE/state 对齐、speculative acceptance/rollback 正确性；以及既定硬件和业务要求下的容量、安全余量、请求语义。改变这些必须显式转入另一个实验。

## 一个可用于 AI 搜索的形式化约定

设 `H` 为硬件/后端，`M` 为模型，`W` 为负载，`C` 为配置或代码候选：

```text
minimize [TTFT_p95(C), ITL_p95(C), -throughput(C), energy_per_token(C)]
subject to:
    peak_VRAM_i(C) <= budget_i                 for each GPU
    peak_RAM(C) <= host_budget
    quality_drop(C, reference) <= epsilon
    state_correct(C) and backend_supported(C)
```

这是建议的评价框架，不是 Strata 自带的完整搜索器。只保留业务实际关心且能够测量的目标；没有功耗计量就不要填能耗结果。单用户聊天更看重 TTFT/ITL，多用户更看重吞吐及尾延迟；不能直接拿二者的“最优”互换。

建议搜索顺序：内存可行性 → CPU/PCIe/专家驻留 → prefill/KV/MTP 联合取舍 → 实测热点 kernel → 并发/多 GPU → 单独质量预算下的近似优化。现有 `tools/calibrate.py` 已覆盖一部分 decode 参数校准，先利用它，而不是重新发明同样的 sweep。

给 AI 的每个候选任务至少包含：允许修改的文件/接口、瓶颈证据、参考实现、质量与资源门槛、固定负载、测量次数、失败回退方法。每轮执行“生成差异 → 静态与编译 → 数值/状态 → 小规模筛选 → 完整 A/B → 保留 Pareto 候选”，不让 AI 自己口头判定成功。

下文给出仓库级证据和 15 个维度。数据均来自固定提交的静态分析；没有将上游宣传速度作为本次实测。

---

## 详细仓库证据

分析基线：`Niko1221/Strata`，commit `296b59d2f73c8f04a805df29c2fa97655adace78`，2026-10-14 检查；CMake 版本为 `0.1.44.1`。这是源码分析，没有独立复现上游速度或质量测量。证据链接均固定到该 commit。

内容索引：能力边界；执行流程；搜索维度；条件依赖；数值契约；实验设计；证据索引。

## 1. 定位与架构特征

Strata 的主路径是面向特定模型的异构推理引擎：GPU 计算 dense/state 部分，GPU 缓存常用 MoE 专家，CPU 计算其余部分专家，也可将一部分 miss 传到 GPU 计算，SSD 支撑 n-gram 查表。最值得搜索的是**内存约束下的放置策略与执行调度联合优化**，并非只改进矩阵乘法。

Flash-Next 路径的编译几何声明：hidden size 2560、48 个 trunk layer、每层 512 个专家、top-10 路由，剪枝版本可携带更少的专家。每四层一层 QSA，即 36 层 Gated DeltaNet 加 12 层 QSA。四条 hyper-connection residual stream 和 PLE history 也是状态契约的一部分。这些数字描述当前模型路径；不能一边任意搜索模型结构，一边声称保持原 checkpoint 的语义。[E1]

不要沿用文档中“只能执行一个模型”的旧说法。当前源码也把 `qwen35moe` 派发到独立的 Qwen3.6-35B-A3B CUDA/HIP 路径，其参数和能力需要另行检查。CUDA 和 HIP 是不同构建选择；SYCL 是独立实验后端。Metal 有较新的专用内核和内存行为，Mac 文档仅报告两台 Mac 的测量，不能据此推断所有后端已全面对齐。[E2–E4]

## 2. 执行流程

**控制层。** Python 的 `StrataEngine` 以 `--serve` 启动可执行文件，通过子进程管道交换文本命令和 token 事件。默认服务将请求排队；可选 batch slot 保存各自的序列状态，并把多请求的 row 合并执行。API 兼容、tokenization、chat template、取消与准入，和内核调度属于不同层。[E5, E16]

**模型与状态准备。** GGUF metadata 需要符合模型家族及编译几何。Dense projection、shared expert、router、residual 计算、output head、session state 和可选 MTP 占用设备内存；expert profile 决定 GPU 专家缓存初始布局。Flash-Next 的主机路径可使用 pinned expert arena、映射专家文件，或只保留 RAM complement/预算内专家。PLE 通过有界 reader 和 row cache 读取。实际运行默认值还受 setup、架构默认表、命令行和环境变量影响，不等于裸 `Options` 的字段初值。[E1, E6, E19]

**Prefill。** 分块读取 prompt。Dense projection 使用矩阵乘法内核，recurrent layer 逐块推进，路由的 row 按专家分组。驻留专家直接从 VRAM 读，其余专家通过 copy stream 的 staging ring 流入。Prefill 工作区可临时借用 expert cache，decode 前再补回。短 chunk 还存在带条件的 CPU 分担路径。增大 chunk 能摊薄专家传输，但增加工作区并可能推迟其它请求。[E7, E8]

**Decode/verification。** MTP 或 suffix lookup 提出草稿 token，verify window 把已接受的输入 token 和草稿一起送入 trunk。每层先对多 row 中重复的 expert ID 去重，再将工作分到 GPU resident hit、通过 PCIe 读取的一部分 nonresident expert、CPU job，以及可选 peer/helper GPU job。先发布 GPU plan，再让 CPU/GPU 重叠计算。因此“cache miss 全部交给 CPU”并不准确。[E9, E10]

**CPU/GPU 交接。** Captured GPU graph 与 mapped pinned doorbell 交换 activation、路由、序号和完成标志。代码显式处理 Windows 驱动提交行为：轮询内存同时查询驱动。只换成普通内存自旋并不等价。[E11]

**推测提交。** Verify 暂时追加 KV/indexer 项；accepted-prefix commit 才推进 recurrent/conv state、修复 indexer tail，并恢复相应的 PLE history。被拒绝的 KV cell 只能在后续 query 读取前覆盖。MTP 有自己的 KV 和 residual/token 对齐语义。Draft policy 根据期望接受 token 数与实际 round 时间，在 MTP 和 suffix lookup 之间选择。[E12–E14]

**自适应驻留。** 主机统计被路由的专家；逐层比较热门 miss 与冷门 resident，按收益排序候选交换，并限制每轮交换数；计数会衰减。与 verify 重叠时，以每层 copy 完成状态作为门槛，防止 residency pointer 暴露尚未到达的数据。缓存存储与自适应替换策略是不同职责。[E6, E15]

## 3. 搜索维度

这是有条件的结构化空间，不能直接做全笛卡尔积。**已有配置**表示已存在 knob；**算法替换**表示在现有契约下修改代码；**新增能力**表示还要实现并验证的扩展。

| 维度 | 已有配置或机制 | 可替换算法／新增能力 | 主要取舍与门槛 |
|---|---|---|---|
| 模型与数值契约 | GGUF family 检查；native quantized pack；Q2/IQ/K quant 路径；条件化 NVFP4 支持 | 新量化格式、任意模型家族、通用算子 IR | 权重字节数、带宽、质量、内核覆盖。新几何并非简单配置变化。 |
| 内存放置 | `--expert-cache`、`--expert-profile`、`--vram-reserve-mib`、`--mmap-experts`、`--resident-experts`、`--resident-budget-gib` | 学习或成本驱动的放置；按边际收益跨层分配 | 更多专家在 VRAM 可减轻 CPU，但挤占 KV、MTP、prefill 空间。 |
| 替换策略 | `--adapt-every`、`--adapt-swaps`、`--adapt-decay`、`--adapt-min-gain`、`--adapt-async`、profile save | LRU/LFU 变种、带宽感知准入、复用距离预测 | 交换字节数和陈旧度对命中收益；保持表与指针有效，避免评价 trace 泄漏。 |
| CPU/GPU 工作划分 | `--pcie-frac`、`--pcie-mode auto/dma/kernel/direct`、自动 share 修正；GPU hit group 与 CPU miss group | 按层或工作负载建立成本模型；新分流规则 | CPU RAM 带宽与 PCIe 加 GPU 成本；必须有合法 pinned source 和 staging 容量。 |
| CPU 调度 | `--pool-workers`、`--pool-tasks`、`--pool-affinity`、`--host-core`、`--aux-cpus`、多 token row-split job | NUMA 感知放置、任务粒度策略 | 更多 worker 可能饿死控制/拷贝线程，或只让内存带宽饱和。 |
| GPU 内核 | Native GEMV/MMVQ、grouped expert kernel、融合 GR/GDN、QSA selection/attention、架构专用 prefill 路径 | Tile/warp 布局、向量宽度、reduction tree、split-K、融合边界 | 寄存器、shared memory、occupancy、访存；改变归约要明确验证数值。 |
| Prompt 处理 | `--prefill N/auto[:N]`、`--short-read`、`--no-prefill-borrow`、`STRATA_PREFILL_RING`、`STRATA_PREFILL_CPU_SHARE` | Chunk 调度、transfer lookahead、ring 容量、按阶段分配工作区 | TTFT、传输摊销与并发 decode 延迟；受后端 chunk 上限约束。 |
| KV/state | `--kv fp16/int8/q4_0/k8v4`、`--kv-resident`、`--kv-grow`；QSA pooled selection 与 recurrent state | Page 替换/预取策略、新量化布局 | KV 占用对专家容量和传输延迟；降低精度改变数值契约。 |
| 推测解码 | `--spec`、`--mtp`、`--mtp-window`、`--spec-min-p`、`--mtp-max-t`、`--suffix-draft`、`--lookup-chain` | Draft source 选择、自适应深度、成本/接受率估计 | 优化接受 token 数除以完整 round 时间，不能只看接受率；计算额外权重和状态。 |
| Sampling | Greedy、temperature/top-k/top-p/seed；coupled/probabilistic draft 机制 | 其它精确 rejection 算法，或单独批准的采样语义改动 | 同 seed 文本相同与目标分布正确是不同契约。 |
| 对话复用 | `--prompt-cache`、checkpoint interval/root/tail、conversation RAM budget/slot、session file | 复用感知 eviction、checkpoint 位置策略 | 节约 prefill 与主机 RAM/copy 成本；recurrent/indexer/PLE 必须对应复用 token prefix。 |
| PLE/I/O | `--ple-io`、`--ple-row-cache`、`--ple-inflight`、prefetch 控制 | 请求合并、cache policy、存储布局 | 随机读延迟与队列深度；row 必须对应正确 n-gram history。 |
| 多 GPU | `--layer-split`、`--split-device`、peer tier、remote expert cache、`--trim-stage-weights`、pipeline window | 拓扑感知 stage 切分和专家放置 | Link 带宽与 stage balance；已有机制不等于通用 tensor parallel 或多机运行时。 |
| 服务与 batching | `--batch`/slot、`--batch-mtp`、`--batch-groups`、prefill/decode 时间分配、Python 请求队列 | 准入/SLO policy、更广泛 continuous-batching 策略 | 吞吐对单请求延迟、公平性和每 slot 状态内存；不能把已有 batch 说成缺失能力。 |
| 弹性资源 | `--vram-elastic`、segment size；`--kv-grow` | Cache/state 联合预算控制器 | 稳定虚拟地址、合法物理映射和足够 headroom；这两种模式并非处处可组合。 |

每个字段的合法范围应从所选版本解析；上表的名称是候选空间，不是一条可任意组合的启动命令。主要声明位于 `src/program/generate.cpp:337–680`，实际是否启用由 parser 和 guard 决定。[E17]

## 4. 关键依赖与约束

- **几何约束：** hidden/head 维度、选中专家数和 residual/state 结构来自 checkpoint 语义及编译内核。改变它们属于模型与引擎联合设计，要建立新的正确性基线。[E1]
- **内存预算：** 每个设备满足 `dense + state/KV + MTP + graph/scratch + prefill workspace + resident experts + reserve <= usable memory`，临时重叠和借用必须按真实生命周期计算，不能重复统计。Host 预算包含完整专家或 complement、pinned KV、停放对话、I/O cache。[E6–E8, E17]
- **Streaming 与 growth：** 当前 Flash-Next 实现的 `--kv-grow` 要求单 GPU、KV 不 streaming、profile-filled cache、所有专家在 RAM、VMM 可用，且没有 batch、VRAM elasticity、peer 或 remote cache。不支持的组合可能只告警并禁用；请求 flag 不等于实际激活。[E18]
- **Streaming 下限：** 当前 resident KV 至少 20,480 cell，以覆盖一个 verify window 可能选择的 cell 和工作需求。不能搜索任意小驻留池并假设行为等价。[E20]
- **推测长度上限：** 编译常量 `kVerifyMaxT = 8` 包含输入 row；`--spec 4` 表示最多三个草稿。增加上限是实现变更，不是无界整数扫描。[E13, E21]
- **Batch MTP：** 要求 serving、至少两个 slot、MTP、至少为二的 speculative window；不能与大于一的 pipelined batch group 同用，layer split 加 helper cache 等组合也有 guard。普通 batch window 有 row 上限及每 slot 状态成本。[E16]
- **RoPE：** scaling 属于进程级状态契约，因为缓存 key 已经过 RoPE。在同一 cache 中按请求混用不同 scaling 却不重建状态是错误的。[E17]
- **Copy/graph 契约：** Cache 借用、eviction、KV 增长和 elasticity 不能使捕获指针失效；swaps 不得暴露未完成的 copy。交接需要真实的生产者/消费者顺序，仅结构体布局一致不够。[E6, E11, E15]
- **后端差异：** CUDA、HIP wave32、gfx906 compatibility、SYCL、Metal 并不意味着功能与默认值相同。逐候选确认内核及 host 路径支持。[E3, E4]

## 5. 数值正确性：不能统称 lossless

区分三种目标：(a) 固定确定性路径下 logits/state 逐位一致或 token 一致；(b) 目标采样分布等价，但同 seed 的样本可能不同；(c) 明确预算的质量变化。

Verify 文档为其参考路径描述了逐 token 精确算术，但这不能覆盖所有已启用优化。特别是 `STRATA_ROUTE_TAIL_SKIP`：如果某 nonresident expert 在整个 window 中的最佳排名仍属于低权重尾部，则其贡献置零，且其它专家不重新归一化。CUDA 和 gfx12 的 serving 默认条件可能启用它；几乎所有专家驻留、NVFP4 默认配置、batch slot 默认配置等场景会抑制启用，dispatch 还排除 peer/helper 场景。**它会改变 logits。** 要声称精确性，必须指定明确参考模式。[E10, E22]

KV quantization、resident-biased routing、speed-projection vector、修改精度/归约路径，以及部分 CPU/GPU prefill-sharing 选择，也需要各自的误差或 parity 评估。只降低 draft 精度，在 verifier/commit 保持契约时可以维持目标正确性，但接受率和耗时会变。Probabilistic speculation 对经过 penalties/filters 的目标分布做接受概率与 residual sampling，应验证这个分布，不能只看少量输出字符串。[E12, E23]

Cache 或调度变化也可能因 CPU/GPU 内核算术不同暴露数值差异。不能因为计算的是同一数学 expert，就推断逐位相等。报告中要区分上游注释、上游测量、独立测试与尚未验证的提案。

## 6. 让 AI 生成与搜索的闭环

候选表示为 `C = (placement, execution split, kernels, prefill, KV, speculation, scheduling, reuse, I/O, approximation policy)`，以固定的 `H = hardware`、`M = model`、`W = workload` 为条件。

1. 建立正确性基线和 workload suite：短聊天、长 prefill、长 decode、工具返回续聊、代码/lookup-rich 文本、不同 context length 与并发到达。Profile 训练 prompt 和评价 prompt 分开。
2. 性能测试前，先根据内存预算、后端支持和依赖 guard 做可行性筛选。
3. 先搜索已有配置，测明限制资源。每次修改一个机制或有依据的交互组合，保存可复现的 incumbent。
4. 确认瓶颈后，再让 AI 生成相关算法/内核代码，提供窄而明确的契约及配对 reference。Kernel microbenchmark 只是筛选，最终仍做端到端验证。
5. 保留 TTFT、p50/p95 inter-token latency、生成 tokens/s、并发吞吐、峰值 RAM/VRAM、启动成本和质量的 Pareto frontier。如关注能耗，需要实测，不能用标称 TDP 替代。

可用近似模型辅助推理：`T_window ≈ T_fixed + Σ_layer max(T_CPU_misses, T_GPU_hits+transfer, T_other_device) + T_handoff + T_draft + T_commit`。它是瓶颈模型，不是严格可加的 profiler 事实；真实 overlap 和共享 link 要实测。推测解码吞吐是 `E[committed tokens] / E[total round time]`，源码 lookup policy 已体现此原则。[E14]

每条结果记录 commit、后端/toolchain、模型 shard hash/quant、GPU/CPU/RAM/拓扑、实际生效配置、workload/seed、冷热状态、专家/字节/接受率计数、重复次数和配对参考。改变质量的候选需要约定质量上限，并做 teacher-forced/logit 或任务评估；吞吐数字不能单独证明成功。

Strata 已有 `tools/calibrate.py`：搜索 PCIe share、speculative confidence、CPU worker 数和 adaptive tier 组合，并采用重复/交错比较及最小收益规则。先复用这个有界校准能力，再考虑新增 optimizer。它测量 decode，并不是完整的端到端代码生成搜索框架。[E24]

建议顺序：先解决内存可行性和明确数值基线；再搜索专家放置及 CPU–PCIe 平衡；接着联合搜索 prefill chunk/工作区与推测 window；再优化实测 kernel hotspot；最后按目标 workload 是否需要，处理多 GPU/serving policy。模型语义改动放入单独预算的近似路径。该顺序是根据所见架构提出的建议，不代表所有硬件瓶颈都相同。

本次检查未证实的扩展包括：通过通用 compiler IR 执行任意模型、通用 tensor parallel、多机 collective、全局自动搜索框架、通用 SLA scheduler。反之，多 GPU 放置、prompt lookup、batch slot、batch MTP、KV streaming 和 elasticity 已经有实现，不能把它们全部当作该仓库的新功能提案。

## 7. 证据索引

以下链接均使用所检查的 commit。定位范围尽量贴近相关契约，真正修改时还应跟进实现。

- **E1** [编译几何与 family/state 契约，`geometry.hpp:20–76`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/geometry.hpp#L20-L76)。
- **E2** [Family dispatch，`generate.cpp:1867–1879`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L1867-L1879)，[Qwen3.6 路径契约](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/qwen35/engine.hpp#L1-L10)。
- **E3** [版本/SYCL guard，`CMakeLists.txt:10–23`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/CMakeLists.txt#L10-L23)，[HIP 构建选择，59–94 行](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/CMakeLists.txt#L59-L94)。
- **E4** [Metal 范围/状态，`docs/MAC.md:1–38`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/docs/MAC.md#L1-L38)。
- **E5** [子进程边界，`serve/server.py:816–824`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/serve/server.py#L816-L824)。
- **E6** [Expert storage/profile 与稳定地址弹性，`expert_cache.hpp:37–134`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/expert_cache.hpp#L37-L134)。
- **E7** [Prefill 契约，`prefill.hpp:1–10`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/prefill/prefill.hpp#L1-L10)，[prefill 借用，`generate.cpp:534–550`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L534-L550)。
- **E8** [短 prefill 分流和 ring 容量，`prefill.cpp:164–206`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/prefill/prefill.cpp#L164-L206)，[ring，292–313 行](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/prefill/prefill.cpp#L292-L313)。
- **E9** [Expert 去重与 CPU/GPU plan，`expert_source.cpp:3715–3745`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/core/expert_source.cpp#L3715-L3745)。
- **E10** [Tail skip 与 pinned PCIe 路由，`expert_source.cpp:3747–3818`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/core/expert_source.cpp#L3747-L3818)。
- **E11** [Mapped pinned doorbell 与 driver polling，`layer.hpp:410–440`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/layer.hpp#L410-L440)。
- **E12** [MTP 对齐及 draft-only 算术，`mtp.hpp:1–19`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/mtp.hpp#L1-L19)。
- **E13** [Verify/accepted-prefix 状态契约，`verify.hpp:1–21`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/verify.hpp#L1-L21)。
- **E14** [接受率/成本策略，`draft_policy.hpp:1–44`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/spec/draft_policy.hpp#L1-L44)。
- **E15** [Adaptive swap 选择，`generate.cpp:8833–8865`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L8833-L8865)，[copy 完成 gate，`verify.hpp:42–59`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/verify.hpp#L42-L59)。
- **E16** [Batch/MTP guard，`generate.cpp:4491–4526`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L4491-L4526)，[batch 行为与评价边界](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/docs/BATCHING.md#L1-L33)。
- **E17** [选项及理由，`generate.cpp:337–680`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L337-L680)。
- **E18** [KV growth 激活条件，`generate.cpp:4391–4408`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L4391-L4408)。
- **E19** [有界 PLE reader，`ple_reader.hpp:1–12`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/ngram/ple_reader.hpp#L1-L12)，[reader 配置，46–63 行](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/ngram/ple_reader.hpp#L46-L63)。
- **E20** [KV layout，`layer.hpp:209–241`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/layer.hpp#L209-L241)，[驻留下限，`layer.cpp:666`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/core/layer.cpp#L666)。
- **E21** [Window 上限，`verify_kernels.hpp:21`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/kernels/verify_kernels.hpp#L21)，[CPU row splitting，`pool.hpp:175–185`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/kernels/cpu/pool.hpp#L175-L185)。
- **E22** [改变输出的条件默认值，`generate.cpp:8618–8664`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L8618-L8664)。
- **E23** [Probabilistic speculative 分布契约，`spec_prob.hpp:1–31`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/spec_prob.hpp#L1-L31)。
- **E24** [已有校准范围与候选值，`tools/calibrate.py:1–44`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/tools/calibrate.py#L1-L44)。

## 8. 验证状态

已阅读相关源码、声明、guard 与仓库规范，交叉检查证据位置，以及“已有”和“提案”的区分。本次没有下载模型、安装、构建、GPU 执行或运行时 benchmark。硬件相关速度、同 seed 等价性和质量仍需目标机器验证。仓库 `AGENTS.md` 要求性能声明有测量依据、新能力 opt-in、构建涉及的后端；后续实施同时遵循用户要求的 plan → code → test → review。
