# Redacted operational copy; <REMOTE_ROOT> supplied privately. Hash differs from submitted wrapper.
#!/usr/bin/env bash
#SBATCH --job-name=qwen38-fi-gemm
#SBATCH --partition=h20
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=00:30:00
#SBATCH --chdir=<REMOTE_ROOT>/artifacts/qwen38-flashinfer-gemm-v3
#SBATCH --output=<REMOTE_ROOT>/artifacts/qwen38-flashinfer-gemm-v3/baseline-%j.log
set -euo pipefail
umask 077
TASK_ROOT=<REMOTE_ROOT>
TASK_OUT="$TASK_ROOT/artifacts/qwen38-flashinfer-gemm-v3"
export TMPDIR="$TASK_OUT/tmp" XDG_CACHE_HOME="$TASK_OUT/baseline-cache"
export HF_HOME="$TASK_OUT/baseline-cache/hf" TORCH_HOME="$TASK_OUT/baseline-cache/torch"
export UV_CACHE_DIR="$TASK_OUT/baseline-cache/uv" TRITON_CACHE_DIR="$TASK_OUT/baseline-cache/triton"
export VLLM_CACHE_ROOT="$TASK_OUT/baseline-cache/vllm" CUDA_CACHE_PATH="$TASK_OUT/baseline-cache/cuda"
export FLASHINFER_WORKSPACE_BASE="$TASK_ROOT/artifacts/qwen38-benchmark-http/baseline-cache/flashinfer"
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1
unset PYTHONPATH OMP_NUM_THREADS
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" "$UV_CACHE_DIR" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT" "$CUDA_CACHE_PATH" "$FLASHINFER_WORKSPACE_BASE"
trap 'task_rc=$?; printf "%s\n" "$task_rc" > "$TASK_OUT/baseline-exit-$SLURM_JOB_ID.txt"' EXIT
date -u +%FT%TZ
printf 'job=%s visible=%s\n' "$SLURM_JOB_ID" "${CUDA_VISIBLE_DEVICES:-unset}"
nvidia-smi --query-gpu=name,uuid,memory.total,driver_version --format=csv,noheader
sha256sum source.tar operator_probe.py http_probe.py > "$TASK_OUT/sources-$SLURM_JOB_ID.sha256"
export PYTHONPATH="$TASK_ROOT/sources/nanovllm-qwen38-flashinfer-gemm"
timeout --signal=TERM --kill-after=20s 400s "$TASK_ROOT/software/qwen38-vllm032/bin/python" -u operator_probe.py --output "$TASK_OUT/operator-$SLURM_JOB_ID.json"
timeout --signal=TERM --kill-after=35s 1300s "$TASK_ROOT/software/qwen38-vllm032/bin/python" -u http_probe.py --source "$PYTHONPATH" --model "$TASK_ROOT/models/Qwen3.8-27B-FP8" --fixture "$TASK_ROOT/artifacts/qwen38-vllm032-readiness/fixture-v1/fixture.json" --output "$TASK_OUT/http-$SLURM_JOB_ID"
date -u +%FT%TZ
