# 快照与依赖

本图基于 `sgl-project/sglang-omni` 的 **2cfb3b67becb437b70751defe37e63d3af4eedb0**（包版本 **0.1.8**）。应用到其他 checkout 前先核对来源记录。遇到过时标题或示例时，以源码元数据和实际执行实现为准。

主 `pyproject.toml` 声明 Python `>=3.10,<3.13`、`sglang==0.5.21`、`torch==2.13.0`、`torchvision==0.28.0`、`transformers==5.12.1`、`torchaudio==2.11.0`、`torchcodec==0.15.0`、`diffusers==0.37.0`。这些是原样记录的依赖约束，不是已经验证的兼容性保证。CUDA 依赖包含 `flashinfer_python[cu13]==0.6.18`、`nixl-cu13>=1.1.0` 和 `mooncake-transfer-engine-cuda13>=0.3.10`；不要随意混合 wheel 系列。将所选依赖清单与安装脚本作为整体核对。仓库另有 CPU、ROCm、MUSA、NPU 和 XPU 清单；清单存在不表示所有模型都已在各后端验证。Apple arm64 采用单独的 SGLang `all_mps` 源码安装路径。

包提供 `sgl-omni`，并在上游 `sglang.serve_backends` 下注册 `omni`。本图使用原生 `sgl-omni` 接口；是否与上游 CLI 等价，需核对实际安装版本。

仓库 LICENSE 与项目元数据均为 Apache-2.0。模型权重和内嵌第三方组件的许可另行适用；分发产物时应核对具体权重与第三方声明。本技能不打包上游源码或大型安装器。

已知解释边界：

- Qwen 流水线示意和通用 TTS 集成文档可能落后于具体配置。Qwen3-TTS 先构造 `vocoder` 再构造 `tts_engine`，使 KV 预算计算时已计入 vocoder 分配；执行仍为 preprocessing → engine → vocoder。
- `StreamQueue` 有过时的“有界队列”模块标题及 `max_pending` 属性，但实际创建无界 `asyncio.Queue()`。背压在上游；设置 `max_pending` 不会限制这些队列。
- 架构文档中的 `FeedbackARModelRunner` 是设计角色。找到实际实现和构造位置前，仅将这类抽象作为设计背景。
- 主安装文档中的镜像命名空间示例不一致。应确认目标环境可用的真实镜像 digest；本图不指定未经核验的镜像。

证据：

- [pyproject.toml](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/pyproject.toml)
- [sglang_omni/__init__.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/__init__.py)
- [LICENSE](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/LICENSE)
- [docs/get_started/installation.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/get_started/installation.md)
- [sglang_omni/pipeline/stage/stream_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/pipeline/stage/stream_queue.py)
- [sglang_omni/models/qwen3_tts/config.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/models/qwen3_tts/config.py)
- [docs/developer_reference/pipeline.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/pipeline.md)
