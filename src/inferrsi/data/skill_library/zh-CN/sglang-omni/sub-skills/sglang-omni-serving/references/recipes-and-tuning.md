# 模型方案、配置与实验契约

## 最终配置

拓扑由模型 Python 配置类声明；用户 YAML/CLI 只能覆盖已有阶段，不能增删阶段。YAML `stages` 是以阶段名为键的映射。阶段顶层字段用于进程/放置规划；`engine.*` 只在 engine 阶段传给 SGLang 参数；`factory.*` 传给阶段构造器。未知 engine/factory 字段允许透传，但仍需真实消费方；解析器接受不等于功能受支持。

CLI 优先于 YAML；显式阶段路径优先于 shared selector/广播值。同优先级对同一叶子的重复写入会冲突，不会静默采用最后值。`--mem-fraction-static` 向 engine 阶段广播。用 `config resolve --show config|diff|provenance` 与 `config explain PATH` 观察最终值。`kv_cache_bytes` 不能与 `mem_fraction_static` 或 `max_total_tokens` 同时存在；需要时明确清除继承的冲突值。

以下命令已按源码核对，应在固定版本源码根目录、依赖及权重可用时运行。serve 命令会启动进程/GPU 负载，只在任务已授权部署时执行。示例中的 8 是实验点，不是推荐最优值。

```bash
sgl-omni config resolve --config examples/configs/qwen3_tts_0_6b.yaml --show diff --tts_engine.engine.max_running_requests 8
sgl-omni config explain stages.tts_engine.engine.max_running_requests --config examples/configs/qwen3_tts_0_6b.yaml --tts_engine.engine.max_running_requests 8
sgl-omni serve --model-path Qwen/Qwen3-TTS-12Hz-0.6B-Base --config examples/configs/qwen3_tts_0_6b.yaml --tts_engine.engine.max_running_requests 8 --host 127.0.0.1 --port 8000
```


## 选择模型专有契约

| 模型 / 路径 | 方案选择与依赖约束 |
|---|---|
| Qwen3-Omni | 通过 chat 接收文本/图像/音频/视频，输出文本或文本+音频。音频需要语音模式；`--text-only` 即使收到音频请求也可能不返回音频。同进程放置方案拒绝 thinker TP=2，TP 应使用支持的拆分配置。一个请求中的所有视频须使用相同采样帧率。 |
| Qwen3-TTS | Base 0.6B/1.7B 使用 preprocessing → engine → vocoder 和参考条件语音。`12Hz` 是 codec 帧率，波形输出为 24 kHz。CustomVoice/VoiceDesign 的请求/参考条件语义不同。保留主栈 Transformers 5.12.1/SGLang 0.5.21；按方案以 `--no-deps` 安装 `qwen-tts==0.1.1`，并配置系统/Python sox。不要降级到其自身依赖声明中的 Transformers，仓库已提供兼容 shim。 |
| Qwen3-ASR / Fun-ASR | 使用转录/realtime 方案与所选平台 runner。Apple MLX/Torch-MPS 是模型专有支持，不代表通用 GPU 等价。 |
| Fish S2-Pro / Drama 3、Higgs、MOSS、Voxtral、ZONOS2 | TTS 方案的参考编码、codebook、vocoder 缓冲、许可和可选依赖不同。共享配置前先读对应 cookbook 与 `models/<family>/config.py`。Drama 3 的 `fishaudio` extra 并非所有 TTS 模型必需。 |
| MiniMax Music 3 / LLaDA2-Uni | MiniMax Music 3 使用模型专有 AR + flow-matching DIT 音乐生成。LLaDA2-Uni 的 cookbook 虽描述模型更广泛的图像生成架构，实际覆盖实验性的文本输出路径。不要将架构描述升级为已支持的接口声明，也不要把本仓库视为通用 SGLang diffusion 服务。 |

按方案选择 speech、transcription、chat 或 realtime 接口，它们不共享一个通用 JSON schema。保留参考文本/音频、采样率和编码，存在能力查询时检查服务能力。SSE 启动后，HTTP 200 仍可包含错误事件；队列满可能表现为流内 server error code 503。没有音频或仅有部分输出应计作失败，而不是延迟改善。

## 在约束下测量目标

记录源码/权重、最终配置、包版本、硬件/驱动、拓扑、启动/图捕获与预热状态、数据集版本和样本 ID、输入输出长度、随机种子/采样、参考音色及到达模式。预热不计入测量。比较逐请求日志和产物，不只比较单个聚合指标。

| 负载 | 性能观测 | 质量 / 正确性下限 |
|---|---|---|
| TTS 流式 | 首个可播放音频、完成 p50/p95/p99、分块时序/播放断流、RTF、完成音频秒数/秒、失败 | WER、适用时的音色相似度/听感、音频时长、连续性、采样率、自然结束与长度截断 |
| 视频+语音提问 → 文本/音频 | 媒体解码/预处理、首文本与首音频、终端延迟、吞吐、prompt token | 任务准确率、转录/WER、固定视频采样、输出完整性 |
| ASR/realtime | 首个 partial、最终延迟、partial 间隔、端点判定延迟 | 说明规范化方式的 WER/CER、最终文本稳定性、取消/会话隔离 |

所提分块间隔和播放标准可能需要新增观测，不要声称每个基准都输出全部指标。原生 `benchmark_omni_streaming_ttft` 虽将指标命名为 TTFT，实际测量的是首个**音频** delta，不是首文本 token。以下客户端向已运行的 Qwen3-Omni 语音服务提交请求：

```bash
python -m benchmarks.eval.benchmark_omni_streaming_ttft --base-url http://localhost:8001 --label baseline --repeats 5
```


SeedTTS 指南使用 `benchmarks.eval.benchmark_tts_seedtts`，可能启动 TTS 服务、下载/读取数据集、保存音频，再启动 ASR 评分；它不是无副作用的解析检查。启动前读当前参数与 runbook。其标准指南报告 speed/RTF/WER，不包括 SIM/UTMOS；MiniCPM 离线指南有独立评分产物。始终报告评分覆盖率/跳过项和长度截断。缩短生成长度可改善表面延迟，却降低质量。

保留基线配置和结果。依据 trace 对有界因素进行扫描（准入、进程放置、阶段显存、受支持的图/精度、模型分块），复测同一质量门槛，并保存未通过的试验。收益仅适用于实际负载和硬件；本技能包不能支持任何加速声明。

固定版本证据：

- [sglang_omni/cli/config.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/cli/config.py)
- [sglang_omni/cli/serve.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/cli/serve.py)
- [sglang_omni/config/schema.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/config/schema.py)
- [docs/developer_reference/config.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/config.md)
- [examples/configs/qwen3_tts_0_6b.yaml](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/examples/configs/qwen3_tts_0_6b.yaml)
- [docs/cookbook/qwen3_tts.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/cookbook/qwen3_tts.md)
- [docs/cookbook/qwen3_omni.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/cookbook/qwen3_omni.md)
- [docs/cookbook/qwen3_asr.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/cookbook/qwen3_asr.md)
- [docs/cookbook/fishaudio_drama3.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/cookbook/fishaudio_drama3.md)
- [docs/cookbook/minimax_music3.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/cookbook/minimax_music3.md)
- [docs/cookbook/llada2_uni.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/cookbook/llada2_uni.md)
- [benchmarks/eval/benchmark_omni_streaming_ttft.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/benchmarks/eval/benchmark_omni_streaming_ttft.py)
- [benchmarks/eval/benchmark_tts_seedtts.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/benchmarks/eval/benchmark_tts_seedtts.py)
- [docs/developer_reference/tts_bench.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/tts_bench.md)
- [docs/developer_reference/omni_offline_bench.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/omni_offline_bench.md)
