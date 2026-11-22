---
name: inference-benchmark-design
description: 'Select task quality gates, reference parity checks and performance workloads for text, agentic coding, work agents, cache-aware ASR, TTS, full-duplex audio/video, image, video and VLA inference. Covers AIPerf AgentX/Exgentic replay, vLLM/SGLang benchmark boundaries, VLA action-chunk timing and quality, SLO-aware metrics and InferRSI integration.'
metadata:
  inferrsi: |
    {
      "tags": [
        "benchmark",
        "evaluation",
        "serving",
        "measurement",
        "task-quality",
        "reference-parity",
        "agentic-coding",
        "work-agents",
        "aiperf",
        "tts",
        "full-duplex",
        "image-generation",
        "video-generation",
        "asr",
        "stream-boundaries",
        "treatment-delivery",
        "trial-validity",
        "protocol-audit",
        "trial-evidence",
        "result-origin",
        "oracle-boundary",
        "candidate-selection",
        "accepted-prefix",
        "state-restoration",
        "completion-accounting",
        "vla",
        "embodied",
        "action-chunks",
        "closed-loop",
        "gpu-timing",
        "profiler-attribution",
        "measurement-validity"
      ],
      "status": "candidate",
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "sources": [
        {
          "type": "document",
          "url": "https://github.com/InferMatrixLab/InferRSI/issues/60#issuecomment-6310920198",
          "version": "2026-10-21 report",
          "sha256": "c56a1b169d70d9cd2bfcf073b13e001354945d71c54ebde5740f3036e4ee4496",
          "readset": "references/task-benchmark-selection.md",
          "scope": "Distilled task matrix, metric definitions, integration boundaries and command templates; original report is source/documentation review, not a runtime benchmark."
        },
        {
          "type": "git",
          "url": "https://github.com/vllm-project/vllm-omni",
          "commit": "b20e5bac96a029172a59559438ad0590460aeb3c",
          "paths": [
            "benchmarks/accuracy/README.md",
            "benchmarks/accuracy/image_to_image/README.md",
            "benchmarks/accuracy/text_to_image/README.md",
            "benchmarks/diffusion/backends.py",
            "benchmarks/diffusion/diffusion_benchmark_serving.py",
            "benchmarks/tts/README.md",
            "benchmarks/tts/bench_tts.py",
            "docs/cli/bench/serve.md",
            "tests/e2e/accuracy/wan22_i2v/test_wan22_i2v_video_similarity.py",
            "vllm_omni/benchmarks/data_modules/seed_tts_eval.py",
            "vllm_omni/benchmarks/duplex_session_metrics.py",
            "vllm_omni/benchmarks/metrics/metrics.py"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/sgl-project/sglang",
          "commit": "844d2b5decf6257aa192744cbdaaffb8ad797263",
          "paths": [
            "docs/cookbook/base/benchmarks/diffusion_model_benchmark.mdx",
            "docs/docs/developer_guide/bench_serving.mdx",
            "docs/docs/developer_guide/evaluating_new_models.mdx",
            "python/sglang/benchmark/serving.py",
            "python/sglang/multimodal_gen/benchmarks/bench_offline_throughput.py",
            "python/sglang/multimodal_gen/benchmarks/bench_serving.py",
            "python/sglang/multimodal_gen/test/test_utils.py"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/vllm-project/vllm",
          "commit": "a9bf45ed8a856a0b1839197152d0d26fabb6599c",
          "paths": [
            "docs/benchmarking/cli.md",
            "vllm/benchmarks/serve.py"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/ai-dynamo/aiperf",
          "commit": "30420ce581d4fc9eeb34b4d47defe367ab8c3a11",
          "paths": [
            "docs/accuracy/accuracy-benchmarking.md",
            "docs/benchmark-datasets.md",
            "docs/metrics-reference.md",
            "docs/tutorials/agentic-code-generator.md",
            "docs/tutorials/agentx-mvp.md",
            "docs/tutorials/h-cua-perf.md",
            "docs/tutorials/tracelab-trace.md",
            "docs/tutorials/weka-trace.md",
            "docs/tutorials/working-with-profile-exports.md",
            "src/aiperf/dataset/loader/exgentic_v2.py",
            "src/aiperf/metrics/types/inter_token_latency_metric.py"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/sgl-project/sglang-omni",
          "commit": "f31cf9e9af749040ffa6dbdf064882c443a2fd37",
          "paths": [
            "benchmarks/README.md",
            "benchmarks/duplex/serving.py",
            "benchmarks/metrics/performance.py",
            "benchmarks/metrics/speaker_similarity.py",
            "benchmarks/metrics/wer.py",
            "docs/developer_reference/full_duplex_bench.md",
            "docs/developer_reference/full_duplex_metrics.md"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/Lucky-Lance/OmniInteract",
          "commit": "de304cef35fd9a50a5caadb5090c34cfbf0dd868",
          "paths": [
            "eval/README.md",
            "eval/evaluation/compute_unified_eval.py",
            "eval/evaluation/summarize_unified_eval.py"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/OpenBMB/Omni-DuplexEval",
          "commit": "962cec448ac37a377ffb963b476778777d11d346",
          "paths": [
            "README.md"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/InferMatrixLab/InferRSI",
          "commit": "b3ef95a6dd3abd85c19b5527fe46e80ccb3521d4",
          "paths": [
            "docs/quickstart.md",
            "src/inferrsi/harness/evaluation.py",
            "src/inferrsi/model/protocols/metrics.py"
          ],
          "readset": "references/task-benchmark-selection.md"
        },
        {
          "type": "git",
          "url": "https://github.com/NVIDIA/NeMo-Speech.cpp",
          "commit": "20999cc921d2b14aa58708f61756a8b2e787ba20",
          "paths": [
            "BENCHMARK.md",
            "LICENSE",
            "NOTICE",
            "THIRD_PARTY_NOTICES.md",
            "src/asr/encoder/cache_aware_encoder.cpp",
            "src/asr/encoder/cache_aware_encoder.h",
            "src/asr/encoder/fastconformer.h",
            "src/asr/recognizer.cpp",
            "src/asr/runner.cpp",
            "src/asr/runner.h",
            "src/asr/vad/vad_endpointer.cpp",
            "src/asr/vad/vad_endpointer.h",
            "tests/cpp/asr/CMakeLists.txt",
            "tests/cpp/asr/test_cache_stream_geometry.cpp"
          ],
          "readset": "references/cache-aware-asr-stream-boundaries.md"
        },
        {
          "type": "git",
          "url": "https://github.com/OpenBMB/JustGoal",
          "commit": "f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d",
          "paths": [
            "LICENSE",
            "NOTICE",
            "README.md",
            "goal_full_shape/fable-5.1/dsa_decode_fwd/dsa_sparse_attention_h16_ckv512_kpe64_topk2048_ps64/dsa_decode.cu",
            "goal_full_shape/fable-5.1/dsa_decode_fwd/dsa_sparse_attention_h16_ckv512_kpe64_topk2048_ps64/main.py",
            "goal_single_shape/fable-5.1/dsa_decode_fwd/t8_topk2048/dsa_kernel.cu",
            "goal_single_shape/fable-5.1/dsa_decode_fwd/t8_topk2048/dsa_kernel.py",
            "kda05_reproduction_full_shape/opus-4.8/fa4_bwd/attention_bwd_causal_h16_d128/cute_fabwd_bshd_v5c_fusedzero/helpers/NOT_INCLUDED.md"
          ],
          "readset": "references/justgoal-source.json",
          "license": "Apache-2.0 repository default; NOTICE exceptions and excluded proprietary helper retained",
          "scope": "Selected kernel entry/workspace/stream contracts and distribution boundary; source-only, no execution"
        },
        {
          "type": "document",
          "url": "https://github.com/OpenBMB/JustGoal/blob/f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d/paper.pdf",
          "version": "Repository-paired PDF at f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d",
          "sha256": "6bfa1a2728546def4c48e15cf55f31d92a543264787318f1522236c80a0ae8c6",
          "readset": "references/justgoal-source.json",
          "license": "UNKNOWN",
          "scope": "Complete 21-page paper and appendices: controlled comparison, independent correctness, repair/coverage and timing evidence; author-reported, no PDF/figure redistribution"
        },
        {
          "type": "git",
          "url": "https://github.com/li-ch/autotunebench",
          "commit": "64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f",
          "paths": [
            "ARTIFACT.md",
            "README.md",
            "CITATION.cff",
            "LICENSE",
            "config/protocol.yaml",
            "pdb/ingest_validate.py",
            "pdb/store.py",
            "agents/loop.py",
            "agents/adapter.py",
            "orchestrator/cli.py",
            "gates/g2_runtime.py",
            "gates/g3_correctness.py",
            "gates/g5_graduation.py",
            "gates/schema.py",
            "harness/kernel_bench.py",
            "figs/plot_cand_ab_saturation.py",
            "scripts/kernelbench_tabulate.py",
            "experiments/kernelbench_l1/results/README.md",
            "experiments/kernelbench_l1/results/TABLE.md",
            "experiments/astra_parity/README.md",
            "observability/iterations.jsonl",
            "experiments/kernelbench_l1/kernelbench_tasks/UPSTREAM_LICENSE",
            "experiments/kernelbench_l1/kernelbench_tasks/README.md"
          ],
          "readset": "references/autotunebench-trial-validity.md"
        },
        {
          "type": "paper",
          "id": "arxiv:2609.18123",
          "version": "v1",
          "url": "https://arxiv.org/abs/2609.18123v1",
          "sections": [
            "1-8",
            "References",
            "Figures 1-6",
            "Tables 1-7"
          ],
          "readset": "references/autotunebench-trial-validity.md"
        },
        {
          "type": "git",
          "url": "https://github.com/IntelLabs/Xe-Forge",
          "commit": "6cd3ee98dfe32746b345a6abe521fa4cb9bdc187",
          "paths": [
            "CONTRIBUTING.md",
            "LICENSE",
            "README.md",
            "docs/CORRECTNESS.md",
            "docs/KERNEL_REPO.md",
            "pyproject.toml",
            "src/xe_forge/claude/generator.py",
            "src/xe_forge/claude/templates/CLAUDE.md.j2",
            "src/xe_forge/cli.py",
            "src/xe_forge/core/trial_manager.py",
            "src/xe_forge/engines/claude_engine.py",
            "src/xe_forge/external.py",
            "src/xe_forge/skills/__init__.py",
            "src/xe_forge/skills/benchmark.py",
            "src/xe_forge/skills/trial.py",
            "src/xe_forge/skills/upstream.py",
            "tests/test_benchmark_gate.py",
            "tests/test_trial_manager_ranking.py"
          ],
          "readset": "references/xeforge-source.json",
          "license": "Apache-2.0 repository default; DCO and curated-example exclusions retained",
          "scope": "Selected source-bound trial origin/comparison identity, host outcomes, measured-only selection and baseline-oracle contracts; source-only, no execution"
        },
        {
          "type": "paper",
          "id": "arxiv:2605.26118",
          "version": "v1",
          "url": "https://arxiv.org/html/2605.26118v1",
          "sections": [
            "Abstract",
            "I-VIII",
            "References",
            "Appendix A",
            "Tables 1-3",
            "Algorithm 1",
            "Listing 1",
            "Figure captions 1-15"
          ],
          "readset": "references/xeforge-source.json",
          "license": "CC-BY-4.0",
          "scope": "Complete HTML text/appendix and captions; historical author-reported context, unused graphic values remain unverified"
        },
        {
          "type": "git",
          "url": "https://github.com/Neroued/ninfer",
          "commit": "1882c6adbc98043fcf89f3589aa5addb3742777a",
          "paths": [
            "LICENSE",
            "README.md",
            "docs/maintainer/engine-architecture.md",
            "docs/maintainer/speculative-decoding.md",
            "docs/maintainer/context-management.md",
            "docs/performance/methodology.md",
            "docs/performance/qwen3.8-27b.md",
            "include/ninfer/ops/gdn_replay.h",
            "src/core/gdn_replay_records.h",
            "src/core/gdn_replay_records.cpp",
            "src/core/linear_attention_state.h",
            "src/core/linear_attention_state.cpp",
            "src/models/qwen3_5/state/state_image.h",
            "src/models/qwen3_5/state/state_image.cpp",
            "src/models/qwen3_5/execution/gdn.cpp",
            "src/models/qwen3_5/execution/text.cpp",
            "src/models/qwen3_5/program/decode.cpp",
            "src/models/qwen3_5/program/commit.cpp",
            "src/models/qwen3_5/program/mtp.cpp",
            "src/models/qwen3_5/session/commit.cpp",
            "src/models/qwen3_5/session/binding.cpp",
            "src/models/qwen3_5/session/checkpoints.cpp",
            "src/runtime/engine/engine_execution.inl",
            "src/runtime/executor/contract.h",
            "src/runtime/executor/local_executor.h",
            "src/ops/linear_attention/gated_delta_net/replay/fold.cpp",
            "tests/ops/linear_attention/gated_delta_net/test_fold.cpp"
          ],
          "readset": "references/ninfer-source.json",
          "license": "Apache-2.0",
          "scope": "Selected Qwen3.5 GDN/MTP state-restoration, accepted-prefix and completion evidence contracts; historical results retain their separate reported revision. Source-only, no native execution."
        },
        {
          "type": "git",
          "url": "https://github.com/yuekaizhang/faster-cosyvoice",
          "commit": "f1049c59196c2c1a890079abc56056b43f27cd1d",
          "paths": [
            "README.md",
            "README_zh.md",
            "docs/benchmark.md",
            "docs/benchmark_zh.md",
            "docs/usage.md",
            "docs/usage_zh.md",
            "examples/offline_inference.py",
            "examples/stream_client.py",
            "faster_cosyvoice/config/settings.py",
            "faster_cosyvoice/llm/engine.py",
            "faster_cosyvoice/server/app.py",
            "faster_cosyvoice/server/arguments.py",
            "faster_cosyvoice/server/audio_encode.py",
            "faster_cosyvoice/server/leading_silence.py",
            "faster_cosyvoice/server/openai_speech.py",
            "faster_cosyvoice/server/protocol.py",
            "faster_cosyvoice/streaming/chunker.py",
            "faster_cosyvoice/streaming/session.py",
            "faster_cosyvoice/streaming/token2wav_batcher.py",
            "faster_cosyvoice/streaming/token2wav_scheduler.py",
            "faster_cosyvoice/token2wav/builders.py",
            "faster_cosyvoice/token2wav/cosyvoice/flow/DiT/modules.py",
            "faster_cosyvoice/token2wav/cosyvoice/flow/flow.py",
            "faster_cosyvoice/token2wav/cosyvoice/hifigan/generator.py",
            "faster_cosyvoice/token2wav/flashinfer_dit.py",
            "faster_cosyvoice/token2wav/flashinfer_flow.py",
            "faster_cosyvoice/token2wav/frontend.py",
            "faster_cosyvoice/token2wav/matcha_audio.py",
            "faster_cosyvoice/token2wav/token2wav.py",
            "pyproject.toml",
            "tests/test_session.py",
            "tests/test_stream_client.py",
            "tests/test_token2wav_batcher.py"
          ],
          "readset": "references/faster-cosyvoice-source.json",
          "license": "UNKNOWN overall; selected file-level Apache-2.0 headers and unresolved inherited attribution retained",
          "scope": "Selected PCM/playout, routed-credit, chunk-dependency and timing-denominator source audit; original analysis and immutable links only, no code/media copying or native/model/quality/service execution"
        },
        {
          "type": "git",
          "url": "https://github.com/SEU-PAISys/Embodied.cpp",
          "commit": "156bed151826780e2ce0132f8d0e3540889ae8cd",
          "paths": [
            "adapter/typed_io.py",
            "eval/client/libero_profile.py",
            "eval/client/vla_cpp_client.py",
            "eval/conf/libero_smolvla_object_q8_eval.yaml",
            "eval/README.md",
            "eval/smolvla_q8_fixed_boundary_20261002.json",
            "eval/smolvla_q8_object_followup_20260930.md",
            "eval/SMOLVLA_VALIDATION.md",
            "eval/THREE_MODEL_VALIDATION.md",
            "eval/VLA_BENCHMARK_STANDARD.md",
            "LICENSE",
            "README.md",
            "scripts/aggregate_smolvla_object_eval.py",
            "scripts/bench_vla_boundary.py",
            "scripts/profile_smolvla_python_baseline.py",
            "serving/vla-server.cpp",
            "serving/vla.proto"
          ],
          "readset": "references/embodied-cpp-source.json",
          "license": "Apache-2.0",
          "scope": "Selected CPU observation-to-action benchmark, client/profiler/aggregation and author artifact contracts; source-derived methodology, not native execution or quality/performance acceptance"
        },
        {
          "type": "paper",
          "id": "arxiv:2607.02501",
          "version": "v3",
          "url": "https://arxiv.org/abs/2607.02501v3",
          "sections": [
            "4 (VLA discussion and Table 3)"
          ],
          "readset": "references/embodied-cpp-source.json",
          "license": "CC-BY-4.0",
          "scope": "Independently normalized VLA metric semantics; predates the later SmolVLA experiment"
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/nsight-compute/2025.3/ProfilingGuide/index.html",
          "version": "Nsight Compute 2025.3",
          "sha256": "c9f3b812ce50a46a751f2c92eff628177554f4f6678bb3381468b1dac91b607e",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected Replay, Overhead, Hardware Model, Metrics Structure, Range and Precision, Reproducibility, Clock Control and Cache Control; source contracts only, no profiler execution."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/nsight-compute/2025.3/NsightComputeCli/index.html",
          "version": "Nsight Compute 2025.3",
          "sha256": "c5129a8afe2439c04906f19312393972ae123062d2ee0894b3ba2b11af43471e",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected Metric Collection and Profiling option defaults for clock/cache control and metric queries; actual target support must be checked separately."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/nsight-systems/2025.3/UserGuide/index.html",
          "version": "Nsight Systems 2025.3",
          "sha256": "1d42e35005fa9a4cb21b2c65d0018e4b065c3756dbba308dc0c41f79746e751f",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected CLI Profile options, CUDA graph/node tracing and CUDA API/kernel/launch/MemOps statistics reports; absence of NCU replay controls is an author inference, not a launcher guarantee."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/cuda/archive/12.9.1/cuda-c-best-practices-guide/index.html",
          "version": "CUDA Toolkit 12.9.1 archive",
          "sha256": "0fcaf0c361d00de56a9870ba96db871a0b880904121e1dfb215ab9882470120b",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected Assess/Optimize, Application Profiling, Amdahl's Law, Timing and Instruction Throughput; normalization/adoption procedure is an unverified author synthesis."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/cuda/archive/12.9.1/cuda-c-programming-guide/index.html",
          "version": "CUDA Toolkit 12.9.1 archive",
          "sha256": "06499a0c6bfc6925cf54c76f6ba86a4986a081c44c602e10d4ef3b4f33a33865",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected Concurrent Kernel Execution, CUDA Graphs (structure, definition/instantiation/execution) and Events; no constant launch/replay overhead or device test claimed."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/cuda/archive/10.2/nsight-compute/docs/NsightComputeCli/index.html",
          "version": "CUDA Toolkit 10.2 archive, Nsight Compute CLI",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected nvprof Metric Comparison for dram__bytes_read.sum, dram__bytes_write.sum and smsp__inst_executed.sum. Legacy names do not guarantee current chip/tool availability; no raw-byte digest retained for this browser read."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/deploy/nvidia-smi/index.html",
          "version": "Unversioned NVIDIA System Management Interface page, retrieved 2026-11-15; content pinned by SHA-256",
          "sha256": "94d1737cdff11b5ef89b121e97365706feeb8ccc18978fecec571bdbbe6ec9ed",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected Performance State, Clocks Event Reasons, clocks, temperature and power reporting. Public page may change; digest identifies inspected HTML, which is not redistributed."
        },
        {
          "type": "git",
          "url": "https://github.com/triton-lang/triton",
          "commit": "9641643da6c52000c807b5eeed05edaec4402a67",
          "paths": [
            "python/triton/testing.py"
          ],
          "readset": "references/gpu-measurement-validity.md",
          "license": "MIT",
          "scope": "v3.2.0 do_bench: write-based cache.zero_ flush, preliminary estimate and per-sample event boundaries; tag resolved with git ls-remote, source inspected in public browser. No flush comparison run."
        },
        {
          "type": "document",
          "url": "https://docs.pytorch.org/docs/2.7/cpp_extension.html",
          "version": "PyTorch 2.7",
          "readset": "references/gpu-measurement-validity.md",
          "scope": "Inspected load/load_inline and the extension name, build-directory and pybind11 module contract. Distinct names for separately loaded variants are author advice, not a documented universal duplicate-name failure; no raw-byte digest retained for this browser read."
        },
        {
          "type": "paper",
          "url": "https://arxiv.org/html/2509.14279v1",
          "id": "arxiv:2509.14279",
          "version": "v1",
          "sections": [
            "3",
            "Appendix A",
            "Appendix C.3"
          ],
          "readset": "references/gpu-measurement-validity.md",
          "license": "CC-BY-4.0",
          "scope": "Lange et al., Towards Robust Agentic CUDA Kernel Benchmarking, Verification, and Optimization. Inspected benchmark loopholes, compromised-task filtering/examples and eager/compiled baseline comparisons; reports remain author-reported, not locally reproduced."
        }
      ],
      "empirical_validation": "not_run",
      "applicability": {
        "scope": "Selecting task quality gates, reference parity checks and performance workloads for text, agentic coding, work agents, cache-aware ASR, TTS, full-duplex audio/video, image and video inference, and designing goodput-based multi-regime comparisons that fit InferRSI's evidence trail; interpreting treatment delivery, arm validity and stated-versus-observed protocol enforcement in supplied tuning reports; interpreting source-bound kernel trial origin, host evaluator outcomes, unresolved performance and measured-only versus manual candidate selection; designing and interpreting the selected NInfer hybrid speculative state-restoration and completion validation contract; designing or auditing VLA deployment comparisons with explicit observation-to-action boundaries, generated/replayed horizons, per-task quality and source/precision identity; assessing GPU timing validity and profiler-based attribution of kernel/inference gains",
        "prerequisites": "The primary objective, timing boundary, quality gates, sample/failure accounting, required regimes, repetitions, seeds and decision rule are frozen before optimization; baseline and candidate share hardware, software stack, input distribution, benchmark configuration, warmup and measurement protocol, and on a shared machine also one time window and dedicated devices; cache-aware ASR also requires the selected model/config and first/steady geometry, decoded clock and reset/EOU/EOF boundaries to be established; VLA comparisons also freeze generated/replayed horizons, initial-state/noise protocol and intended precision or quantization treatment",
        "input_contract": "The task family and deployment use case; candidate quality evaluators and reference parity; the declared SLO and the caller's policy on which regimes must improve or must not regress; for an audit, a supplied fixed-workload report with request-to-trial grouping, exclusion and failure counts and the declared aggregation rule; for a treatment audit, the frozen delivery/arm-validity rules, run/candidate identities, feedback and consumer-input evidence, and per-arm raw records; for a kernel trial audit, complete saved candidate bytes and IDs, baseline/spec/reference/variant identities, result-origin fields, raw host outcome and return code, named gate and persisted ratio, actual oracle and the selecting/delivering caller; for the NInfer slice, a complete checkpoint/frontier identity, physical verify-block/state oracle, final adopted extents and correlated execution/termination records; for VLA audits, the declared CPU input/output boundary, source/fixture/checkpoint/processor identities, per-task trial scope and available raw records or explicit artifact gaps",
        "produced_artifact": "A frozen benchmark design with evaluators, reference parity, primary objective, timing boundary, quality gates, required regimes, repetition and seed rules and an explicit decision config, plus the evidence-tree layout a PASS claim must produce; for a supplied report, the computed threshold result and missing evidence. Candidate knowledge, not qualification of any model or backend; for a treatment audit, a contract-bound eligibility and interpretation report separating treatment exposure, observed checks, comparator identity, anomaly disposition and source conflicts; for a kernel trial audit, a source-bound interpretation separating artifact/cohort identity, origin, oracle, performance resolution and selected-versus-delivered eligibility, without promoting kernel parity into a gain or whole-model acceptance; for the NInfer slice, a source-bound validation plan or report interpretation that separates state-oracle evidence, final adoption, retirement and workload denominators; for VLA reports, a timing/denominator and precision reconciliation with per-task quality/completion accounting and source-artifact limits; for GPU attribution, a source-grounded measurement plan or interpretation binding environment, paired timing, work counts, predicted signature and E2E decomposition with explicit assumptions and unresolved evidence",
        "failure_modes": [
          "Raw throughput is optimized in place of goodput, so requests served outside the SLO count toward a win",
          "One concurrency level or one undisclosed aggregate score stands in for all required regimes",
          "Recorded agent task scores or replay completion are read as current task success, or a VBench prompt workload as computed VBench quality",
          "An upstream better/worse/inconclusive label is used as InferRSI's PASS/FAIL/INCONCLUSIVE verdict",
          "Runs on the same hardware class, in different time windows or on shared devices are compared as if pinned",
          "A quality pass is taken to certify that the timed work actually occurred",
          "Best-seen results are reported as delivered without restarting and validating the final code/config artifact",
          "A cache-aware ASR EOU is treated as EOF or full reset, nominal chunk duration as the decoded mel frontier, or shape-only geometry PASS as a native model-state test",
          "An enabled treatment or stored feedback summary is taken as proof of delivery to the next eligible consumer",
          "A failed arm-validity condition is overridden by a favorable best timing or a saturation/null interpretation",
          "Complete gate keys or zero recorded failures are read as proof that every declared protocol check ran",
          "A tool-origin measured marker or completed status is treated as a resolved performance gain",
          "A displayed/manual best, baseline copy or edited candidate is reported as the eligible measured delivery",
          "Ratio omission alone is assumed to clear an earlier ratio, or baseline agreement is treated as independent semantic correctness",
          "Zero accepted drafts is treated as zero adopted input, or a matching token prefix is used to splice unrelated State and KV checkpoints",
          "ResultReady or a commit receipt is treated as DeviceRetired, or selected full-batch intervals are compared with complete-cohort rates under one unlabeled denominator",
          "Generated-action amortization is read as action-response latency or actual control frequency",
          "Matching structural pair fields are taken to certify matched effective compute precision or quality equivalence",
          "An aggregate VLA success rate conceals task-specific losses or missing/skipped episodes",
          "A public current script, recorded experiment revision or binary hash is treated as the exact measured dirty source patch",
          "Whole-device fallback memory is relabelled as process-attributed memory or compared with simulator-inclusive/allocator quantities",
          "NCU replay durations are substituted for normal E2E evidence, or an untouched region is treated as a universal clock without checking common drift and critical-path assumptions",
          "Unexplained gains, changed baseline modes or same-named JIT loads are adopted without binding actual work, module identity and predicted profiler signatures"
        ],
        "refusal_point": "Records missing coverage and high-variance results as INCONCLUSIVE rather than a win; a run without a frozen RunSpec, or whose validator changed after the plan was frozen, is INCONCLUSIVE regardless of metric values; sets no universal numeric gate or noise threshold; withholds causal treatment benefit/null conclusions when required delivery or arm eligibility is unverified, and preserves conflicts between stated protocol, exported code and source reports; withholds a kernel gain for unresolved performance or an unbound comparison and identifies missing independent semantic evidence when only baseline agreement is available; withholds native state-correctness and cancellation/reuse conclusions when the required same-block oracle, checkpoint identity or matching receipt is missing; withholds VLA quality-preservation, runtime-only attribution, control-rate or current-build conclusions when their required precision, per-task, timestamp or measured-source evidence is missing"
      },
      "recommendations": [
        "Freeze one primary objective, timing boundary, quality gates and sample/failure accounting before optimization.",
        "Choose the required regimes from the deployment use case, report each separately, and record which must improve or must not regress in a versioned decision config.",
        "Use the replay trace that matches the actual deployment pattern.",
        "State the concurrency, trace, model, SKU and microbenchmark scope boundaries in any report that cites benchmark results.",
        "Trace treatment to its eligible consumer and apply the frozen arm-validity precedence before attributing benefit, saturation or a null.",
        "Bind the complete saved candidate and comparator cohort; keep result origin, actual oracle, named gate/ratio and delivered eligibility separate.",
        "For hybrid speculative comparisons, freeze the coupled restore point, same-physical-block oracle, zero-draft/zero-adoption controls and complete-cohort versus steady-phase denominators before interpreting a result.",
        "Separate complete VLA request cost, generated/replayed action denominators and actual control cadence; retain per-task quality and measured-source/precision limits.",
        "For GPU comparisons, retain timestamped clocks/temperature/power, same-run region shares and work counts; test the predicted mechanism signature and paired E2E change before adopting a gain."
      ],
      "limitations": [
        "Source-derived candidate; no local efficacy validation.",
        "Original typed source inventory is not normalized; retain source identities and limits in the procedure/readsets.",
        "Task benchmark knowledge is distilled from issue #60 with selected pinned-source rechecks; no all-task runtime qualification or optimization benefit is established.",
        "Benchmark feasibility and package-consumption checks do not promote this candidate or replace task quality, repeated A/B and service qualification.",
        "The pinned NeMo-Speech.cpp ASR reference covers selected source/test definitions and author-reported benchmark boundaries; native model/device, decoder internals, quality, long-audio/load and service behavior remain not_run.",
        "JustGoal contributes source-only controlled-evaluation and kernel-acceptance guidance; its repaired/retested timings, released-pass counts and protocol differences are author-reported, not locally reproduced or a complete campaign runner.",
        "The AutoTuneBench reference is source-only: original operational checkpoint/prompt receipts remain unavailable, source contradictions remain explicit, and no tuning, device/performance or agent-efficacy validation was run.",
        "The Xe-Forge reference is source-only and limited to inspected host/manual/Claude trial paths; named-verdict update predicates and caller defaults remain explicit. Native tests, backend/model/quality/performance/service behavior and agent efficacy were not evaluated, and source/package checks do not promote whole-model support.",
        "The NInfer reference inspects selected Qwen3.5 GDN/MTP source contracts and unexecuted test definitions; its historical author measurements use a different engine revision. Native state/model/device/quality/performance and efficacy remain unvalidated.",
        "The Faster CosyVoice reference is source-only: server route credit and client simulated playback remain distinct, reported costs/quality retain their boundaries, overall source rights are UNKNOWN, and native/model/device/audio quality/service/performance are not_run with efficacy not_evaluated.",
        "The Embodied.cpp reference is source-derived: its public latency arrays allow arithmetic audit, but raw episode recount, exact measured script/dirty patch, effective dispatch and current model/device/service or efficacy qualification remain unresolved.",
        "The GPU measurement-validity reference is source-only. The within-run normalization and explanation-first adoption procedure is an unverified author proposal; four task-supplied numerical observations have no supplied raw evidence. GPU/profiler, model/quality, L1–L4 and efficacy validation were not run; legacy metric mappings require target-specific queries."
      ],
      "provenance_readsets": [
        "references/task-benchmark-selection.md",
        "references/benchmark-commands.md",
        "references/cache-aware-asr-stream-boundaries.md",
        "references/justgoal-evaluation-contracts.md",
        "references/justgoal-source.json",
        "references/autotunebench-trial-validity.md",
        "references/autotunebench-source.json",
        "references/xeforge-trial-evidence.md",
        "references/xeforge-source.json",
        "references/ninfer-state-and-completion-contracts.md",
        "references/ninfer-source.json",
        "references/dependency-aware-tts-playout.md",
        "references/faster-cosyvoice-source.json",
        "references/embodied-cpp-boundary-and-quality.md",
        "references/embodied-cpp-source.json",
        "references/gpu-measurement-validity.md"
      ],
      "references": [
        "../../../casebooks/inference/inference-optimization-casebook/cases/admission-drain-occupancy.md",
        "../../../casebooks/inference/inference-optimization-casebook/cases/admission-drain-occupancy.json",
        "../../../systems/engines/deepinfer/budget-speculative-verification/SKILL.md",
        "../../../systems/engines/vllm-rlt/audit-recurrent-kv-finalization/SKILL.md"
      ],
      "consumption_mode": "packaged",
      "searchspace_not_applicable": "SKILL.md §§ Select the task and its evaluation contract, Statistical requirements, Shared-machine measurement discipline, and Search integrity and final-state verification design comparable evaluation; hardware identity and allocation isolation are comparison controls, not a hardware-resource mechanism."
    }
---

# Inference Benchmark Design

Status: candidate. Source-grounded from vllm-evolve @ 43cc82c and
InferRSI evidence framework @ 4c8e1285.

## Select the task and its evaluation contract

Read [task-specific benchmark selection](references/task-benchmark-selection.md)
when choosing quality evaluators, reference parity and a performance workload.
It covers text, agent replay, TTS, three full-duplex task families, images and
videos, with pinned provenance from InferRSI issue #60. Use the
[command templates](references/benchmark-commands.md) for entry points and a
bounded HTTP smoke. These references are candidate knowledge, not qualification
of every model or backend.

For cache-aware speech recognition, read the
[ASR stream-boundary procedure](references/cache-aware-asr-stream-boundaries.md)
before selecting tests or comparing chunk latency. It separates startup/steady geometry, decoded
progress, stream-slot reuse, reset, EOU and EOF; its source tests and
author benchmark reports are not local model or serving qualification.

For streaming TTS measurements tied to playback deadlines or dependent chunks,
read [dependency-aware TTS playout](references/dependency-aware-tts-playout.md).
It traces server PCM credit, client playback events, independent batching work
and partial pipeline costs at one pinned source; it adds no hardware coverage,
runtime or locally reproduced quality/performance result.

For VLA and robot deployment comparisons, read
[observation-to-action timing and closed-loop quality](references/embodied-cpp-boundary-and-quality.md).
Define the complete CPU-action boundary, distinguish generated and replayed
horizons from the control clock, and reconcile per-task quality, precision and
the measured source revision. Freeze latency/jitter and quality objectives for
the actual control use case; per-generated-action cost is amortization.

For treatment-enabled tuning comparisons or claimed protocol integrity, read
[treatment delivery and trial validity](references/autotunebench-trial-validity.md).
Trace feedback to the eligible consumer input and apply the frozen arm-validity
precedence before interpreting benefit, saturation or a null.

For GPU timing comparisons, read
[measurement validity and profiler attribution](references/gpu-measurement-validity.md).
Separate normal E2E timing from profiler replay, test within-run attribution
assumptions and retain work counts plus the predicted mechanism signature.
This is candidate guidance; its task-supplied observations remain unverified.

For hybrid speculative state-restoration or completion evidence, read the
[NInfer validation contract](references/ninfer-state-and-completion-contracts.md).
Freeze a coupled checkpoint and same-physical-block state oracle; distinguish
zero accepted drafts from zero adopted inputs, logical commit from device
retirement, and selected steady intervals from complete-cohort denominators.
Its source contracts and historical author reports are not native parity results.

Freeze one primary objective, timing boundary, quality gates and sample/failure
accounting before optimization. Recorded agent task scores and replay completion
do not establish current task success; a VBench prompt workload does not compute
VBench quality. Missing coverage stays INCONCLUSIVE. Numeric gates and required
workload regimes are campaign choices, not repository-wide defaults.

## Core principle: goodput over throughput

Raw throughput (tokens/second, frames/second) is misleading because a system
can maximize throughput by accepting requests it then fails to serve within
the user's latency expectation. The meaningful metric is goodput: the rate of
requests that complete AND meet the declared SLO.

```
goodput = (requests completed within SLO) / time
```

A candidate that improves raw throughput by trading latency away cannot "win"
under a goodput metric if it causes SLO violations.
Source: vllm-evolve README @ 43cc82c.

## Workload regimes to select for the campaign

A single benchmark run at one concurrency level does not characterize serving
performance. These source-derived regimes answer different questions; choose
the required set from the deployment use case and freeze it before comparison:

| Regime | Load level | What it answers |
|--------|-----------|----------------|
| Throughput | Saturating load, with observed bottleneck and queue state | Max sustainable goodput at peak load |
| Latency | Low load | Responsiveness for latency-sensitive workloads |
| Replay | Real or representative trace | Behavior under actual production burstiness |

An optimization may improve one regime while degrading another. Report all
required regimes separately; do not aggregate into a single score without disclosing
how the aggregation was done.

For replay, standard trace sources (from vllm-evolve): BurstGPT, Azure,
ShareGPT, Mooncake. Use the trace that matches your actual deployment pattern.

## Verdict semantics

The upstream vllm-evolve comparison labels are:

| Verdict | Condition |
|---------|----------|
| better | Improvement in all required regimes, no regression in any |
| worse | Regression in any required regime |
| inconclusive | Too noisy to distinguish (see below) |

These labels are not InferRSI's verdict enum. InferRSI uses PASS / FAIL /
INCONCLUSIVE and the campaign's frozen gates. `high_variance_inconclusive`
is a useful diagnostic reason: it means the
measurement signal is not strong enough to support a claim in either direction.
Do not report an inconclusive result as a win. Record it as INCONCLUSIVE and
note the variance level.
Source: vllm-evolve README @ 43cc82c.

## Statistical requirements

Freeze repetition count, workload seeds and the decision rule in the campaign.
The upstream guidance recommends multiple seeds and median goodput with IQR or
range. State whether a repetition changes the workload seed or repeats identical
inputs. If using `max - min > threshold × median` as a noise gate, choose the
threshold in the acceptance plan; this skill defines no universal numeric bar.
InferRSI's built-in median/range summaries are descriptive, not a significance
test or automatic enforcement of that noise gate.

The decision of which regimes must improve and which must not regress is the
caller's policy, not the benchmark's. Encode it in a decision config file
(`decision.yaml` in vllm-evolve) so it is explicit, versioned, and auditable.

## Audit a supplied fixed-workload report

Preserve the request-to-trial grouping and every observation covered by the
contract. Late requests and outliers remain included unless the frozen protocol
explicitly excludes them; retain exclusion and failure counts. Apply aggregation
in the declared order: a median of per-trial request means uses every included
request to calculate each trial mean, then takes the median across trials. A
pooled request median is a different statistic, especially with unequal trial
sizes. If the report omits an aggregation rule that changes the verdict, expose
that ambiguity rather than choosing one after seeing the result.

For a lower-is-better metric with a positive baseline, calculate percentage
reduction as `100 * (baseline - candidate) / baseline` and compare it with the
declared threshold before rounding. Check workload equivalence, output quality
and completion evidence separately from this arithmetic. Report the computed
threshold result and any missing evidence under the frozen contract's verdict
semantics; an attractive aggregate alone does not establish an accepted gain.

## What must be pinned before comparing two runs

Every valid A/B comparison requires these to be identical:
- Hardware (exact device SKU, driver version, firmware).
- Software stack (framework version, model weights revision).
- Input distribution (same trace or same generation config and seed).
- Benchmark configuration (concurrency levels, SLO thresholds, timeout).
- Warmup (same warmup protocol, excluded from measurement).
- Measurement protocol (same window duration, same number of seeds).

If any of these differ between the baseline and candidate run, the comparison
is invalid. "Same hardware class" is not the same as "same device."

## Shared-machine measurement discipline

On shared infrastructure (multiple users, shared GPU/NPU allocation):

- Cross-window comparison is invalid. Run baseline and candidate within the
  same time window (interleaved or back-to-back in the same allocation).
- Record neighbor load state before each run. If it changes between runs,
  report the comparison as potentially confounded.
- Dedicate devices: do not share GPU devices between the baseline server and
  the candidate server in the same comparison run.

Source: MindIE-SD perf-gate skill @ 8481d39b (window discipline for NPU).

## What a benchmark cannot prove

- A benchmark win at one concurrency level does not imply a win at other
  concurrency levels.
- A benchmark win with synthetic traces does not imply a win under real
  production traffic.
- A benchmark win on one model does not transfer to other models without
  re-running.
- A benchmark win on one hardware SKU does not transfer to other SKUs.
- Microbenchmark improvement does not imply E2E benchmark improvement.

State these scope boundaries explicitly in any report that cites benchmark
results.

## Search integrity and final-state verification

Freeze workload hashes, output/work semantics, permitted approximations, quality
checks, timing events and developer-versus-held-out splits. Verify that measured
work actually occurs; a quality pass does not certify a truthful timing path.
Keep fast probes separate from full evaluation, and preserve invalid, failed and
inconclusive trials. A simulator shortlist requires calibrated load/capacity
coverage and does not replace measurements.

Compare search methods at matched total budgets. Separate search/API cost from
steady-state serving cost; independent per-engine searches are not one equal-budget
engine-selection run. Keep different SLOs, baselines, resources and aggregation
rules explicit. Before reporting, restart the final code/config artifact and
validate that exact state; report best-seen results separately from delivered ones.

[Reviewed experiment discipline](../performance-ceiling-analysis/references/papers-20261015/govern-optimization-experiments/procedure.md)
and [source audit](../performance-ceiling-analysis/references/papers-20261015/references/inferencebench.md)
retain author-reported evidence and counterexamples. No local experiment is
established by integrating these notes.

For controlled kernel-agent comparisons, use the
[JustGoal source reference](references/justgoal-evaluation-contracts.md).
Keep model/budget/task scope, independent acceptance, released versus repaired
artifacts and workspace/stream/cache contracts explicit. Its results remain
author-reported; it adds no runner or device/performance qualification.

For source-bound kernel trial records, read
[trial identity, evaluator evidence and candidate selection](references/xeforge-trial-evidence.md).
Keep tool origin, actual oracle, unresolved performance, selection and delivered
eligibility distinct; a retained parity candidate is not a measured gain.

## Evidence trail requirements (InferRSI compatibility)

A benchmark campaign that claims PASS under InferRSI's evidence framework
must produce:
```
evidence/<campaign-id>/
  plan/
    hypothesis.md         # what is being tested and why
    runspec.json          # frozen RunSpec (repo × revision × backend × device × model × scenario)
    slo.yaml              # declared SLO and threshold
    decision.yaml         # which regimes must improve / must not regress
  results/
    regime-throughput/    # raw metrics, logs, per-seed records
    regime-latency/
    regime-replay/
    verdict.json          # PASS / FAIL / INCONCLUSIVE with reasons
  patch/
    candidate.patch       # the exact change being evaluated
  validator/
    validate.py           # frozen validator script
```

A run without a frozen RunSpec is INCONCLUSIVE regardless of the metric values.
A run whose validator was modified after the plan was frozen is INCONCLUSIVE.
Source: InferRSI AGENTS.md and rsi-evidence skill @ 4c8e1285.

## Scoped internal experience

Read the single authoritative [admission/drain occupancy case](../../../casebooks/inference/inference-optimization-casebook/cases/admission-drain-occupancy.md) when interpreting finite service cohorts. It separates recorded observation, action and interpretation; phase-selected occupancy is not end-to-end gain. The original frozen evidence remains linked, not copied. This shared reference is included in the packaged skill library; standalone folder export is not supported.
