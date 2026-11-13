# Recipes, configuration and experiment contract

## Effective configuration

Topology is declared in model Python config classes; user YAML/CLI override existing stages, not add/remove stages. YAML `stages` is a mapping keyed by stage name. Stage top-level fields feed process/placement planning; `engine.*` feeds SGLang arguments only for engine stages; `factory.*` feeds the stage constructor. Unknown free-form engine/factory keys pass through and still require a real consumer; their acceptance by the parser proves no feature support.

CLI overrides YAML; explicit per-stage paths override shared selectors/broadcast values. Repeated writes to the same leaf at the same precedence conflict rather than silently using the last value. `--mem-fraction-static` broadcasts to engine stages. Use `config resolve --show config|diff|provenance` and `config explain PATH` to observe the effective value. A `kv_cache_bytes` value must not coexist with `mem_fraction_static` or `max_total_tokens`; clear inherited conflicting values explicitly where appropriate.

These source-checked commands run from the pinned source checkout with its dependencies and checkpoint available. The serve line starts a process/GPU workload; only run it when deployment is within the task's authorization. The example value 8 is an experiment point, not a recommended optimum.

```bash
sgl-omni config resolve --config examples/configs/qwen3_tts_0_6b.yaml --show diff --tts_engine.engine.max_running_requests 8
sgl-omni config explain stages.tts_engine.engine.max_running_requests --config examples/configs/qwen3_tts_0_6b.yaml --tts_engine.engine.max_running_requests 8
sgl-omni serve --model-path Qwen/Qwen3-TTS-12Hz-0.6B-Base --config examples/configs/qwen3_tts_0_6b.yaml --tts_engine.engine.max_running_requests 8 --host 127.0.0.1 --port 8000
```


## Select a model-specific contract

| Model / path | Recipe decision and dependency caveat |
|---|---|
| Qwen3-Omni | Multimodal text/image/audio/video input, text or text+audio output through chat. Speech mode is required for audio; `--text-only` can return no audio even if requested. Colocated recipe rejects thinker TP=2; use supported disaggregated config for TP. All videos in one request require the same sampled frame rate. |
| Qwen3-TTS | Base 0.6B/1.7B use preprocessing → engine → vocoder and reference-conditioned speech. `12Hz` is codec frame rate; waveform output is 24 kHz. CustomVoice/VoiceDesign have different request/reference semantics. Preserve main Transformers 5.12.1/SGLang 0.5.21 stack; upstream `qwen-tts==0.1.1` is installed with `--no-deps` plus both system/Python sox as recipe requires. Do not downgrade Transformers to its own package pin; the repository supplies compatibility shims. |
| Qwen3-ASR / Fun-ASR | Use transcription/realtime recipes and the selected platform runner. Apple MLX/Torch-MPS support is model-specific, not general GPU parity. |
| Fish S2-Pro / Drama 3, Higgs, MOSS, Voxtral, ZONOS2 | TTS recipes differ in reference encoding, codebooks, vocoder buffering, licenses and optional dependencies. Read the actual cookbook and `models/<family>/config.py` before sharing settings. Drama 3's `fishaudio` extra is not needed for every TTS model. |
| MiniMax Music 3 / LLaDA2-Uni | MiniMax Music 3 has model-specific AR + flow-matching DIT music generation. LLaDA2-Uni's cookbook covers an experimental text-output path despite describing the model's broader image-generation architecture. Do not turn architecture descriptions into supported endpoint claims or treat this as a generic SGLang diffusion server. |

Choose speech, transcription, chat or realtime endpoint from the recipe; they do not share a universal JSON schema. Preserve reference text/audio, sample rate and encoding. Inspect server capabilities when available. Once SSE starts, HTTP 200 can carry an error event; queue-full errors may be represented as server error code 503 inside the stream. Treat missing audio or partial output as a failed completion, not a latency win.

## Measure a constrained objective

Capture source/weights, effective config, package versions, hardware/driver, topology, startup/graph capture versus warmed state, dataset revision and sample IDs, input/output lengths, seed/sampling, reference voice and arrival pattern. Keep warmup out of measurement. Compare per-request logs and artifacts, not an isolated aggregate.

| Workload | Performance observations | Quality / correctness floor |
|---|---|---|
| TTS streaming | First playable audio, completion p50/p95/p99, chunk timing/underrun, RTF, completed audio-seconds/s, failures | WER, voice similarity/listening checks as applicable, audio duration, continuity, correct sample rate, natural versus length stop |
| Video + spoken question → text/audio | Media decode/preprocessing time, first text versus first audio, terminal latency, throughput, prompt tokens | Task accuracy, transcription/WER, frame sampling held constant, complete output |
| ASR/realtime | First partial, final latency, partial intervals and endpointing delay | WER/CER with stated normalization, stable final text, cancellation/session isolation |

Proposed chunk-gap and playback criteria may require additional instrumentation; do not assert every benchmark emits every metric. Native `benchmark_omni_streaming_ttft` names its metric TTFT but measures the first **audio** delta; it is not first text token. The following client targets an already running Qwen3-Omni speech server and submits workload requests:

```bash
python -m benchmarks.eval.benchmark_omni_streaming_ttft --base-url http://localhost:8001 --label baseline --repeats 5
```


The SeedTTS runbook uses `benchmarks.eval.benchmark_tts_seedtts`: it can start a TTS server, download/read a dataset, save audio, then run ASR scoring. It is not a harmless parser check. Read its current arguments and runbook before launching. Its standard runbook reports speed/RTF/WER, not SIM/UTMOS; the MiniCPM offline runbook has separate scoring artifacts. Always report scoring coverage/skips and length stops. A reduced generation length can improve apparent latency while lowering quality.

Preserve a baseline config and results. Sweep a bounded factor justified by traces (admission, process placement, stage memory, supported graph/precision, model chunking), retest the same quality gate, and retain rejected trials. Improvements remain workload/hardware-specific; no speed claim is justified by this skill package.

Pinned evidence:

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
