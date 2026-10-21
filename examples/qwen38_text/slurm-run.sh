#!/usr/bin/env bash
# Submit with explicit partition, GPU/CPU/memory/time and private output paths.
set -euo pipefail
: "${SLURM_JOB_ID:?Run under a Slurm allocation}"
: "${TASK_ROOT:?Set the authorized remote task root}"
: "${CONTROL_REPO:?Set the frozen InferRSI checkout}"
: "${TASK_PYTHON:?Set the registered uv environment interpreter}"
TASK_ROOT=$(realpath -e "$TASK_ROOT")
export TASK_ROOT
CONTROL_REPO=$(realpath -e "$CONTROL_REPO")
TASK_PYTHON=$(realpath -s -e "$TASK_PYTHON")
for task_path in "$CONTROL_REPO" "$TASK_PYTHON"; do
    case "$task_path" in "$TASK_ROOT"/*) ;; *) echo 'Task path escapes root' >&2; exit 2;; esac
done
export TMPDIR="$TASK_ROOT/tmp/qwen38-$SLURM_JOB_ID"
export XDG_CACHE_HOME="$TASK_ROOT/cache/qwen38"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export TRITON_CACHE_DIR="$XDG_CACHE_HOME/triton"
export VLLM_CACHE_ROOT="$XDG_CACHE_HOME/vllm"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
for task_path in "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$HF_HOME" \
                 "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"; do
    case "$(realpath -m "$task_path")" in
        "$TASK_ROOT"/*) mkdir -p "$task_path" ;;
        *) echo 'Cache path escapes root' >&2; exit 2 ;;
    esac
done
cd "$CONTROL_REPO"
export PYTHONPATH="$CONTROL_REPO/src:$CONTROL_REPO"
exec "$TASK_PYTHON" -m examples.qwen38_text.launch "$@"
