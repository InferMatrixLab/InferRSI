# Benchmark entry points and a bounded smoke

Use the [task matrix and metric contracts](task-benchmark-selection.md) first.
These are templates for the source versions linked there, not universal commands
or evidence that all runners were executed. Set variables from the frozen plan;
run from the relevant upstream checkout with its dependencies prepared. Servers,
models, datasets and judges must already be available. Keep raw outputs.

## Text: native HTTP benchmark

For a local feasibility run, set `MODEL_PATH` to a complete local checkpoint,
`MODEL` to the served name, and `GPU_ID` to an available device. Confirm the
model architecture is supported. The following capacity and sample settings
are smoke parameters, not acceptance thresholds. Record preparation and
process-to-readiness separately; stop the owned server when finished.

```bash
CUDA_VISIBLE_DEVICES="$GPU_ID" vllm serve "$MODEL_PATH" \
  --host 127.0.0.1 --port 8000 --served-model-name "$MODEL" \
  --max-model-len 4096 --max-num-seqs 4 --gpu-memory-utilization 0.30 \
  --enforce-eager

# In another terminal, wait for /health and verify a first real generation.
# A random prompt workload is a plumbing check, not task quality.
vllm bench serve --backend vllm --base-url http://127.0.0.1:8000 \
  --endpoint /v1/completions --model "$MODEL" --tokenizer "$MODEL_PATH" \
  --dataset-name random --random-input-len 128 --random-output-len 32 \
  --num-prompts 4 --max-concurrency 1 --seed 42 --ignore-eos \
  --num-warmups 1 --temperature 0 \
  --save-result --result-dir results --result-filename text-smoke.json
```

In a real campaign replace synthetic input with a frozen workload and explicit
warmup/load settings. Check completed/failed requests and output length, then
read `median_ttft_ms` as a finite positive objective. With four requests,
percentiles do not establish production tail behavior. Offline cached operation
can set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; incomplete cached weights
are a preparation failure, not a benchmark result.

For task quality and alternative performance entry points:

```bash
# Run from the pinned vLLM checkout; this evaluates generated math answers.
python tests/evals/gsm8k/gsm8k_eval.py \
  --port 8000 --num-questions "$QUALITY_N" --save-results gsm8k.json

# Run using the pinned SGLang evaluator and benchmark installation.
sgl-eval run gsm8k --base-url http://127.0.0.1:30000/v1 \
  --num-examples "$QUALITY_N"
python -m sglang.benchmark.serving --backend sglang --port 30000 \
  --dataset-name random --num-prompts "$PERF_N" \
  --max-concurrency "$CONCURRENCY" --output-file results.jsonl

aiperf profile "$MODEL" --url http://127.0.0.1:8000 \
  --endpoint-type chat --accuracy-benchmark gsm8k \
  --num-requests "$QUALITY_N" --concurrency "$CONCURRENCY" \
  --extra-inputs '{"temperature":0}'
```

Freeze shots, reasoning/generation budgets, extraction and evaluator versions.
A GSM8K workload does not necessarily represent production performance.

## Agent replay

```bash
aiperf profile --model "$MODEL" --tokenizer "$TOKENIZER" \
  --url http://127.0.0.1:8000 --endpoint-type chat \
  --scenario inferencex-agentx-mvp \
  --public-dataset semianalysis_cc_traces_weka_062126 \
  --max-context-length "$CONTEXT_LIMIT" --concurrency "$CONCURRENCY" \
  --benchmark-duration 1800 --random-seed 42 \
  --streaming --use-server-token-count --extra-inputs ignore_eos:true \
  --cache-bust first_turn_prefix --system-idle-gap-cap-seconds 10 \
  --artifact-dir artifacts/agentx

aiperf profile --model "$MODEL" --url http://127.0.0.1:8000 \
  --endpoint-type chat --public-dataset exgentic_v2 \
  --dataset-filter benchmark=appworld --dataset-filter harness=tool_calling \
  --dataset-filter source_model="$SOURCE_MODEL" \
  --num-conversations "$SESSIONS" --concurrency "$CONCURRENCY" --streaming \
  --artifact-dir artifacts/work
```

AgentX's 1800-second duration is the cited scenario default, not a suggested
brief smoke. Shortened/custom runs must retain their non-comparable status.
Set context capacity to the actual server limit; check endpoint token-limit
field support. Exgentic output-budget and scheduling rules differ from AgentX.
Do not copy `ignore_eos` into another workload without recording that change.
Replay success and `submission_valid` are not task-success scores.

## TTS and full-duplex

```bash
SEED_TTS_SIM_EVAL=1 SEED_TTS_UTMOS_EVAL=1 \
python benchmarks/tts/bench_tts.py \
  --model "$MODEL" --task voice_clone --dataset-path "$SEED_TTS_DIR" \
  --wer-eval --concurrency "$CONCURRENCY" --num-prompts "$QUALITY_N" \
  --output-dir results-quality

python -m benchmarks.eval.benchmark_tts_seedtts \
  --model "$MODEL" --meta "$SEED_TTS_META" --port 8000 \
  --generate-only --stream --concurrency "$CONCURRENCY" \
  --max-samples "$PERF_N" --output-dir results-tts

vllm bench serve --omni --backend openai-realtime-duplex \
  --dataset-name omniinteract --dataset-path "$OMNIINTERACT_DATA" \
  --model "$DUPLEX_MODEL" --base-url http://127.0.0.1:8000 \
  --endpoint /v1/realtime --omniinteract-ref-audio "$REF_WAV" \
  --omniinteract-output-dir results-omniinteract \
  --num-prompts "$PERF_N" --max-concurrency "$CONCURRENCY" \
  --num-warmups 0 --save-result

vllm bench serve --omni --backend openai-realtime-duplex \
  --dataset-name omni-duplex-eval --dataset-path "$DUPLEX_EVAL_DATA" \
  --model "$DUPLEX_MODEL" --base-url http://127.0.0.1:8000 \
  --endpoint /v1/realtime --duplex-eval-ref-audio "$REF_WAV" \
  --duplex-eval-response-root results-duplexeval \
  --duplex-eval-split PR_correction --num-prompts "$PERF_N" \
  --disable-shuffle --max-concurrency "$CONCURRENCY" --num-warmups 0 \
  --ready-check-timeout-sec 0 --save-result
```

The SGLang-Omni TTS example only generates audio; evaluate saved WAVs separately
with its `--transcribe-only`, `--similarity-only` and `--utmos-only` modes using
the same frozen evaluators for both sides. The realtime examples collect outputs;
they do not enable optional judges. Follow the cited realtime guide for
`--omniinteract-evaluate` or `--duplex-eval-evaluate` and judge configuration.
RTD needs a visual judge. FDB uses `python -m benchmarks.duplex.fdb` with the
runbook's generate/asr/judge/aggregate stages; select v1.0 or v1.5 explicitly.

## Diffusion

```bash
# From vLLM-Omni; choose t2i/t2v/etc. to match the running server.
python benchmarks/diffusion/diffusion_benchmark_serving.py \
  --base-url http://127.0.0.1:8000 --model "$MODEL" --task "$TASK" \
  --dataset random --num-prompts "$PERF_N" --output-file diffusion.json

# From SGLang; this uses VBench inputs for performance, not quality scoring.
python -m sglang.multimodal_gen.benchmarks.bench_serving \
  --dataset vbench --num-prompts "$PERF_N" --port 8000
```

Freeze resolution, steps, frames, FPS, output count and delivery boundary, and
save media for a separate quality evaluator. Neither command computes general
T2I quality or VBench temporal-quality scores automatically.

## Existing InferRSI integration

Supply reviewed trial scripts that start the intended server, warm up, invoke
the native benchmark, write to `INFERRSI_RESULT_PATH` and clean up. A thin
adapter may select one current JSONL run or normalize an AIPerf export, but must
preserve the native artifacts, metric units and failure accounting.

```bash
inferrsi plan \
  --repo "$BASELINE_REPO" --candidate-repo "$CANDIDATE_REPO" \
  --repo-type vllm --backend cuda --device-ids "$GPU_ID" \
  --python "$TRIAL_PYTHON" --scenario text_generation \
  --model "$MODEL" --model-revision "$MODEL_REVISION" --workload-id "$WORKLOAD_ID" \
  --baseline-command "$BASELINE_TRIAL_COMMAND" \
  --candidate-command "$CANDIDATE_TRIAL_COMMAND" \
  --validation-command "$QUALITY_COMMAND" \
  --metric-key median_ttft_ms --metric-unit ms --comparison-scope http_e2e \
  --direction minimize --repetitions "$REPETITIONS" \
  --min-improvement-pct "$TARGET_REDUCTION_PCT" --max-minutes "$MAX_MINUTES" \
  --output-dir "$RUN_OUTPUT_DIR"
```

Use `run` with the same frozen arguments after reviewing the plan. These command
variables are user-supplied trusted commands, not strings extracted from model
output. No new built-in scenario, adapter or evaluator is introduced here.
`--validation-command` must verify the actual quality/coverage gates; a health
check or one arithmetic response only establishes a smoke path. A one-server
feasibility run is not an A/B campaign and cannot establish `PASS` or a speedup.
