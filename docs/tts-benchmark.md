# 单 NPU Qwen3-TTS 优化任务

这是一个可直接修改和运行的真实文本转语音任务。输入中英文文本、音色和生成参数，
使用 **Qwen3-TTS 1.7B CustomVoice 真实权重**，输出 24 kHz 单声道 PCM 音频。
任务自身包含推理调度和服务代码，运行时依赖 PyTorch、torch_npu/CANN、官方
`qwen-tts==0.1.1` 与 `transformers==4.57.3`，无需安装或检出 vLLM、vLLM-Omni。

本版为 `qwen3-tts-npu-v2`：改变了参考实现，不能与原 vLLM-Omni 基线混算加速比。
固定模型版本与全部文件摘要见题包 `model-assets.json`。启动前逐文件核对大小和
SHA256；启动器阻止导入 vLLM、vLLM-Omni、SGLang 和历史独立引擎。

## Agent 要改什么

题包位于 `src/inferrsi/benchmark/tasks/qwen3-tts-npu/`：

| 文件 | 做什么 | 优化时的作用 |
| --- | --- | --- |
| `benchmark.py` | 解析 prepare/serve/collect/assess 参数 | 题包自身的可执行入口 |
| `evaluation.py` | 冻结判据、采集音频和计时、离线判定 | 评测规则和结果复核 |
| `baseline.py` | 校验模型资产、启用引擎导入隔离、启动服务 | 固定参考入口，记录代码与权重身份 |
| `inference.py` | 文本和指令编码 → Talker/code predictor → codec 解码 → PCM | 推理调度、缓存、算子、同步和解码优化的入口 |
| `service.py` | HTTP/SSE、请求校验、有界队列、单模型线程 | 批处理、排队和增量音频交付的入口 |
| `workload.jsonl` | 12 条原创中英文文本、交替音色和随机种子 | 固定比较两边的输入 |
| `TASK.md`、`task.json`、`model-assets.json` | 任务边界、模型和测量定义 | 固定实验口径 |

从冻结后的题包复制一个候选目录，Agent 修改候选目录内的推理和服务代码。官方包
提供模型结构和 tokenizer；必要时可在候选内适配这些组件，保留来源和许可证，记录
实际导入路径及摘要。不能更换权重、降低精度、缩短文本或缓存文本对应的成品音频。

参考实现逐请求生成完整波形，再通过 SSE 一次发送 PCM。它具有 SSE 接口，尚未做
真正的增量音频生成。因此基线 TTFA 包含整段生成时间。候选可以做分块解码和真正
的增量输出，但仍需保留完整音频和质量。这是服务级优化题，覆盖的范围超过单算子。

## 在 RSI 中怎样执行

```text
冻结任务与判据 → 基线 A/A 资格检查 → Agent 修改候选代码
→ Harness 在单 NPU 内顺序运行两边服务 → collect 留存音频和耗时
→ 独立 ASR／音色评分 → assess 核对 → 反馈下一轮 → 独立 final
```

这里的 prepare、serve、collect、assess 由题包内 benchmark.py 和 evaluation.py 实现。RSI 的实验调用方
负责触发它们；描述任务的 Markdown 不会自动启动评测。task、运行入口和判据对应
#362 的 Benchmark 职责，当前沿 scenario 入口提供，后续公共契约按 S1 对接。

## 冻结、启动与采集

搜索前确定门槛和 scorer 身份；scorer 身份应绑定 ASR、音色模型、文本规范化及独立
voice anchors 的固定版本或摘要。

```bash
inferrsi benchmarks run qwen3-tts-npu prepare \
  --output-dir <new-prepared-dir> --concurrency 1 4 8 --warmups <count> \
  --quality-scorer-id <frozen-scorer-identity> \
  --min-improvement-pct <gain-gate> \
  --max-error-rate-increase <absolute-WER-CER-margin> \
  --max-speaker-drop <cosine-margin> \
  --max-duration-change-pct <duration-gate> \
  --max-ttfa-regression-pct <first-audio-gate>
```

prepared 目录含完整参考实现、工作负载和 policy；加载时核对全部题包文件摘要。
准备固定模型的本地目录，在一个由调度器分配的 NPU 内前台启动：

```bash
inferrsi benchmarks run qwen3-tts-npu serve \
  --prepared <prepared-dir> --model-path <local-model-dir> \
  --port <port> --identity-output <new-identity.json>
```

服务仅绑定 loopback。`GET /health` 就绪后，调用方启动采集：

```bash
inferrsi benchmarks run qwen3-tts-npu collect \
  --prepared <prepared-dir> --endpoint <speech-endpoint> \
  --model <model-label> --timeout-seconds <request-timeout> \
  --output-dir <new-baseline-or-candidate-dir>
```

候选从独立进程执行 `python <candidate-dir>/baseline.py`，使用同样的 model-path、
port、identity-output 参数。`serve --prepared` 专门启动不可修改的参考题包，不用于
启动已修改的候选。collect/assess 始终使用原 prepared 判据。保留两个实现的身份、
启动日志、退出码和清理证据。外层 Harness 负责预约、总超时、readiness 和退出，
并可用现有 `inferrsi run` 的外部命令做顺序 AB/BA 配对。profiling 可按需执行。

测量保留每个并发的预热、WAV、chunk 到达和请求记录。RTF 为逐请求完成耗时／音频
时长的均值，TTFA 从 HTTP 发出到收到首个完整非空 PCM sample，包含服务排队。
单线程基线在并发请求下排队，候选的调度优化必须与这条基线实测对比。权重校验、
加载、预热、评分和清理单独计入全程代价，不算稳态推理加速。

## 离线验收

独立 scorer 对全部 WAV（含预热）评分，保留转写和音色参考。JSON 含 scorer_id、
baseline 与 candidate 列表；每条含 id、pcm_sha256、error_rate、speaker_similarity。
ID 为 `c<concurrency>-r<index>`，预热为 `c<concurrency>-w<index>`。英文用 WER、中文
用 CER；音色用同 verifier、同独立 anchor 的余弦分数。评分必须绑定实际 PCM 哈希。

```bash
inferrsi benchmarks run qwen3-tts-npu assess \
  --prepared <prepared-dir> --baseline <baseline-dir> \
  --candidate <candidate-dir> --quality <independent-scores.json>
```

assess 核对 WAV、请求与评分覆盖并重算指标。缺证据为 INCONCLUSIVE，越过冻结
质量门槛为 FAIL；全部通过后才提供可用 speedup，退出码分别为 2、1、0。
设备运行成功只能证明链路可执行；没有真实 ASR／音色评分不能宣称质量验收通过。
具体软件和设备检查的结果保存在对应验证记录中。
