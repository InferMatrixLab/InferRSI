#!/usr/bin/env bash
# Use the native benchmark; run quality separately from performance.
set -euo pipefail
: "${OMNI_REPO:?set checkout}"
: "${PYTHON:?set prepared interpreter}"
: "${MODEL_PATH:?set local frozen checkpoint}"
: "${DATASET_PATH:?set Seed-TTS Eval root}"
: "${RESULT_DIR:?set private result directory}"
: "${CONCURRENCY:?set fixed client concurrency}"
: "${RESULT_FILENAME:?set distinct trial JSON name}"
export PYTHONPATH="$OMNI_REPO${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m vllm_omni.entrypoints.cli.main bench serve --omni \
  --host 127.0.0.1 --port "${PORT:-28931}" \
  --model Qwen/Qwen3-Omni-30B-A3B-Instruct --tokenizer "$MODEL_PATH" \
  --backend openai-chat-omni --endpoint /v1/chat/completions \
  --dataset-name seed-tts-text --dataset-path "$DATASET_PATH" --seed-tts-locale en \
  --num-prompts "${NUM_PROMPTS:-256}" --num-warmups 5 \
  --max-concurrency "$CONCURRENCY" --request-rate inf \
  --no-oversample --disable-shuffle --seed 0 \
  --percentile-metrics ttft,e2el,audio_rtf,audio_ttfp,audio_duration \
  --metric-percentiles 50,95,99 \
  --extra-body '{"modalities":["text","audio"]}' \
  --save-result --save-detailed --result-dir "$RESULT_DIR" \
  --result-filename "$RESULT_FILENAME" "$@"
