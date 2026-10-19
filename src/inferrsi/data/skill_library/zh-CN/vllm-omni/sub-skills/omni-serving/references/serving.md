# 服务操作参考

## 环境与基线

在目标 Linux 上使用独立环境和匹配的加速器栈。元数据允许 Python >=3.10,<3.14；固定提交的快速开始使用 Python 3.12 与 vLLM 0.31.0，不能沿用旧 AREX 的 0.26 假设。安装前明确 release/wheel/驱动组合，本 Skill 不包含 wheel 或模型权重。

环境就绪后检查本机 CLI：

```bash
vllm serve --omni --help
vllm bench serve --omni --help=all
```

固定提交快速开始的最小示例（需要模型访问及足够显存）：

```bash
vllm serve Tongyi-MAI/Z-Image-Turbo --omni --port 8091
```

```bash
curl -s http://localhost:8091/v1/images/generations   -H 'Content-Type: application/json'   -d '{"prompt":"a cup of coffee on the table","size":"1024x1024","response_format":"b64_json","seed":42}'
```

检查响应状态、非空有效媒体及尺寸；HTTP 200 不足以证明图像质量。本地 Python 入口为 `from vllm_omni.entrypoints.omni import Omni`，初始化选定模型后调用 `.generate(prompt)`；输出字段依模态而定。按所选 API 生命周期约定关闭所拥有的资源。

## 阶段配置

部署 YAML 覆盖已有 `stage_id`。`devices`、副本、TP、资源预算可因阶段而异；`DeployConfig` 顶层引擎字段对全流水线生效。还存在兼容透传字段，需检查解析后配置，不能臆造通用优先级捷径。模型采样约束仍归模型所有。

Qwen3-Omni 的源码部署使用异步块及 SharedMemoryConnector，含 `initial_codec_chunk_frames: 4`、`codec_chunk_frames: 25`、`codec_left_context_frames: 25`；这些是模型特定默认值，不是所有 TTS 的建议值。搜索延迟时保持 codec 上下文语义，记录各阶段有效队列/序列/token/计算图限制。

## 扩散执行模板

在此固定提交，Qwen-Image 文档明确支持请求批处理及单步连续批处理；源码/模型版本变化时需重新核对。先用以下串行基线：

```bash
vllm serve Qwen/Qwen-Image --omni --port 8091 --max-num-seqs 1
```

再逐项比较：请求批处理使用 `--max-num-seqs N`，单步调度使用 `--step-execution --max-num-seqs N`。`--request-batch-max-wait-ms` 仅影响请求模式，不影响单步模式。支持单步不自动支持批量单步。`--diffusion-streaming-output` 会按需开启单步执行，但只有可产出块的流水线才会返回中间媒体。

## 实验记录契约

固定模型及 tokenizer/processor 版本、部署摘要、精度、后端、请求语料、输出形状/时长/步数、采样及种子、到达过程、并发、预热、重复次数和失败。记录实际回退与有效配置。同条件重复比较，报告 p50/p95/p99、样本量、带单位的吞吐、GPU/主存峰值、阶段耗时及传输量。

语音需区分文本 TTFT 和首音频 TTFP，报告块间隙长尾以及带计时边界的 RTF；明确首音频是收到首个 delta、解码出首包，还是首次可听见的语音，否则前导静音和编码会干扰比较。这些指标可能需要额外埋点。图像/视频采用媒体单位及端到端延迟，局部 denoiser kernel 速度不等于服务吞吐。先记录正确性/质量失败再筛选，更快但无效的配置不参与排名。

## 故障恢复

| 症状 | 检查 | 下一步 |
|---|---|---|
| `--omni` 不可用/导入不兼容 | 当前 vLLM/Omni 版本和命令路径 | 对齐固定提交环境，不猜旧 CLI 归属 |
| utilization 之和小于一仍启动 OOM | 实际权重、计算图/workspace、阶段启动日志 | 降低容量/图覆盖或调整放置，不能盲目增加 utilization |
| 无首音频/块间隙大 | 请求到阶段追踪、上游等待、块契约、下游队列 | 单请求基线，分离阶段与传输延迟，查看错误路径 |
| 不支持批处理/单步组合 | 流水线能力及 runner 检查 | 回到串行请求路径；新增能力作为代码变更验证 |
| 媒体损坏/重复/缺失 | 载荷形状/类型、块身份/顺序、累积和完成事件 | 保存追踪与输出，暂停性能搜索并跑输出/传输测试 |
| 多卡挂起 | 通信组、放置、各 rank 启动/错误及对端故障 | 最小受支持拓扑复现，验证受影响的原生传输/通信 |

参见[quickstart、schema、deploy、modes、qwen-deploy 证据](../../../references/evidence.md)。命令经过源码核对，本包未实际启动 GPU 服务。
