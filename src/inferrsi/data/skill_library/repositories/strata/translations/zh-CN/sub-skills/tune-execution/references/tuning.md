# 对照调优流程

## 1. 固定实验条件

固定源码与构建版本、模型和 pack 校验值、tokenizer 和模板、硬件拓扑、驱动与工具链、功耗策略、负载集、采样规则及质量门槛。分别测冷启动、冷 prompt、复用 prompt 和稳定 decode。专家缓存预热、OS 文件缓存、MTP 接受率及语言组成均属于实验状态。固定请求和实际输出长度，或报告差异。

记录显存、内存预算，包含驱动分配、图捕获、临时缓冲区、会话状态及 pinned 页。SSD 映射能降低提交内存，但不会消除工作集或缺页代价。长上下文与并发负载必须各自检查内存。

## 2. 根据瓶颈选择分支

| 观测 | 候选改动 | 应测内容 |
|---|---|---|
| CPU 专家计算占关键路径 | `--pool-workers`、`--pool-tasks`、`--pool-affinity`，再调 `--pcie-frac` | CPU 任务时间、H2D 字节与耗时、窗口延迟；更多线程可能争抢带宽 |
| 专家频繁 miss | 缓存容量与预留、放置/profile、适应性换入参数 | 实际驻留槽数、miss、CPU 与传输 miss 分工、换入开销 |
| 长 prompt 阻塞 | `--prefill`、受支持的量化矩阵路径、分阶段传输 | TTFT、prefill 吞吐、临时显存与主机内存峰值、decode 公平性 |
| 长上下文挤占专家空间 | 对应路径的 `--kv-resident`、`--kv`、`--kv-grow` | attention/传输时间、专家容量、长上下文质量和峰值内存 |
| 草稿开销大或常被拒绝 | MTP 开关、`--spec`、`--spec-min-p`、草稿词表 | 每 verify 窗口实际输出 token 数 / 完整 draft+verify 时间 |
| 多用户排队 | `parallel` / `--batch`、分块准入和分组流水线 | 总吞吐、p95 请求延迟及单请求速度 |
| 有额外 GPU | 按层切分与 helper/peer 专家放置 | 链路流量、阶段不均衡、重复占用及实际重叠 |

不能只看缓存命中率：PCIe 分担比例改变后，计入 CPU 统计的 miss 也会改变。需核查统计口径和端到端延迟。

### 内置硬件校准

模型已准备完成且兼容时，在 Strata checkout 根目录运行：

```text
python -X utf8 tools/calibrate.py strata-iq2_xs.json
```

此 CLI 只接受一个位置参数，即 config 路径。它启动配置中的原生引擎、测量候选，打印进度和最终 JSON，但不会把选出的设置写回该配置。它仍会执行真实生成，测试 worker/adaptation 候选时重启引擎，并使用配置中的日志。前置条件包括可用 GPU/runtime 和引擎、现有模型/pack、正确的 `exe`/`args`/`cwd`/`tokenizer` 路径、Python 中供 server 导入的 `jinja2` 和供 `strata_tokenizer` 使用的 `regex`，以及 tokenizer 的 `vocab.json`、`merges.txt`、`token_type.json`。应留出独立测试时段并保证内存充足；它不是无 GPU 或短时 smoke 命令。

当前程序扫描 `--pcie-frac`（0、0.2、0.35、0.55、0.75、0.9、1，加探测到的默认值）、`--spec-min-p`（0.3、0.5、0.7，加默认值）、CPU worker 数，以及对比引擎默认值的 adaptive-tier `(every, swaps, decay)` 候选 `(1,80,0.97)` 和 `(1,160,0.97)`。PCIe/draft 扫描做三轮交替顺序测量及交错确认；worker/tier 候选需要重启。`MIN_GAIN=0.03` 仅在候选 decode 速率中位数比对应默认值高出超过 3% 时保留。它是抑制速度测量噪声的启发式筛选，不是统计置信度、输出等价测试或质量容差。目标仅为 decode；prompt TTFT、并发、长上下文质量和内存仍需单独验证。三个 prompt 均为英文，其中一个是 Python 任务，不能代表中文或其他目标领域。

需要有意保存某个已安装模型的校准结果时，setup 支持：

```text
python -X utf8 setup.py --calibrate --family qwen --model IQ2_XS --no-start
```

应选择确实已安装的 family/model。Setup 写入 config 的 `args`，并按硬件/模型/context/vision 标识保存设置；未改变的调优项会恢复产品默认值，因此应用前保留原配置。`--no-start` 只阻止最后启动服务器，这个 setup 分支仍可能先更新已安装引擎再校准。要求固定引擎版本的实验应先使用 standalone 工具并审阅结果。`--calibrate` 与 `--setup` 或 `--check` 同用、或尚未安装任何模型时不会生效。证据：`tools/calibrate.py:1-53,102-162,202-295,325-343`、`tools/strata_tokenizer.py:22`、`setup.py:4732-4773,5893-5918`。此工具依赖匹配版本的仓库，应在相应 checkout 使用，不在技能中捆绑第二份副本。

## 3. 做小规模条件化搜索

以下是建议的起始实验，不是上游默认值，也不保证所有组合合法。使用前检查所选模型族的参数解析和启动日志。

- 先固定权重、KV 格式、近似专家跳过及模型语义，每次只改变一个机制，与工作基线对比。
- 单独显卡、专家常驻 RAM 时，可用 0、0.25、0.5、0.75 等 `--pcie-frac` 粗粒度候选诊断负载平衡。PCIe 拓扑和 CPU 带宽决定结果，没有通用最优值；显式参数覆盖自动调节。
- 根据物理核和性能核数量选少量 CPU pool 大小。主线程可能参与计算，`--pool-workers N` 不一定等于总计算线程数。
- 在容量允许时比较 1024、2048、4096、`auto` 等 prefill chunk。`auto` 随平台变化：Windows HIP 可能设上限，部分 gfx12 路径会增大。不能把 decode 与 prefill 混为一个目标。
- 准备兼容 MTP 产物后，对比关闭 MTP 与 `--spec 2`、`--spec 4` 的验证窗口预算；这个值不简单等于草稿 token 数。同时记录 suffix/prompt-lookup 策略，它也会影响实际窗口。引擎参数是 `--mtp <path>`，不能省略路径。
- 只在对应后端和模型路径中探索 KV `fp16`、`int8`、`k8v4`、`q4_0`，分别通过质量门槛。切换 KV 格式属于不同数值实验。
- 核查内存后再增加第二个 slot。它可能减少排队，却降低单请求 decode 速度；并发对比必须固定请求负载。
- 理解单项作用后，再测有耦合的组合：KV 驻留 × 专家槽、MTP head × 缓存容量、CPU 线程 × PCIe 比例、batch groups × 草稿策略。

优先分阶段随机或贝叶斯搜索，避免平铺笛卡尔积。代码生成则将 AI 限制在一个机制或接口，先过编译与 parity，再运行昂贵端到端实验。这些搜索方法是建议方案，不是 Strata 已有功能。

## 4. 保留兼容性条件

- 原生引擎、安装器和服务配置参数不同。例如安装器 `--parallel N` 写入服务配置 `parallel`，引擎使用 `--batch N`；安装器 `--draft-vocab en` 选择产物，引擎 `--mtp-draft-vocab` 接受文件。
- 按层切分时，`--batch-groups G` 要求 G 整除 slot 数。分组流水线可能关闭 batch MTP 或异步适应性换入。读取 `INFO batch_groups`、`INFO batch_slots` 及说明日志；内存或行数限制可能降低请求的并发数。
- `--vram-elastic` 是有条件的 NVIDIA serving 功能，不能当作跨后端通用分配器。按层切分、helper/peer、resident 模式及活动 batch 都有额外限制。resize 返回成功也可能未达到预留要求，必须看返回的空闲内存。
- 异步换入不能覆盖尚被在途窗口使用的专家槽；保留 copy-ready、consumer-complete 事件、pinned buffer 生命周期及所有权映射。
- `--mmap-experts` 不意味着全部专家已在 RAM；`--resident-experts` 尝试把 GPU 未驻留部分留在 RAM，必须确认实际模式和余量。

## 5. 先验质量，再测性能

运行相关 parity 和状态检查，再交错重复 baseline/candidate（例如 ABBA），控制预热与缓存状态。保留未参与调参的 prompt 集，目标包含中文或代码时应覆盖这些负载。报告中位数、离散程度、样本量，并在并发场景报告 p95 延迟。微基准变快只能作为筛选信号。

较严格的诊断基线可显式设置 `STRATA_ROUTE_TAIL_SKIP=0`、`STRATA_PREFILL_CPU_SHARE=0`；说明这与上游默认不同。`STRATA_IQ_MT_MIN=1`、`--prompt-cache 0`、`--adapt-swaps 0`、`--pcie-frac 0` 等控制项可以减少跨次波动来源，但不能证明跨设备或不同算术路径逐位相同。

只有实际验证器已赋予 `quality_ok` 和 `valid` 标签，才能使用 [CSV 约定](../../../references/trial-format.md)与[汇总脚本](../../../scripts/summarize_trials.py)。实验清单还需保存模型、编译器和配置元信息；不能把失败或截断输出的运行变成吞吐冠军。

## 恢复办法

- OOM：检查实际 slot/chunk/KV/cache 分配，降低对应占用并先恢复基线，不能悄悄缩短输出或上下文。
- 接受率低：先检查语言词表覆盖和草稿成本，再决定是否增加推测深度。
- 重叠没有收益：检查同步等待与总线饱和；只有移出关键路径才有帮助。
- 质量退化：隔离近似机制及 CPU/GPU 算术差异，保存 logits 和反例，门槛通过前排除候选。
- 功能没有生效：核对启动解析及支持的参数，将结论降为“请求启用，但实际未启用”。

## 固定版本证据

- [引擎参数及执行条件](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp)：参数在约 1890–2230 行，tail skip 策略在约 8618 行。
- [Batch 分组解析](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/program/batch_groups.hpp)。
- [原生基准客户端](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/tools/strata_bench.py)：区分客户端 TTFT 与引擎计时、重复运行和比较选项。
- [硬件校准程序](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/tools/calibrate.py)：有限 decode 扫描、重启、确认与 3% 选择门槛。
- [显存弹性接口约定](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/docs/VRAM_ELASTIC.md)。
- [异步专家交换所有权](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/expert_source.hpp)。
