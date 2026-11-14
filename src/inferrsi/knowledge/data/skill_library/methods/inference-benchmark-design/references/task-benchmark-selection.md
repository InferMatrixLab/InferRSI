# Select benchmarks by task

Knowledge distilled from [InferRSI issue #60][issue] and its
[source-reviewed report][report] (research date: 2026-10-21). This is candidate
guidance, not a benchmark ranking or a claim of local quality/performance
qualification. The source snapshots below describe specific versions; confirm
interfaces at the version used by a campaign.

Use this reference when choosing the evaluator, workload and objective for a
campaign. Read [command templates](benchmark-commands.md) for entry points.

## 1. Freeze three separate contracts

| Contract | Question answered | What to freeze |
| --- | --- | --- |
| Task quality / behavior | Does the model perform the intended task? | Dataset revision, split and sample IDs; prompt/chat template; generation budget; evaluator, judge and normalization; thresholds and failure accounting |
| Reference parity | Does the candidate preserve the intended reference behavior? | Reference implementation and outputs; seed, shapes, precision, output format and allowed deviation |
| Performance workload | Does the service meet the intended workload efficiently? | Arrival process or concurrency, session topology, context/output distributions, warmup, cache state, timing boundaries, measurement window and SLOs |

Declare the use case, non-goals, isolated variable and stop condition. Select one
primary metric and its unit, direction and statistic; keep other measurements as
gates or diagnostics. Freeze numeric bars in the acceptance issue and campaign
plan before searching. Research source pins in this reference are provenance,
not baseline/candidate defaults.

Task quality and parity are not interchangeable. Exact matching is often too
strict for independently sampled text; task correctness remains necessary.
SSIM/PSNR/LPIPS against reference media cannot establish instruction following
or video temporal quality. Conversely, a task score cannot certify that a timer
measured the declared work. [Accuracy helpers][vo-accuracy], [diffusion tests][sg-diff-test-utils]

## 2. Task matrix

| Task / use case | Quality and behavior gate | Performance runner / workload | Candidate primary objective |
| --- | --- | --- | --- |
| Text generation | GSM8K, MMLU, GPQA or code execution accuracy; select one protocol matching the use case. AIPerf also has accuracy evaluators. | `vllm bench serve`, `sglang.benchmark.serving`, or `aiperf profile` with frozen lengths/load | TTFT, TPOT or E2E tail down; SLO goodput up |
| Agentic coding | Execute live coding tasks in their original environment with a grader | AIPerf AgentX MVP, WEKA/TraceLab, synthetic coding traces or Exgentic SWE-bench replay | Request TTFT/ITL down or goodput up with a fixed session tree |
| Work / general-purpose agents | Re-run the original task evaluator for task success | Exgentic v2 AppWorld/BrowseCompPlus/τ²-bench; H CUA Perf desktop/screenshot replay | Request latency down or goodput up with fixed tool/context/wait distributions |
| TTS / voice cloning | Seed-TTS WER/CER, reference-speaker SIM when applicable, UTMOS; same evaluator for both sides | vLLM-Omni TTS serving or SGLang-Omni SeedTTS/serving harness | First playable audio latency or RTF down; audio seconds/s up, with underrun limits |
| Full-duplex audio/video interaction | OmniInteract IA-QTF1, interruption diagnostics and nested recovery NCCS | vLLM-Omni realtime serving, `--dataset-name omniinteract` | IA-QTF1/NCCS up, or per-response TTFP tail down subject to interaction gates |
| Real-time description / proactive reminders | Omni-DuplexEval RTD content/temporal scores; PR all-success, scored separately | vLLM-Omni realtime serving, `--dataset-name omni-duplex-eval` | One RTD/PR score up, with timing, coverage and error constraints |
| Full-duplex speech / capacity | Full-Duplex-Bench v1.0/v1.5: pauses, turn-taking, interruption, overlap | SGLang-Omni FDB pipeline and concurrent duplex serving sweep | Response/stop latency or unit deadline misses down; concurrency meeting frozen targets up |
| Image generation / editing | Reference parity plus task quality: general T2I, GUI or editing need different suites | vLLM-Omni or SGLang Diffusion serving; offline throughput for diagnosis | Delivered-image E2E down or images/s up |
| Video generation | Decoded-frame parity and a separately executed temporal-quality suite such as VBench | vLLM-Omni or SGLang Diffusion serving with matched delivery boundaries | Delivered-video E2E down; videos/s or generated frames/s up |

Sources: [vLLM][vllm-bench-doc], [SGLang][sg-eval-doc],
[AIPerf accuracy][ai-accuracy], [AgentX][ai-agentx], [agent datasets][ai-datasets],
[CUA][ai-cua], [TTS][vo-tts-doc], [SGLang-Omni TTS][so-readme],
[OmniInteract][oi-eval-doc], [Omni-DuplexEval][ode-readme],
[realtime integration][vo-bench-serve-doc], [FDB][so-fdb-doc],
[image accuracy][vo-accuracy], [diffusion serving][sg-diff-doc].

## 3. Choose the evaluator, not just a dataset name

### Text and agents

GSM8K requires answer extraction/scoring, not just sending math prompts. Freeze
shots, CoT/reasoning budget, chat versus completions, answer extraction and sample
count. Code generation accuracy requires executing the test cases. AIPerf's
`--accuracy-benchmark` supports tasks including GSM8K, MMLU, GPQA and LiveCodeBench;
retain both aggregate results and per-example exports. Its `unparsed` count
describes parsing/fallback behavior, not necessarily wrong answers. [Accuracy][ai-accuracy]

AgentX is selected by `--scenario inferencex-agentx-mvp`, which uses the
`agentic_replay` timing mode. WEKA is a trace format; it is not an alias for a
compliant AgentX run. Inspect scenario settings, `submission_valid`, branch
statistics, output-length compliance, context overflow and truncation. These
establish workload properties, not coding task success. [AgentX][ai-agentx]

WEKA reconstructs synthetic prompts from hash IDs; TraceLab reconstructs workload
shape without the original prompt/response text. Synthetic coding generators
validate distributions, not code correctness. Exgentic trace `success/score`
fields belong to the original recorded execution. Replay of its SWE-bench,
AppWorld, BrowseCompPlus or τ²-bench requests does not rerun the task grader.
H CUA Perf needs a vision-capable endpoint and a frozen screenshot window;
text-only token counts miss visual input. [WEKA][ai-weka], [TraceLab][ai-tracelab],
[synthetic coding][ai-agentic-code], [Exgentic][ai-exgentic-v2], [CUA][ai-cua]

For agent replay, also freeze source model/harness filters, tool schemas,
tokenization, prefix reconstruction, waits and child-session scheduling. Fixed
schedule versus closed-loop replay changes load semantics. A duration-cropped
session fragment is not a complete task, and its latency is not task completion
time. Run live task quality separately from the performance replay.

### TTS and voice cloning

Save generated audio and evaluate both sides with the same ASR checkpoint,
decoding and text normalization. Specify WER versus CER and corpus-micro versus
per-utterance-macro aggregation. At the report's pins, vLLM-Omni's speaker SIM
uses a mean-pooled WavLM proxy; SGLang-Omni uses a speaker-verification model with
a different scale. Rescaling alone does not make them equivalent. [Seed-TTS
evaluator][vo-seed-eval], [WER][so-wer], [SIM][so-sim]

In the pinned vLLM-Omni evaluator, explicitly enable `SEED_TTS_SIM_EVAL=1` and
`SEED_TTS_UTMOS_EVAL=1` when those gates are required. Check actual evaluated
counts and raw JSON keys: the TTS wrapper's console summary uses some legacy
names. Empty or skipped evaluations must not become a successful zero WER.
[Wrapper][vo-tts], [evaluator][vo-seed-eval]

Freeze sample rate, channels, sample width and codec. Time the first playable
audio payload, not HTTP headers or an empty SSE event. Non-streaming complete
WAV delivery has a different first-audio boundary. Report audio duration and
underruns alongside latency. [Audio metrics][so-perf]

### Full-duplex interaction

Do not replace continuous input with a whole-video prompt: the model must not
receive future input early. Preserve input pacing, output/playback clocks,
native versus server-VAD protocol, system prompt, voice reference, ASR/aligner
and judge. Session duration includes input and drain; it is not pure generation
compute. These suites cover distinct behaviors:

| Suite | Score interpretation | Failure / coverage trap |
| --- | --- | --- |
| OmniInteract | IA-QTF1 combines quality, timeliness, missed responses and invalid outputs. NCCS checks answering the inner question then recovering the outer task. | Recompute aggregate F1 from aggregate soft TP/FP/FN. High NOR can mean silence. CSM spill uses interrupted slots with output, not all interruption cases. Keep sampled/completed/eligible/evaluated counts. |
| Omni-DuplexEval | RTD content/temporal scores are judge scores, not milliseconds. PR all-success requires every event in a sample to pass. | Keep RTD and PR separate; report relevant/error counts. Freeze time windows, text versus vision judge and frame-sample versus video-url mode. Upstream scores response JSON; the integration supplies generation. |
| Full-Duplex-Bench | v1.0 turn-taking and v1.5 paired overlap/clean behavior need separate tables. True interruptions and backchannels require different responses. | Low takeover can mean silence. Check interruption exercised rate, missed responses, judge coverage, underruns and input pacing. Official and unified metrics are different protocols; do not attribute v2/v3 coverage to the pinned v1.0/v1.5 runner. |

Sources: [OmniInteract computation][oi-compute] and [aggregation][oi-summary],
[Omni-DuplexEval][ode-readme], [realtime scoring eligibility][vo-bench-serve-doc],
[FDB runbook][so-fdb-doc] and [unified metrics][so-fdb-metrics].

Client payload arrival, simulated playback and physical speaker output are
different events. Native response TTFP, stream-origin TTFP and last-input-append
TTFP have different start clocks. SGLang-Omni unit lag starts at the last input
packet for that unit; it cannot be compared directly with a model-turn timer.
If every tested concurrency passes, capacity is a lower bound, not a measured
maximum. [Duplex timing][vo-duplex-metrics], [serving sweep][so-duplex-serving]

### Images and videos

For lossless optimizations, begin with model-specific parity. For approximation,
quantization or fewer denoising steps, add task quality. GEBench in the pinned
vLLM-Omni integration is a GUI benchmark, not GenEval; GEdit-Bench assesses image
editing. General T2I may require an external suite such as GenEval. SGLang's
golden image-image CLIP cosine is not prompt-image CLIPScore. [Image evaluation][vo-accuracy],
[GUI suite][vo-gebench], [editing suite][vo-gedit], [golden tests][sg-diff-test-utils]

Compare decoded video frames and metadata (frame count, FPS, size and duration),
not encoded-file identity alone. Frame SSIM/PSNR or LPIPS does not fully assess
motion, temporal consistency or prompt alignment. `--dataset vbench` in a
performance runner selects workload inputs; it does not run VBench quality
evaluation. Run the chosen VBench dimensions separately with frozen evaluator
and dataset versions. [Video parity][vo-wan-video], [diffusion workload][sg-diff-doc],
[external VBench evaluator][vbench-evaluate]

## 4. Normalize metric meaning before extracting a number

| Metric / boundary | Definition and comparison rule |
| --- | --- |
| TTFT / TTFO | First token can be a reasoning token; first user-visible output can occur later. State which event is measured. |
| TPOT / ITL / ICL | TPOT is commonly `(request latency - TTFT) / (output tokens - 1)` for multi-token responses. ITL aggregation and chunk handling differ across tools; an SSE chunk interval is not necessarily a token interval. Retain sample counts and token timing assumptions. |
| Goodput / attainment | Goodput is successful requests meeting the frozen SLO per wall-clock second. Attainment is a fraction with a declared denominator. Neither is raw throughput. |
| Audio RTF / throughput | Per-request RTF = generation elapsed seconds / audio seconds. Aggregate audio throughput = successful audio seconds / measurement-window seconds. Under concurrency, inverse mean RTF is not aggregate throughput. |
| Requests/s / outputs/s | A request may produce several images/videos; preserve output count, frames and duration. Lower work is not a speedup. |
| Offline wall time / latency | Total wall time divided by completed requests under concurrency is not the distribution of individual request latency. |
| Video job-complete | Time until the client observes completion, including polling; excludes media delivery if content is not fetched. |
| Video media-delivered | Time until complete media bytes reach the client; freeze content transfer and polling policy. |
| Engine compute | Server stage timers; useful for diagnosis but not a replacement for client E2E. |

Sources: [vLLM metrics][vllm-bench-doc], [SGLang metrics][sg-bench-doc],
[AIPerf metrics][ai-metrics] and [ITL implementation][ai-itl],
[audio formulas][so-perf], [offline diffusion][sg-diff-offline].

At the report's pins, vLLM-Omni video polling includes fetching `/content`, while
SGLang Diffusion stops when the job is observed complete; their polling intervals
also differ. Do not compare those default `latency` fields as one delivery
metric. Use a common client/boundary. Freeze SLO deadlines before A/B: deriving a
new deadline from each candidate's warmup can hide regression.
[vLLM-Omni backend][vo-diff-backends], [SGLang backend][sg-diff-serving]

Record expected, attempted, completed, evaluated, failed, timed-out and excluded
counts with reasons. Successful-request-only latency must be accompanied by
failure accounting. Missing quality, zero eligible samples, missing timings or
unqualified environments are evidence gaps, not wins. Distinguish a completed
gate rejection (`FAIL`) from missing required evidence (`INCONCLUSIVE`). Zero or
absent peak-memory telemetry means unknown when the backend did not report it.

## 5. Connect to InferRSI without claiming a new adapter

The existing [benchmark contract][rsi-quickstart] accepts JSON at `{result}` or
`INFERRSI_RESULT_PATH`, one flat/dotted `--metric-key`, its unit and direction,
and a separate `--validation-command`. It does not automatically select these
suites, enforce all SLOs or calculate their quality scores.

| Native output | Objective extraction example | Required handling |
| --- | --- | --- |
| vLLM text JSON | `median_ttft_ms` (ms, minimize), `request_goodput` (requests/s, maximize) | Configure SLOs for goodput; retain raw results and success counts. |
| SGLang text JSONL | `median_ttft_ms`, `p99_ttft_ms` | Select exactly the current run; do not silently take an old appended object. |
| AIPerf exports | The chosen statistic of `time_to_first_token`, `request_latency` or `goodput` | Inspect `profile_export_aiperf.json`; normalize the metric/statistic/unit explicitly. Keep per-request `profile_export.jsonl`. |
| vLLM-Omni TTS | `median_audio_ttfp_ms`, `mean_audio_rtf`, `audio_throughput` | Check the revision's fields and audio accounting; quality is a separate gate. |
| SGLang-Omni TTS | `summary.audio_ttfp_p95_s`, `summary.audio_throughput_s_per_s` | Read `speed_results.json` alongside saved audio and quality results. |
| vLLM-Omni duplex | `p99_duplex_response_ttfp_ms` | Require eligible response timing; preserve per-session/per-response records. |
| SGLang-Omni duplex | A selected level's `unit_lag_s.p99`, or `max_concurrency_meeting_targets` | Select a fixed concurrency/profile; array wildcards are not InferRSI dotted paths. Preserve capacity-bounded status. |
| Diffusion serving | `latency_p95` (s), `throughput_qps` (requests/s) | Align media delivery boundaries; use output throughput for multiple outputs/request. |

Sources: [text output][vllm-serve], [SGLang output][sg-serving],
[AIPerf exports][ai-exports], [Omni metrics][vo-metrics], [audio output][so-perf],
[duplex sweep][so-duplex-serving], [diffusion output][vo-diff-serving].

The current [metric reader][rsi-metrics] requires a **finite, strictly positive
number**, rejecting zero, booleans and missing/non-numeric values. A legitimate
zero quality score is allowed in an external quality report, but not as this
runner's objective. Do not add epsilon, fabricate timings or silently omit failed
runs to satisfy the parser. Choose a suitable positive performance objective and
keep quality scores in validation, or explicitly scope a future runtime change.

The supplied quality command should verify frozen thresholds, units, sample
coverage and output integrity, write a report and exit nonzero on rejection.
InferRSI only observes its exit status; exit zero proves nothing outside that
command's coverage. A 0.80 to 0.79 accuracy drop is one percentage point; define
absolute versus relative tolerances explicitly. Keep judges/profilers outside
the measured performance window. [Evaluation contract][rsi-evaluation]

Baseline and candidate trial scripts own startup, readiness, warmup, measured
work, raw output retention and cleanup. `--candidate-repo` changes the working
directory; `--python` does not automatically change the executable used inside
the commands. Pin and invoke the intended interpreter in each script. Run the
smallest feasibility check first; full quality, repeated A/B and service SLO
qualification remain separately scoped campaign work.

## Provenance and validation limits

The original report reviewed vLLM, SGLang, AIPerf, vLLM-Omni, SGLang-Omni,
InferRSI, OmniInteract and Omni-DuplexEval source snapshots. Its complete readset
is preserved in the issue comment. This extraction rechecked the pinned AIPerf
accuracy/AgentX/datasets/CUA docs, vLLM-Omni realtime guide and video backend,
SGLang-Omni FDB guide and SGLang video backend. Other upstream details retain
the report's attribution rather than claiming a new full audit. The current
InferRSI contract was also checked against its source.

The typed source inventory in `metadata.json` identifies the retained readset.
The external VBench link is a locator with an unpinned revision; pin it before
an experiment. This reference adds no hardware qualification or efficacy claim.
Any accompanying local smoke validates only its recorded path, not all nine
task families, evaluator correctness or an optimization benefit.

[issue]: https://github.com/InferMatrixLab/InferRSI/issues/60
[report]: https://github.com/InferMatrixLab/InferRSI/issues/60#issuecomment-6310920198
[vo-accuracy]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/benchmarks/accuracy/README.md
[sg-diff-test-utils]: https://github.com/sgl-project/sglang/blob/844d2b5decf6257aa192744cbdaaffb8ad797263/python/sglang/multimodal_gen/test/test_utils.py
[vllm-bench-doc]: https://github.com/vllm-project/vllm/blob/a9bf45ed8a856a0b1839197152d0d26fabb6599c/docs/benchmarking/cli.md
[sg-eval-doc]: https://github.com/sgl-project/sglang/blob/844d2b5decf6257aa192744cbdaaffb8ad797263/docs/docs/developer_guide/evaluating_new_models.mdx
[ai-accuracy]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/accuracy/accuracy-benchmarking.md
[ai-agentx]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/tutorials/agentx-mvp.md
[ai-datasets]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/benchmark-datasets.md
[ai-cua]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/tutorials/h-cua-perf.md
[vo-tts-doc]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/benchmarks/tts/README.md
[so-readme]: https://github.com/sgl-project/sglang-omni/blob/f31cf9e9af749040ffa6dbdf064882c443a2fd37/benchmarks/README.md
[oi-eval-doc]: https://github.com/Lucky-Lance/OmniInteract/blob/de304cef35fd9a50a5caadb5090c34cfbf0dd868/eval/README.md
[ode-readme]: https://github.com/OpenBMB/Omni-DuplexEval/blob/962cec448ac37a377ffb963b476778777d11d346/README.md
[vo-bench-serve-doc]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/docs/cli/bench/serve.md
[so-fdb-doc]: https://github.com/sgl-project/sglang-omni/blob/f31cf9e9af749040ffa6dbdf064882c443a2fd37/docs/developer_reference/full_duplex_bench.md
[sg-diff-doc]: https://github.com/sgl-project/sglang/blob/844d2b5decf6257aa192744cbdaaffb8ad797263/docs/cookbook/base/benchmarks/diffusion_model_benchmark.mdx
[ai-weka]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/tutorials/weka-trace.md
[ai-tracelab]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/tutorials/tracelab-trace.md
[ai-agentic-code]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/tutorials/agentic-code-generator.md
[ai-exgentic-v2]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/src/aiperf/dataset/loader/exgentic_v2.py
[vo-seed-eval]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/vllm_omni/benchmarks/data_modules/seed_tts_eval.py
[so-wer]: https://github.com/sgl-project/sglang-omni/blob/f31cf9e9af749040ffa6dbdf064882c443a2fd37/benchmarks/metrics/wer.py
[so-sim]: https://github.com/sgl-project/sglang-omni/blob/f31cf9e9af749040ffa6dbdf064882c443a2fd37/benchmarks/metrics/speaker_similarity.py
[vo-tts]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/benchmarks/tts/bench_tts.py
[so-perf]: https://github.com/sgl-project/sglang-omni/blob/f31cf9e9af749040ffa6dbdf064882c443a2fd37/benchmarks/metrics/performance.py
[oi-compute]: https://github.com/Lucky-Lance/OmniInteract/blob/de304cef35fd9a50a5caadb5090c34cfbf0dd868/eval/evaluation/compute_unified_eval.py
[oi-summary]: https://github.com/Lucky-Lance/OmniInteract/blob/de304cef35fd9a50a5caadb5090c34cfbf0dd868/eval/evaluation/summarize_unified_eval.py
[so-fdb-metrics]: https://github.com/sgl-project/sglang-omni/blob/f31cf9e9af749040ffa6dbdf064882c443a2fd37/docs/developer_reference/full_duplex_metrics.md
[vo-duplex-metrics]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/vllm_omni/benchmarks/duplex_session_metrics.py
[so-duplex-serving]: https://github.com/sgl-project/sglang-omni/blob/f31cf9e9af749040ffa6dbdf064882c443a2fd37/benchmarks/duplex/serving.py
[vo-gebench]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/benchmarks/accuracy/text_to_image/README.md
[vo-gedit]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/benchmarks/accuracy/image_to_image/README.md
[vo-wan-video]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/tests/e2e/accuracy/wan22_i2v/test_wan22_i2v_video_similarity.py
[vbench-evaluate]: https://github.com/Vchitect/VBench/blob/master/evaluate.py
[sg-bench-doc]: https://github.com/sgl-project/sglang/blob/844d2b5decf6257aa192744cbdaaffb8ad797263/docs/docs/developer_guide/bench_serving.mdx
[ai-metrics]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/metrics-reference.md
[ai-itl]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/src/aiperf/metrics/types/inter_token_latency_metric.py
[sg-diff-offline]: https://github.com/sgl-project/sglang/blob/844d2b5decf6257aa192744cbdaaffb8ad797263/python/sglang/multimodal_gen/benchmarks/bench_offline_throughput.py
[vo-diff-backends]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/benchmarks/diffusion/backends.py
[sg-diff-serving]: https://github.com/sgl-project/sglang/blob/844d2b5decf6257aa192744cbdaaffb8ad797263/python/sglang/multimodal_gen/benchmarks/bench_serving.py
[rsi-quickstart]: https://github.com/InferMatrixLab/InferRSI/blob/b3ef95a6dd3abd85c19b5527fe46e80ccb3521d4/docs/quickstart.md
[vllm-serve]: https://github.com/vllm-project/vllm/blob/a9bf45ed8a856a0b1839197152d0d26fabb6599c/vllm/benchmarks/serve.py
[sg-serving]: https://github.com/sgl-project/sglang/blob/844d2b5decf6257aa192744cbdaaffb8ad797263/python/sglang/benchmark/serving.py
[ai-exports]: https://github.com/ai-dynamo/aiperf/blob/30420ce581d4fc9eeb34b4d47defe367ab8c3a11/docs/tutorials/working-with-profile-exports.md
[vo-metrics]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/vllm_omni/benchmarks/metrics/metrics.py
[vo-diff-serving]: https://github.com/vllm-project/vllm-omni/blob/b20e5bac96a029172a59559438ad0590460aeb3c/benchmarks/diffusion/diffusion_benchmark_serving.py
[rsi-metrics]: https://github.com/InferMatrixLab/InferRSI/blob/b3ef95a6dd3abd85c19b5527fe46e80ccb3521d4/src/inferrsi/model/protocols/metrics.py
[rsi-evaluation]: https://github.com/InferMatrixLab/InferRSI/blob/b3ef95a6dd3abd85c19b5527fe46e80ccb3521d4/src/inferrsi/harness/evaluation.py
