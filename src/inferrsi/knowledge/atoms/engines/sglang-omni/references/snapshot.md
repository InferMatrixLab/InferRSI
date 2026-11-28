# Snapshot and dependencies

This graph is grounded in `sgl-project/sglang-omni` at **2cfb3b67becb437b70751defe37e63d3af4eedb0** (package **0.1.8**). Read the provenance before applying it to a different checkout. Source metadata and executable implementations take precedence over stale headings or examples.

The main `pyproject.toml` declares Python `>=3.10,<3.13`, `sglang==0.5.21`, `torch==2.13.0`, `torchvision==0.28.0`, `transformers==5.12.1`, `torchaudio==2.11.0`, `torchcodec==0.15.0`, and `diffusers==0.37.0`. These are literal declared pins, not a tested compatibility certification. CUDA-oriented dependencies include `flashinfer_python[cu13]==0.6.18`, `nixl-cu13>=1.1.0`, and `mooncake-transfer-engine-cuda13>=0.3.10`; do not combine wheel families arbitrarily. Inspect the selected manifest and install helper as a unit. Separate CPU, ROCm, MUSA, NPU and XPU manifests exist; their presence does not imply every model is validated on every backend. Apple arm64 uses a separate source-install path for SGLang `all_mps`.

The package exposes `sgl-omni` and registers an upstream `sglang.serve_backends` entry named `omni`. The graph uses the native `sgl-omni` surface; upstream CLI equivalence must be checked against the installed versions.

Repository LICENSE and project metadata both specify Apache-2.0. Model weight and vendored component licenses are separate; select the actual checkpoint and third-party notices when distributing artifacts. No upstream source code or heavyweight installer is bundled in this skill.

Known interpretation limits:

- Documentation sketches of Qwen pipelines and generic TTS integration may lag specific configs. Qwen3-TTS constructs `vocoder` before `tts_engine` so vocoder allocations exist when the KV budget is sized, while execution remains preprocessing → engine → vocoder.
- `StreamQueue` has a stale bounded-queue module heading and a `max_pending` attribute, but creates unbounded `asyncio.Queue()` objects. Backpressure is upstream; setting `max_pending` does not bound those queues.
- Architecture documentation describes a `FeedbackARModelRunner` design role. Treat proposed abstractions as design context until a concrete implementation and construction site are found.
- Main installation docs show inconsistent image namespaces in examples. Resolve a real image digest for the intended environment; this graph does not prescribe an unverified image.

Evidence:

- [pyproject.toml](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/pyproject.toml)
- [sglang_omni/__init__.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/__init__.py)
- [LICENSE](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/LICENSE)
- [docs/get_started/installation.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/get_started/installation.md)
- [sglang_omni/pipeline/stage/stream_queue.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/pipeline/stage/stream_queue.py)
- [sglang_omni/models/qwen3_tts/config.py](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/sglang_omni/models/qwen3_tts/config.py)
- [docs/developer_reference/pipeline.md](https://github.com/sgl-project/sglang-omni/blob/2cfb3b67becb437b70751defe37e63d3af4eedb0/docs/developer_reference/pipeline.md)
