# 两张 L20X 上 Qwen3-Omni 的条件性能边界

目前可以建立带明确假设的计算、带宽边界，但不能据此宣布目标已经可达、实现达到最优，或给出整条服务链的可靠预测。下面区分硬件条件上界、模型工作量下界和实际请求的时间预算。本文只整合已有证据，没有启动 GPU 工作。

## 硬件：可计算条件值，尚缺 SKU 规格确认

两张卡的直接 NVML 查询均报告计算能力 9.0、6144-bit 显存接口、最高显存频率 3201 MHz、最高 SM 频率 1980 MHz。先前 CUDA runtime 查询报告 132 SM、60 MiB L2，已有 sm90 编译的 CUDA 测试成功。与之不一致的是此前 `nvidia-smi` 的 `compute_cap` 字段 8.9；不能写成“NVML 报告 8.9”，也不能推断冲突原因。显存容量的不同工具口径亦应保留，不用它们认定产品型号。

| 每卡指标 | 条件计算 | 结果与限制 |
| --- | --- | --- |
| 显存接口带宽 | 3201 MHz × 2 × 6144/8 | 4.916736 TB/s；假设频率为 DDR 基准时钟、接口全部有效，未扣协议/ECC 开销 |
| Dense BF16 Tensor 算力 | 132 SM × 1.98 GHz × 4096 FLOP/SM/周期 | 1070.53056 TFLOP/s；假设标准 Hopper dense BF16 数据通路及所报频率成立，不使用稀疏翻倍值 |

4096 的来源是官方 Ampere 每 SM 每周期 2048 个 FP16 FLOP，以及 Hopper 对前代相同 tensor 类型每 SM 同频吞吐翻倍、BF16 与 FP16 同速的说明。计算能力表示指令兼容性，不能单独证明启用单元吞吐或持续时钟。未找到可确认该设备的官方 L20X 规格，因此以上是**条件硬件包络**，不是已核实 SKU 的无条件理论峰值；不得直接代入 H100/H200 的宣传参数。[Ampere 白皮书](https://images.nvidia.com/aem-dam/en-zz/Solutions/data-center/nvidia-ampere-architecture-whitepaper.pdf)、[Hopper 架构](https://developer.nvidia.com/blog/nvidia-hopper-architecture-in-depth/)、[带宽计算方法](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html)。

本机已有微基准：大块 copy 的读写合计带宽约 4.265/4.267 TB/s，大方阵 BF16 GEMM 最好中位数对应约 788/780 TFLOP/s。它们是特定操作的实测包络，不是所有 kernel 可达到的速度，也不能证明上述硬件假设。

## 模型工作与目标预算

本 checkpoint 的语音是每秒 12.5 个 codec 帧、每帧 16 个码本；残差 predictor 顺序生成 15 步。24 kHz 输出对应稳态每 codec 帧约 1920 个 PCM sample frames。用户指标中的 frames/s 是 **PCM frames/s**，不是 codec 帧率，短输出应以实际音频长度为准。[固定模型配置](https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct/blob/26291f793822fb6be9555850f06dfe95f2d7e695/config.json)、[模型报告](https://arxiv.org/html/2509.17765v1)。

原始两卡放置中，Thinker 在第一张卡，Talker、predictor、codec 共用第二张卡。不能将第二张卡独占承担的语音工作除以两卡算力总和。

在等长请求、同步满批、稳态近似下：

| 并发 | 目标 mean RTF | 每次批量推进一个 codec 帧的预算 | 对应条件聚合 PCM 吞吐 |
| --- | ---: | ---: | ---: |
| 1 | <0.06 | <4.8 ms | >400,000 frames/s |
| 64 | <0.3 | <24 ms / 64 帧 | >5,120,000 frames/s |

这只是容量预算。异长请求、排队及尾部会破坏上述换算；原生 benchmark 的 mean RTF 是逐请求 latency/audio_duration 的平均，不能用聚合吞吐倒数替代。

Talker 已计线性计算约 0.571474 GFLOP/codec 帧。predictor 五层共约 7864 万个被使用的线性权重参数，每个位置约 0.1572864 GFLOP：

| Predictor 路径 | 每帧处理的位置数 | Predictor 线性工作 | 加上 Talker 后的已计工作 |
| --- | ---: | ---: | ---: |
| 全长 17，重复 15 步 | 255 | 40.108032 GFLOP | 40.679506 GFLOP |
| 每步较短前缀 2…16 | 135 | 21.233664 GFLOP | 21.805138 GFLOP |
| 增量 KV：首次 2，后续 14 | 16 | 2.516582 GFLOP | 3.088056 GFLOP |

1.889 倍、15.9375 倍仅是 predictor 线性工作量之比，不是端到端加速比；质量、数值及采样语义仍必须独立验证。[固定实现来源](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/model_executor/models/common/qwen3_code_predictor.py)。

## 条件理论吞吐上限与 RTF 下限

令 F 为每帧已计工作，Q 为每批流经显存的假设字节量，P/B 为上述每卡条件峰值。在指定算法、放置、流量模型下：

`t_batch >= max(C×F/P, Q/B)`；`RTF_steady >= 12.5×t_batch`；`PCM吞吐 <= C×1920/t_batch`。

这是被省略工作为零的乐观边界。采用当前全长重复路径，C1 假设每残差步重新流过全部 predictor 权重，加上 Talker 活跃线性权重，总计约 2.931 GB/帧；C64 示例采用全部 128 个专家均被触达的权重流量约 8.687 GB/批。C64 的该专家流量不是每批必然流量；此例最终由计算项限制。

| 条件稳态示例 | 每批时间下界 | RTF 下界 | PCM 吞吐上界 |
| --- | ---: | ---: | ---: |
| C1 | 约 0.596 ms | 约 0.00745 | 约 322 万 frames/s |
| C64 | 约 2.432 ms | 约 0.03040 | 约 5053 万 frames/s |

这些数字**不是完整 Qwen3-Omni 的可达上限或预测值**。特别是 C1 带宽项依赖重复读权重假设，缓存/工作重排可改变 Q，所以不能称为任何实现都必须满足的物理下限。按已计计算量，目标至少需要语音卡在 C1 提供约 8.475 TFLOP/s、C64 提供约 108.479 TFLOP/s；小矩阵、MoE、不规则访问与串行依赖能否实现这些有效速率仍需测量。用实测包络作敏感性分析也不能证明目标可行或不可行。

尚未完整枚举的正成本包括：codec 卷积和 transformer、attention/KV 访问、采样与归一化、激活读写、填充行、数据传输、CPU 调度、排队、Thinker 供给、首包串行链和结束排空。默认 codec 每 25 个新帧还可能重算 25 帧左上下文；其缓存化需验证因果边界和裁剪。TTFA p50/p95 不能从峰值 FLOP 推导。

## 从已观测请求拆分得到的实际难度

独立复核了首个 eligible formal pair 的逐请求恒等式：

`mean RTF = mean(TTFA / 音频时长) + mean((latency−TTFA) / 音频时长)`。

它不是平均 TTFA 除以平均音频时长。候选 MRv2+adapter 的结果如下，仅代表该 pair，不能替代三组质量/性能验收：

| 并发 | 已观测 mean RTF | 首音频贡献 | 首音频后贡献 | 若 TTFA 与时长不变，剩余阶段达到目标所需加速 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.109138 | 0.025442 | 0.083697 | >2.4219 倍 |
| 64 | 0.586494 | 0.095586 | 0.490908 | >2.4015 倍 |

最后一列为“剩余贡献 / (目标−首音频贡献)”的反事实预算，不是硬件上界，也没有声称首包无法优化。它说明在首包不变时，仅小幅改进局部 kernel 不足以达标。

现有 MoE 微调的 **3–5% 仅为选定合成 M1/M64 kernel 的诊断收益**，尚无服务级收益，也不知道其占请求关键路径的比例。不能直接将它乘到完整 RTF 上，或声称已解决瓶颈。

后续应优先验证 predictor 重复工作的消除、codec 状态缓存与实际关键路径；通过组件数值/采样检查后再执行固定质量和性能验收。保留失败样本，不以理论工作比、单 kernel 收益或有条件下界替代整模型实测。

证据文件：`ceiling-analysis-v6.md`、`hardware-conditional-roof-v6.md`、`empirical-roof-v6.json`、`rtf-first-audio-decomposition-v6.json`、`iteration-v6-search-plan.json`。本说明为私有 scratch 分析，无代码提交、无新增 GPU 操作。
