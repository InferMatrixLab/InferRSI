#!/usr/bin/env bash
#SBATCH --job-name=qwen38-eval-platform-fs
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:03:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}" "${BASE_PYTHON:?}" "${SOURCE_DIR:?}" "${OUTPUT_DIR:?}"
: "${SCRIPT_SHA256:?}" "${PROBE_SHA256:?}" "${DRIVER_SHA256:?}" "${PYTHON_SHA256:?}"
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
inside_root() {
    local path
    path=$(realpath -m "$1")
    case "$path" in "$root"/*) ;; *) exit 2;; esac
}
for path in "$BASE_PYTHON" "$SOURCE_DIR" "$OUTPUT_DIR"; do inside_root "$path"; done
check_digest() {
    [[ $2 =~ ^[a-f0-9]{64}$ ]]
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
check_digest "$SOURCE_DIR/probe.py" "$PROBE_SHA256"
check_digest "$SOURCE_DIR/platform_fs.py" "$DRIVER_SHA256"
check_digest "$BASE_PYTHON" "$PYTHON_SHA256"
cmp "${BASH_SOURCE[0]}" "$SOURCE_DIR/run.sbatch"
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]]
export TMPDIR="$root/tmp/qwen38-eval-platform-fs-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-eval-sandbox"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export TRITON_CACHE_DIR="$XDG_CACHE_HOME/triton"
export VLLM_CACHE_ROOT="$XDG_CACHE_HOME/vllm"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME PYTHONINSPECT PYTHONSTARTUP PYTHONOPTIMIZE VIRTUAL_ENV
for path in "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"; do
    inside_root "$path"
    mkdir -p "$path"
done
cd "$root"
status=0
"$BASE_PYTHON" -IB "$SOURCE_DIR/platform_fs.py" --output "$OUTPUT_DIR" || status=$?
if [[ -d "$OUTPUT_DIR" ]]; then
    printf '%s\n' "$status" > "$OUTPUT_DIR/helper-exit-code"
    cp "$SOURCE_DIR/run.sbatch" "$SOURCE_DIR/probe.py" "$SOURCE_DIR/platform_fs.py" "$OUTPUT_DIR/"
fi
check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
check_digest "$SOURCE_DIR/probe.py" "$PROBE_SHA256"
check_digest "$SOURCE_DIR/platform_fs.py" "$DRIVER_SHA256"
exit "$status"
