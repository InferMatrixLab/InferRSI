# 有限调优与验证

对比配置或接受调度/cache/后端改动前读取。命令已对照本源码快照检查；运行时命令需要预先配置好的兼容环境。本候选未经过 GPU 测试。

## 复现契约

记录提交、clean/dirty 状态及补丁；已安装包版本；模型/tokenizer/draft 版本；加速器数量/型号/内存、驱动/toolkit 和互连；dtype/量化/KV 布局；生效参数与环境 override；请求数据集 hash、长度、共享前缀及多模态分布；到达/并发；seed、输出上限/EOS 与采样；预热、缓存状态和重复次数。

明确正确性阈值、延迟 SLO、失败容许范围和有限实验预算。用已完成请求/token 计算有效吞吐，报告错误/超时而非静默删掉。联合比较 p50/p95/p99 TTFT、ITL/TPOT、端到端延迟，以及排队、吞吐、内存、缓存/投机数据。客户端饱和和分词可能限制观测到的速率。

## 命令

源码命令从仓库根目录执行。运行时示例将 `/path/to/model` 替换为已获准的本地模型/tokenizer，并选择独立结果路径。两种语言树内的以下命令完全一致。不为运行 help 而安装整个重量级依赖栈。

源码身份及已审查的仓库 CPU 检查：

```bash
git rev-parse HEAD
git status --short
python -B scripts/lint/check_registered_tests.py
```

该检查扫描测试注册/入口，不导入 SGLang 运行时，也不执行模型测试。[E35](source-map.md#e35)

在兼容的已安装环境中查看帮助，并启动单设备基线：

```bash
sglang version
sglang serve --help
sglang serve --model-path /path/to/model --host 127.0.0.1 --port 30000 --tp-size 1
```

`sglang serve` 是当前推荐入口；`python -m sglang.launch_server` 保留但输出弃用警告。字段 CLI 名称从声明推导。增加参数前确认模型/后端兼容性。[E28](source-map.md#e28)、[E29](source-map.md#e29)、[E34](source-map.md#e34)

面向该服务的有限合成负载试验：

```bash
python -m sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:30000 --model /path/to/model --dataset-name random --random-input-len 256 --random-output-len 64 --num-prompts 64 --request-rate 4 --max-concurrency 8 --seed 42 --warmup-requests 4 --output-file sglang-baseline.jsonl
```

这只是示例负载，不是生产推荐负载或已完成基准。源码分别限制并发与到达速率；并发上限可能使实际到达速率更低。对比冷缓存与前缀复用实验时必须记录预热/cache flush 行为。合成 smoke 后再使用代表性请求 trace。旧 `sglang.bench_serving` 是弃用 wrapper。[E24](source-map.md#e24)、[E25](source-map.md#e25)、[E30](source-map.md#e30)

内核/模型前向计时及源码提供的正确性入口：

```bash
python -m sglang.benchmark.one_batch --model-path /path/to/model --batch-size 1 8 --input-len 256 --output-len 64
python -m sglang.benchmark.one_batch --model-path /path/to/model --correctness-test
```

这些检查的边界比在线服务更窄。解析器定义了完整 `--correctness-test`，不依赖旧示例中的 argparse 缩写。应对照匹配的数值/模型参考，不能将打印输出当成全面通过。[E26](source-map.md#e26)

安装开发依赖后，可以在 GPU 测试前运行定向 CPU 目录测试：

```bash
python test/registered/unit/kernels/test_kernels_namespace.py
```

“CPU 测试”不等于“无需 Python 运行时依赖”：导入包仍可能需要 PyTorch 等依赖。本次提取环境未运行该测试。[E36](source-map.md#e36)

## 搜索一个小的有效空间

| 假设 | 首个受控维度 | 必须同时观测 |
|---|---|---|
| 长 prefill 干扰 decode | chunk size / prefill token 预算 | decode 尾延迟、prefill TTFT、完成吞吐、workspace 峰值 |
| 准入超过有效 KV 容量 | running-request 上限 / 静态比例 | 排队与 OOM/回撤率、公平性、峰值内存 |
| 前缀复用有收益 | 缓存策略及明确 cold/warm 流量 | 节省 prefill 与传输/等待成本、命中正确性 |
| 投机收益覆盖开销 | 兼容算法及 draft 预算 | 接受 token 与 draft+verify 工作、内存、端到端 SLO |
| 通信限制扩展 | 一个有效拓扑/后端维度 | 各 rank 利用率、集合通信时间、输出等价性、总硬件基线 |

从基线和少量有依据的候选开始，不做所有参数的笛卡尔积。启动前排除源码禁止的组合。测量单个类别效果后，再测试少量交互。保留原始产物和失败，重复有希望的成对配置，只对可行候选排序，并在预设预算内停止。新算法属于研究扩展，需要独立消融与正确性论证。

## 正确性门槛及限制

| 门槛 | 检查 | 本候选状态 |
|---|---|---|
| 源码/静态 | AST 语法、参数声明、测试注册、固定证据行号、图链接及双语命令一致性 | 构建时执行，结果见外部报告 |
| CPU 语义 | 正确环境中的配置/注册/cache 单测 | 仅运行独立注册检查和 linter 恢复 fixture；运行时单测仍未验证 |
| 模型与缓存 | 数值/logit 参考；miss/hit；部分前缀；驱逐/取消；chunk 边界；SWA/Mamba 状态 | 需要目标运行时/模型/硬件 |
| 投机 | 基线采样/质量等价性、接受/拒绝状态及 target 验证 | 需要兼容 target/draft 与运行时 |
| 分布式/PD | TP/DP/EP 输出一致；空闲/不均匀 rank；传输/超时/取消；两端配置 | 需要真实通信组拓扑及 transport |
| 性能 | 同硬件/负载/SLO 下的重复成对试验和 profiler 证据 | 未测量；不声明加速或最佳配置 |

prefill 与 decode 的 logprob/KL 检查衡量状态/函数一致性，任务准确率衡量另一种性质。原生 helper 区分无缓存、prefill-cache-hit、decode-cache-hit 路径；数值上的 batch 依赖可能掩盖恢复错误。使用原生 KL 指南和模型特定基线设定有意义容差。[E27](source-map.md#e27)

## 失败恢复

参数失败时检查当前解析器和来源记录，不猜替代参数。启动失败时保留第一个 worker 错误及生效配置，适合时缩小到已知模型/后端和单设备。正确性失败时冻结性能修改，缩小输入/生命周期。吞吐波动大时，先检查客户端负载生成、缓存状态、预热和外部干扰，再扩大搜索。保留最后通过配置，并明确报告所有未执行门槛。

## 评审补充：注意力 DP 与缓存实验

本提交要求 attention DP 为正；拒绝副本 `dp_size > 1` 与 `attn_dp_size > 1` 同时启用。TP 必须能被 attention-DP 整除；存在 attention CP 时，还需能被 `attn_dp_size * attn_cp_size` 整除。因此 TP=4、attention-DP=2、副本-DP=1、attention-CP=1 通过这些算术检查；TP=3/attention-DP=2 或副本-DP=2/attention-DP=2 不通过。这些是符号化校验示例，不是模型/硬件认证配置。钩子还会把有效 chunked-prefill 预算除以 attention-DP 数，必须记录解析后的值。[校验器](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/parallel_hook.py#L279-L321)、[CP 约束](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/parallel_hook.py#L152-L158)。

重复前缀/恢复验证可采用原生[unified-memory HiCache 测试](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/e2e/hicache/test_hicache_unified_memory.py)作为具体负载和 schema 参考：向 `/generate` 提交 `text`、`sampling_params.temperature=0`、`sampling_params.max_new_tokens` 并请求输出 logprob。顺序为预热目标前缀、用不同 filler 前缀使其从设备缓存驱逐、重新加载时要求出现 host hit，再与常驻缓存参考比较文本/logprob。两端使用相同 unified-memory 模式，避免改变 attention 归约顺序。沿用该测试真实模型用例和启动设置；它是 two-GPU-large CUDA CI 负载，会启动服务/加载权重，不是本地 CPU 检查。

改成性能实验时，保存精确 token ID、模型/tokenizer、请求顺序；把真正重置后的 cold 阶段与热 L1 复用分开，再给 L1 足够压力以触发 L2 恢复。总体 cache hit 高不够，必须确认 host hit 及传输/等待成本。只有配置了后端且观测到 storage hit 才测试 L3。固定输出上限、EOS、并发和质量。原生测试执行后提供正确性证据，不是现成通用吞吐 benchmark；服务计时和存储特定埋点可能需要补充。

其他精确候选：[分配/驱逐](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/unit/mem_cache/test_unified_radix_allocation_eviction.py)和[HiCache dispatch](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py)注册为 CPU 测试，使用 mock allocator/cache 组件，仍依赖正常 SGLang/PyTorch 环境。[Full-attention KL](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/radix_cache/unified_radix_tree/test_unified_radix_cache_kl_full.py)会以 TP2 启动 Qwen3-32B，注册为两张大显存 CUDA/AMD GPU 测试；其阈值仅适用于对应模型/测试。其他布局选择 SWA/Mamba/MLA 套件。本次补充未执行这些测试，它们不能继承 registration linter 的通过结论。
